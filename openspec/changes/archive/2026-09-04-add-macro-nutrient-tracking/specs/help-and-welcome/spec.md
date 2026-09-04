## MODIFIED Requirements

### Requirement: The help text states what the bot does not track

The help text SHALL name at least the quantities a user is most likely to assume are
tracked and are not — in particular sodium and sugar — so that the limit is learned from
the documentation rather than from being refused mid-conversation. Where the bot does
track a quantity (calories and, as of this requirement's update, macronutrients), the help
text SHALL say so rather than disclaiming it.

#### Scenario: A user wonders whether macronutrients are tracked

- **WHEN** a user reads the help text
- **THEN** it states that the bot tracks calories and macronutrients, and does not track
  sodium or sugar
