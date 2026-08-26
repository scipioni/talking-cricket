import json
import sys
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

# Provide path to calobot project root
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import asyncio
from typing import TypedDict
from calobot.settings import get_settings

try:
    from tests.harness.simulation import score, snapshot
    from tests.harness.user_agent import SimulatedUser
    from tests.harness.scenario import Scenario, Persona, Step, NothingStored, StoredFood, StoredWeight
    from tests.harness.run import CheckedRun, RunStopped
    from tests.harness.client import Client
    from tests.harness.transport import FakeBot
except ImportError as e:
    print(f"Error importing harness: {e}", file=sys.stderr)
    sys.exit(1)

class QA_Config(TypedDict):
    persona: str
    intent: str
    behaviour: str

async def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/run_qa_scenario.py <config.json>", file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[1])
    config = json.loads(config_path.read_text())
    
    settings = get_settings()
    now = dt.datetime.now(settings.timezone)

    persona = Persona(
        name=config["persona"],
        description=f"A user with persona: {config['persona']}",
        repertoire=()
    )
    
    step = Step(
        intent=config["intent"],
        expect=NothingStored(), # We just care about UX, so expect NothingStored is fine
        behaviour=config.get("behaviour", "straight")
    )

    scenario = Scenario(
        name="qa-test",
        persona=persona,
        starts_at=now,
        steps=[step],
        action_cap=15, # prevent long loops
    )

    bot = FakeBot()
    client = Client(bot, settings)
    user = SimulatedUser(client)
    run = CheckedRun(bot, client, user, invariants=[])

    try:
        verdicts = await score(scenario, run, settings)
    except RunStopped:
        verdicts = run.verdicts
    except Exception as e:
        print(f"Error running scenario: {e}", file=sys.stderr)
        sys.exit(1)

    result = snapshot(scenario, seed=1, run=run, verdicts=verdicts, settings=settings)
    
    if "cassette" in result:
        del result["cassette"]
    if "metrics" in result:
        del result["metrics"]

    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
