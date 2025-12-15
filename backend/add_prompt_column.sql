-- Migration: Add prompt_used column to criterion_scores table
-- Date: 2024-12-14

ALTER TABLE criterion_scores ADD COLUMN prompt_used TEXT;
