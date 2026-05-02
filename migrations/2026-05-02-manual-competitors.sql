-- =============================================================================
-- Migration: 2026-05-02 — manual competitors
--
-- Adds `is_manual` to competitor_matches so users can pin their own competitors
-- alongside auto-discovered ones. Manual rows bypass the COMPETITOR_MATCH_TTL_DAYS
-- expiry and are not wiped by the auto-discovery cache rebuild.
-- =============================================================================
BEGIN;

ALTER TABLE competitor_matches
  ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE;

-- Hot path: "give me the manual rows for business X".
CREATE INDEX IF NOT EXISTS competitor_matches_manual_idx
  ON competitor_matches (business_id, is_manual);

COMMIT;

-- =============================================================================
-- ROLLBACK
-- =============================================================================
-- BEGIN;
-- DROP INDEX IF EXISTS competitor_matches_manual_idx;
-- ALTER TABLE competitor_matches DROP COLUMN IF EXISTS is_manual;
-- COMMIT;
