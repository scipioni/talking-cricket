"""Render a saved simulation report for reading.

    uv run python scripts/show_run.py [simulation-runs/<name>.report.json]

Reads the JSON rather than importing the harness, so it works from anywhere and does
not drag the test tree into a script. Prints failures first, because the point of
reading a report is finding what to act on.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "simulation-runs"


def _wrap(text: str, label: str) -> str:
    # Continuation lines are padded to the label's width rather than repeating it, so
    # a wrapped reply reads as one block instead of looking like several.
    return textwrap.fill(
        text, width=96, initial_indent=label, subsequent_indent=" " * len(label)
    )


def render(report: dict) -> str:
    lines = [
        f"scenario:    {report['scenario']}",
        f"persona:     {report['persona']}"
        + (f"  ({', '.join(report['behaviours'])})" if report["behaviours"] else ""),
        f"seed:        {report['seed']}",
        f"result:      {'PASSED' if report['passed'] else 'FAILED'}"
        + ("  (stopped early)" if report["stopped_early"] else ""),
    ]
    if report.get("model_calls"):
        cost = f"{report['model_calls']} model calls"
        if report.get("duration_seconds"):
            cost += f" in {report['duration_seconds']:.0f}s"
        lines.append(f"cost:        {cost}")
    if report.get("cassette"):
        lines.append(f"recording:   {report['cassette']}")

    failed = [v for v in report["verdicts"] if not v["passed"]]
    failures = report["failures"]

    if failures:
        lines += ["", f"-- {len(failures)} code-attributable failure(s) " + "-" * 40]
        for failure in failures:
            lines.append(f"\n  [{failure['kind']}] action {failure['action_index']}")
            lines.append(_wrap(failure["action"], "    where: "))
            lines.append(_wrap(failure["detail"], "    what:  "))

    if failed:
        lines += ["", f"-- {len(failed)} unmet expectation(s) " + "-" * 45]
        for verdict in failed:
            lines.append(f"\n  step {verdict['step_index']}: expected {verdict['expected']}")
            lines.append(_wrap(verdict["intent"], "    meant: "))
            lines.append(_wrap(verdict["said"], "    said:  "))
            for reply in verdict["replies"]:
                lines.append(_wrap(reply, "    bot:   "))
            lines.append(_wrap(verdict["detail"], "    ->     "))

    if not failures and not failed:
        lines += ["", f"all {len(report['verdicts'])} steps met their expectations"]

    metrics = report.get("metrics")
    if metrics:
        total = metrics["from_food_table"] + metrics["from_model_estimate"]
        share = metrics["from_food_table"] / total if total else 0.0
        lines += [
            "",
            "-- metrics (trends, never a gate) " + "-" * 40,
            f"  entries stored:                {metrics['entries_stored']}",
            f"  clarification turns per entry: {metrics['clarification_turns_per_entry']:.2f}",
            f"  replies off intent:            {metrics['off_intent_replies']}",
            f"  resolved from the food table:  {share:.0%}",
        ]
    return "\n".join(lines)


def main() -> int:
    paths = (
        [Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(RUNS.glob("*.report.json"))
    )
    if not paths:
        print(f"no reports in {RUNS}/ - run `task simulate` first", file=sys.stderr)
        return 1
    for path in paths:
        print(render(json.loads(path.read_text())))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
