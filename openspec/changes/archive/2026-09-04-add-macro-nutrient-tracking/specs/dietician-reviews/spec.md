## MODIFIED Requirements

### Requirement: Dietician review structured schema

The system SHALL enforce that the dietician review adheres to a structured format containing a warm summary, an energy density/volume insight, a temporal timing/regularity insight, a data sourcing/provenance quality insight, and a single practical actionable recommendation. The actionable recommendation SHALL be tiered by period:

- For a **week** period, the recommendation SHALL be framed as advice for the remaining days of that week, taking into account the week's calorie and eating-pattern trend so far.
- For a **month** or **year** period, the recommendation SHALL be framed as a general health habit to adopt going forward, and SHALL explicitly address macronutrient balance (protein, fat and carbohydrate variety) in qualitative terms, without stating a specific gram amount of any macronutrient — this review reasons from the indirect signals (density, timing, variety, provenance) it is already built on, not from macro grams, which a user can obtain from the dedicated macro report instead.

#### Scenario: Review conforms to schema
- **WHEN** the dietician review is generated
- **THEN** the output contains a general summary, a density insight, a timing pattern insight, a sourcing quality insight, and a single actionable tip, all in Italian

#### Scenario: Weekly review recommendation looks forward

- **WHEN** a dietician review is generated for a week period
- **THEN** the actionable recommendation is framed around what to do for the rest of that week

#### Scenario: Monthly or yearly review recommendation addresses macro balance

- **WHEN** a dietician review is generated for a month or year period
- **THEN** the actionable recommendation is a general habit recommendation that qualitatively addresses protein, fat and carbohydrate balance, without stating a specific gram amount for any macronutrient
