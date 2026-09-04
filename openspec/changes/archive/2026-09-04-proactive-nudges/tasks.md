## 1. Schema

- [x] 1.1 Add `nudges_enabled: bool = False` and `last_nudge_sent_at: dt.datetime |
      None` to `User` in `calobot.persistence.models`.
- [x] 1.2 `task migration -- "add nudge preference to users"`.
- [x] 1.3 Confirm `hard_delete_user` already removes these (they're columns on
      `User`, not a separate table) - verified by a test, not just inspection.

## 2. Preference: command and button

- [x] 2.1 `/notifiche_on`, `/notifiche_off` commands in `telegram/handlers.py`,
      following the `/memory_on`/`/memory_off` pattern.
- [x] 2.2 A `nudge:stop` callback (button attached to every nudge) that disables the
      preference and edits/replies confirming it, following the `entry:`/`ans:`
      callback pattern already in `handlers.py`.
- [x] 2.3 `format_profile_summary` (`profile/service.py`) reports whether nudges are
      enabled.
- [x] 2.4 `HELP_TEXT` documents the two commands.

## 3. Signals

- [x] 3.1 New module `calobot.nudges.signals`:
  - [x] 3.1.1 `goal_reached_recently(session, user, tz) -> bool` - latest weight
        entry reaches `peso_obiettivo_kg` and was recorded within the recency
        window (design.md - Decisions).
  - [x] 3.1.2 `broken_logging_streak(session, user, tz) -> bool` - no food logged in
        the last `streak_break_days`, but food was logged in the window before that
        (design.md - Decisions: requires prior engagement).
  - [x] 3.1.3 `unresolved_suggestion(session, user, tz) -> AdviceRecord | None` -
        oldest-first undetermined, topic-tagged `AdviceRecord` older than the
        minimum age.
  - [x] 3.1.4 `find_candidate(session, user, tz, settings) -> NudgeCandidate | None`
        - fixed priority order (design.md - Decisions), returns at most one.

## 4. Content and sending

- [x] 4.1 New module `calobot.nudges.messages`: one fixed Italian template per
      candidate kind, each including the opt-out instruction; a
      `compose(candidate) -> str` function.
- [x] 4.2 New module `calobot.nudges.service`:
  - [x] 4.2.1 `run_nudge_cycle(bot, settings) -> None` - iterates users with
        `nudges_enabled=True`, skips a chat in no-retention mode entirely, skips
        during quiet hours, skips if the rate limit hasn't elapsed, else evaluates
        `find_candidate` and sends if one fires.
  - [x] 4.2.2 Before sending, run the composed text through
        `calobot.safety.medical.is_medical_topic`; skip (log) if it trips.
  - [x] 4.2.3 On send, attach the `nudge:stop` inline button and update
        `last_nudge_sent_at`.

## 5. Wiring

- [x] 5.1 `calobot.settings.Settings`: `nudge_check_interval_seconds`,
      `nudge_min_interval_days`, `nudge_quiet_hours_start`,
      `nudge_quiet_hours_end`, `nudge_streak_break_days`,
      `nudge_goal_reached_recency_days`, `nudge_suggestion_min_age_days`.
- [x] 5.2 `main.py`: after constructing `bot` and `scheduler`, register
      `scheduler.register("proactive_nudges", settings.nudge_check_interval_seconds,
      lambda: run_nudge_cycle(bot, settings))`.

## 6. Tests

- [x] 6.1 Each signal function: fires when its condition holds, does not fire
      otherwise (including the "no prior engagement" / "not recent enough" /
      "too young a record" negative cases from design.md - Decisions).
- [x] 6.2 `find_candidate` priority ordering when more than one signal would fire.
- [x] 6.3 `run_nudge_cycle`: sends when a candidate fires and the user is opted in,
      outside quiet hours, and past the rate limit; does not send otherwise for each
      of those gates individually.
- [x] 6.4 No-retention mode: a chat in no-retention mode is skipped entirely by the
      cycle.
- [x] 6.5 `/notifiche_on` / `/notifiche_off` commands.
- [x] 6.6 `nudge:stop` callback disables the preference.
- [x] 6.7 `last_nudge_sent_at` is updated on send and enforces the rate limit on the
      next cycle.
- [x] 6.8 Content constraint tests: each template contains no forbidden framing
      (spot-check against the literal templates, not a classifier).

## 7. Verification

- [x] 7.1 `task check` passes (diffed against the established pre-existing
      baseline).
