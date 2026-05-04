-- migrations/2026-05-04-competitor-prefs.sql
-- Adds per-business competitor preferences and a preview-result cache.
-- competitor_prefs_mode='auto' preserves today's pipeline behaviour.

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS competitor_prefs_mode TEXT NOT NULL DEFAULT 'auto'
    CHECK (competitor_prefs_mode IN ('auto', 'custom')),
  ADD COLUMN IF NOT EXISTS competitor_prefs JSONB,
  ADD COLUMN IF NOT EXISTS competitor_prefs_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_businesses_prefs_mode
  ON businesses(competitor_prefs_mode);

CREATE TABLE IF NOT EXISTS competitor_preview_cache (
  place_id TEXT NOT NULL,
  radius_m INT NOT NULL,
  payload JSONB NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (place_id, radius_m)
);

CREATE INDEX IF NOT EXISTS idx_competitor_preview_cache_fetched_at
  ON competitor_preview_cache(fetched_at);
