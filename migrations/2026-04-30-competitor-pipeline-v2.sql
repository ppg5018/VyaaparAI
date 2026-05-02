-- =============================================================================
-- Competitor pipeline v2 — embeddings + similarity-search schema
-- Run date target: 2026-04-30
-- Owner: Pratham
--
-- This migration is PURELY ADDITIVE. It does not drop or alter any existing
-- tables/columns. The old `competitor_score` column on `health_scores` is
-- left untouched (currently stubbed to 65 in code; the new pipeline will
-- write real scores back into that same column).
--
-- Apply with:
--   psql "$SUPABASE_DB_URL" -f migrations/2026-04-30-competitor-pipeline-v2.sql
-- or paste into Supabase Dashboard → SQL Editor → Run.
--
-- Rollback (if needed) at the bottom.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. pgvector extension — required for vector(N) column type and ivfflat index
-- -----------------------------------------------------------------------------
-- Supabase enables this on most plans. Safe to re-run.
CREATE EXTENSION IF NOT EXISTS vector;


-- -----------------------------------------------------------------------------
-- 2. review_embeddings — content-keyed cache of vectorised review text
-- -----------------------------------------------------------------------------
-- One row per embedded unit. Two unit types coexist:
--   (a) per-review     → review_id IS NOT NULL, is_centroid = false
--   (b) per-business   → review_id IS NULL,     is_centroid = true
--                        (centroid = embedding of concatenated review text)
--
-- text_hash lets the pipeline skip re-embedding identical text. If a review
-- hasn't changed since last sync we look up by hash and reuse the vector.
--
-- vector(1024) matches Cohere `embed-multilingual-v3` output dimension.
-- If you swap providers, change the dim AND the index lists count.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_embeddings (
  id           bigserial   PRIMARY KEY,
  place_id     text        NOT NULL,
  review_id    text,                                -- NULL for centroid rows
  is_centroid  boolean     NOT NULL DEFAULT false,
  embedding    vector(1024) NOT NULL,
  text_hash    text        NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT review_embeddings_unit_unique
    UNIQUE (place_id, review_id, is_centroid),
  CONSTRAINT review_embeddings_centroid_shape
    CHECK ((is_centroid AND review_id IS NULL)
        OR (NOT is_centroid AND review_id IS NOT NULL))
);

-- ivfflat index on cosine distance for the similarity search hot path.
-- `lists = 100` is the sweet spot for ~10k–100k vectors — adjust upward if
-- the table grows past 100k rows.
-- NOTE: ivfflat requires data before being effective; the index is created
-- empty here and pgvector populates it on insert. For best query speed run
-- `REINDEX INDEX review_embeddings_ivfflat;` once you have ~5k+ rows.
CREATE INDEX IF NOT EXISTS review_embeddings_ivfflat
  ON review_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Fast lookup by place_id (used to fetch all vectors for a business at once).
CREATE INDEX IF NOT EXISTS review_embeddings_place_idx
  ON review_embeddings (place_id);

-- Fast lookup by text_hash (used to skip re-embedding unchanged review text).
CREATE INDEX IF NOT EXISTS review_embeddings_text_hash_idx
  ON review_embeddings (text_hash);


-- -----------------------------------------------------------------------------
-- 3. competitor_matches — relationship cache, refreshed weekly per business
-- -----------------------------------------------------------------------------
-- Stores the matched competitor list per user-owned business so we don't
-- re-run Nearby Search + similarity scoring on every /generate-report.
--
-- Refresh policy is enforced in code, not at the DB layer:
--   - On /generate-report, look up rows where matched_at > now() - 7 days.
--   - If empty/stale, re-run the matcher and upsert.
--
-- ON DELETE CASCADE on business_id means deleting a business automatically
-- cleans up its match cache.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS competitor_matches (
  id              bigserial   PRIMARY KEY,
  business_id     uuid        NOT NULL
                              REFERENCES businesses(id) ON DELETE CASCADE,
  competitor_pid  text        NOT NULL,
  competitor_name text        NOT NULL,
  rating          numeric,
  review_count    integer,
  similarity      numeric     NOT NULL,           -- cosine [0..1]
  sub_category    text,                           -- Haiku tag (footwear/etc.)
  matched_at      timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT competitor_matches_unique
    UNIQUE (business_id, competitor_pid),
  CONSTRAINT competitor_matches_similarity_range
    CHECK (similarity >= 0 AND similarity <= 1)
);

-- Hot path: "give me competitors for business X, freshest first".
CREATE INDEX IF NOT EXISTS competitor_matches_business_idx
  ON competitor_matches (business_id, matched_at DESC);

-- Useful for cache-staleness sweeps.
CREATE INDEX IF NOT EXISTS competitor_matches_matched_at_idx
  ON competitor_matches (matched_at);


COMMIT;


-- =============================================================================
-- ROLLBACK (run only if you need to undo this migration)
-- =============================================================================
-- BEGIN;
--   DROP TABLE IF EXISTS competitor_matches;
--   DROP TABLE IF EXISTS review_embeddings;
--   -- DROP EXTENSION vector;        -- only if no other table uses it
-- COMMIT;
