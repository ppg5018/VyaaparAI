# Update Docs

Review the current state of the codebase and update `CLAUDE.md` to reflect any changes since it was last written.

## Steps

1. Read the current `CLAUDE.md`
2. Scan all key files: `main.py`, `google_places.py`, `health_score.py`, `insights.py`, `pos_pipeline.py`, `generate_synthetic_pos.py`
3. Check for:
   - New files added to the project
   - Endpoints added, renamed, or removed in `main.py`
   - Changes to the health score formula or weights in `health_score.py`
   - New or modified database tables/columns (look for Supabase queries)
   - Changes to Claude API model name or output format in `insights.py`
   - Any quality gates that have been passed (check git log for evidence)
4. Update `CLAUDE.md` in place — only change sections where the code has actually diverged from the docs
5. Update the `Last updated` date at the bottom to today's date
6. Report a summary of what changed and what was left untouched
