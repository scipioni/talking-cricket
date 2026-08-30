## 1. Welcome message

- [x] 1.1 Confirm `_welcome_message` shows a concrete example for asking about own data
  and for asking a meal suggestion — verify a test asserts both example lines are present
- [x] 1.2 Confirm the experimental / not-medical disclaimer and the lead-in to profile
  setup survive — verify `tests/test_welcome_message.py` asserts both

## 2. Help text

- [x] 2.1 Confirm `HELP_TEXT` lists the commands and shows a concrete example for each
  conversational capability: food, activity, weight, report, question about own data,
  meal suggestion, photo, profile correction — verify a test asserts one marker per
  capability
- [x] 2.2 Add a line stating that the bot tracks calories and does not track
  macronutrients — verify a test asserts the help text names the limit

## 3. Spec coverage

- [x] 3.1 Extend `tests/test_welcome_message.py` with one test per scenario in the
  `help-and-welcome` delta spec — verify each test names the scenario it covers
- [x] 3.2 Run `openspec validate help-and-welcome-cover-advice --strict` and confirm it
  passes
- [x] 3.3 Run `task check` and verify no new test failures, lint errors or `mypy` errors
  against the pre-change baseline
