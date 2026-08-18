"""Whether a reply tells the user something went into the log
(specs/message-ingestion - Only the storing path may confirm a record).

DELIBERATE DUPLICATION - DO NOT MERGE WITH THE HARNESS DETECTOR.

The simulation harness carries its own, independent implementation of this same
question (`tests/harness/invariants.py`). Sharing one implementation between the
guard and the check that verifies the guard would make a defect in it invisible:
the guard would fail to fire and the invariant would fail to notice, at the same
moment and for the same reason. Two implementations that can disagree are the point.
This one scopes negation by clause; the harness one strips negated spans by pattern.
If they ever disagree, that is a gap surfacing, not a bug to deduplicate away.
"""

from __future__ import annotations

import re

# Verb stems that assert something was written to, changed in, or removed from the
# diary. Stems rather than whole words, because Italian inflects these heavily
# (registrato/registrata/registrati/registrate). Deletion and modification stems were
# added for the advice agent (specs/advice-agent - The agent's data access is
# read-only: "Answer claims a record was made" covers recorded, changed or removed
# alike), and apply equally on the conversational path this guard already covered -
# a false claim of having deleted or edited an entry is the same failure as a false
# claim of having created one.
_RECORDED_STEMS = (
    "registrat",
    "salvat",
    "memorizzat",
    "annotat",
    "aggiunt",
    "inserit",
    "eliminat",
    "cancellat",
    "modificat",
    "rimoss",
    # A profile edit uses a different verb family from the diary - these were added
    # for the conversational profile-edit path (specs/message-ingestion - Only the
    # storing path may confirm a record), and until now passed through unrecognised:
    # the bot could already claim to have updated a goal it never touched.
    "aggiornat",
    "impostat",
    "cambiat",
)

_NEGATIONS = ("non", "nessun", "nessuna", "niente", "nulla", "senza")

# Sentences first, then clauses within them. Negation scopes to a clause; being a
# question scopes to the whole sentence.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\n])\s*")
_CLAUSE_SPLIT = re.compile(r"[,;:]")
_WORD = re.compile(r"[a-zàèéìòù']+")


def asserts_a_record(text: str) -> bool:
    """True when some clause of `text` claims a record was made, unnegated.

    Two things stop a mention of recording from being a claim:

    - **Negation**, scoped to its clause, so the ignored-text notice
      ("... - non l'ho registrato, scrivimelo di nuovo") reads as what it is.
    - **Being a question**, scoped to its sentence. A past participle can describe an
      existing entry rather than assert a new one: "Intendi correggere l'ultima voce
      registrata o e una voce nuova?" asks about a record, it does not claim one.
      A live simulation run flagged exactly that reply, from the correction path.
    """
    for sentence in _SENTENCE_SPLIT.split(text.lower()):
        if "?" in sentence:
            continue
        for clause in _CLAUSE_SPLIT.split(sentence):
            if not any(stem in clause for stem in _RECORDED_STEMS):
                continue
            if set(_WORD.findall(clause)).isdisjoint(_NEGATIONS):
                return True
    return False
