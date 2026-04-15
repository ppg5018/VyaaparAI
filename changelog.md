# changelog.md — VyaparAI Module 1

All notable changes to this project. Most recent entry at the top.
Format: `## [date] — [what changed]`

---

## [April 2026] — Project initialised

- Created project spec doc (product + engineering requirements)
- Created CLAUDE.md, architecture.md, project-status.md
- Created .env.example with all required keys
- Defined database schema: businesses, health_scores, pos_records
- Defined health score formula: review × 0.40 + competitor × 0.25 + pos × 0.35
- Decided: POS score defaults to 50 (neutral) when no data — not 0
- Decided: synthetic CSV first, Petpooja API when approved
- Decided: WhatsApp + scheduler + Hindi deferred to V2
- Created GitHub issues #1–#14 covering all MVP phases

---

*Add a new entry every time you:*
- *Add or remove a file*
- *Change a function signature or formula*
- *Add or modify a database table/column*
- *Make a scope decision (in or out)*
- *Pass a quality gate*
- *Fix a bug that could recur*
