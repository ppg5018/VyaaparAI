-- =============================================================================
-- Migration: 2026-05-03 — pos_records.product_name
--
-- Petpooja / DotPe / Tally exports include an ItemName column that we
-- previously dropped because the matcher only had product_category. This
-- adds an optional product_name column so per-item rollups can preserve the
-- actual item identity, and `top_product` reports a real product instead of
-- a category. Nullable so existing rows + CSVs without item names continue
-- to work.
-- =============================================================================
BEGIN;

ALTER TABLE pos_records
  ADD COLUMN IF NOT EXISTS product_name TEXT;

COMMIT;

-- =============================================================================
-- ROLLBACK
-- =============================================================================
-- BEGIN;
-- ALTER TABLE pos_records DROP COLUMN IF EXISTS product_name;
-- COMMIT;
