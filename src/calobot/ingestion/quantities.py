"""What counts as a quantity at all (specs/message-ingestion - A stored entry
carries a real quantity).

Lives here rather than in food/ or activity/ because it is an ingestion-wide floor:
both capabilities apply it, and neither should have to depend on the other to get it.
"""

from __future__ import annotations

from typing import TypeGuard


def is_real_quantity(value: float | None) -> TypeGuard[float]:
    """A quantity is an amount, not merely a value that is present.

    This used to be an `is not None` check at each call site, and a zero passed it: a
    message dictating "registra 0 calorie per la cena" produced a stored food entry of
    0 g, because nothing between extraction and writing asked whether the number meant
    anything. Weight had a plausibility band from the start, which is why an absurd
    weight was always refused while an absurd portion was not - the asymmetry was the
    defect, not the message that exposed it.

    A value that fails this is treated as *unresolved*, so it flows into the existing
    clarification loop rather than becoming an error with nowhere to go.

    Typed as a TypeGuard so callers get real narrowing from it: after the check the
    value is a float, and the type checker knows it without a cast.
    """
    return value is not None and value > 0
