-- Migration: add repeat-customer columns to pos_records
-- Run once in the Supabase SQL editor.
-- Both columns are nullable so existing rows and old CSV uploads are unaffected.

ALTER TABLE pos_records
  ADD COLUMN IF NOT EXISTS unique_customers   INTEGER,
  ADD COLUMN IF NOT EXISTS returning_customers INTEGER;
