# Changelog

All notable changes to **Grillo Parlante (Calobot)** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Budget-Aware Recipe Suggestions**: The advice agent can now recommend healthy, Italian-style recipe ideas when asked "cosa posso mangiare stasera?" or similar, using the user's specific remaining calorie budget.
- **Empathetic Calorie Deficit Counseling**: Added support for empathetic counseling and volume-satiety alternatives (such as clear vegetable broths, cucumbers, or fennel under 100 kcal) if the user has exhausted or exceeded their calorie budget, ensuring no meal-skipping is encouraged.

### Fixed
- **Correction Routing Bug**: Fixed a bug where replying directly to the "modifica" instruction prompt message caused the bot to process it as a fresh, contextless message instead of targeting the correction of the correct entry.
- **Clinical Safety Guardrails**: Expanded the deterministic safety keyword guard filter to block cardiovascular and metabolic queries (such as cholesterol, hypertension, and blood pressure) at the code level, keeping the agent safe and clinical-free.

## [0.2.0] - 2026-08-19

### Added
- **Read-Only Advice Agent**: Introduced the `other` intent handler and two-phase Advice Agent (Gather & Narration) for responding to open-ended questions about logged food, weight, and activity.
- **Persistent Conversational Drafts**: Added local state preservation for pending drafts in no-retention mode.
- **Tailored Activity Corrections**: Implemented physical activity duration and description corrections with automated MET re-calculations.
- **JSONL Interaction Logger**: Built high-efficiency structured JSONL telemetry logging for all chat interactions and causal tracing.

## [0.1.1] - 2026-08-16

### Added
- **Behavioral Dietician Reviews**: Added weekly and monthly dietary behavioral reviews in Italian (evaluating calorie density, meal timings, variety, and registration accuracy).
- **Photo Input Integration**: Supported Reading nutritional labels (OCR), barcode lookup (Open Food Facts), and dish visual classification.
- **Simulation Harness & Guardrails**: Integrated a conversation simulation harness, False Confirmation Guard, and Clarification Escape Loop for automated testing.
- **Real-Time Telemetry Monitor**: Built a reactive dashboard and causal session tracing via WebSockets and FastAPI.
- **Activity Export API**: Added structured JSON history export endpoints.
- **Italian Localization**: Fully localized user README.md and commands into Italian.

### Fixed
- **Clock Seam & Timezones**: Fixed timezone offset calculations in `when_text` date resolution.
