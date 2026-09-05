## 1. Content

- [x] 1.1 Extend `HELP_TEXT` in `src/calobot/telegram/handlers.py` with a corrections line (amend the last entry by writing the correction; `/annulla` deletes it) and a nudges paragraph (occasional, opt-in via `/notifiche_on`, kinds: pause in logging, goal reached, advice left unapplied, off via one reply or `/notifiche_off`); verify the existing help tests still pass
- [x] 1.2 Extend `_welcome_message` with the counted-quantities line (calories and macronutrients, not sodium or sugar) and the opt-in proactive-messages line, keeping the disclaimer and the profile-setup lead untouched; verify `task typecheck` adds no errors

## 2. Tests

- [x] 2.1 Add content assertions to `tests/test_help_command.py`: corrections line ("200g", delete-last command), nudge description (opt-in, kinds, off switch), and a welcome-content test for the new user path (macros named, sodium/sugar disclaimed, opt-in messages mentioned, disclaimer present); verify with `uv run pytest tests/test_help_command.py`
- [x] 2.2 Run `task check` and confirm no new lint/type failures beyond the pre-existing set; run `openspec validate --changes`
