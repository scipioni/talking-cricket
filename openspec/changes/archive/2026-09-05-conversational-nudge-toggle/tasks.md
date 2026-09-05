## 1. Intent plumbing

- [x] 1.1 Add `nudges` to the `Intent` Literal in `ingestion/schemas.py` and add a `NudgesExtraction` schema with a single enable/disable field; verify `task typecheck` adds no errors
- [x] 1.2 Add the `nudges` intent line to the classifier prompt in `ingestion/classifier.py` with enable and disable examples, and note that questions about notifications stay `other`; verify the prompt renders
- [x] 1.3 Add `extract_nudges` in `ingestion/extractors.py` following the `extract_report` pattern; verify import and `task typecheck`

## 2. Pipeline behaviour

- [x] 2.1 Add the `nudges` dispatch branch and `_handle_nudges` in `ingestion/pipeline.py`: extract, set `User.nudges_enabled`, commit, and confirm with the same texts the commands send, with an "already on/off" variant when nothing changes; verify with e2e tests

## 3. Help text and tests

- [x] 3.1 Amend the help text's nudge paragraph to mention the free-form way ("basta scrivermelo"); verify the help tests still pass
- [x] 3.2 Add e2e tests: enable statement turns the preference on and confirms; disable statement turns it off and confirms; a statement matching the current state confirms without claiming a change; verify with `uv run pytest tests/test_pipeline_e2e.py tests/test_nudges.py tests/test_help_command.py`
- [x] 3.3 Run `task check` (expect only the pre-existing lint/type failures) and `openspec validate --changes`
