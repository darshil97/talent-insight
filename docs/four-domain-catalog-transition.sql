-- Run only after the separately approved `python -m app.seed` has upserted
-- the four-domain fixture into the shared Neon catalog. Review the read-only
-- counts and IDs first. This file is never run by startup or tests.
BEGIN;
SET LOCAL statement_timeout = '10s';

-- Refuse an unexpected catalog, including another job added after review.
DO $$
BEGIN
  IF (SELECT array_agg(id ORDER BY id) FROM talent_insight.jobs)
     IS DISTINCT FROM ARRAY[
       'demo_ai', 'demo_backend', 'demo_ds', 'demo_hr_ops',
       'demo_marketing_ops', 'demo_mle'
     ]::varchar[] THEN
    RAISE EXCEPTION 'Unexpected job IDs; inspect the catalog before retirement';
  END IF;
END $$;

-- Their requirements and memberships cascade from the two exact job IDs.
DELETE FROM talent_insight.jobs
WHERE id IN ('demo_ai', 'demo_mle');

-- Remove only the six superseded profiles, and only if no job still uses them.
DELETE FROM talent_insight.demo_candidates AS candidate
WHERE candidate.id IN (
  'demo_ai_elena', 'demo_ai_kai', 'demo_ai_rowan',
  'demo_mle_samir', 'demo_mle_leah', 'demo_mle_noah'
)
AND NOT EXISTS (
  SELECT 1 FROM talent_insight.job_candidates AS member
  WHERE member.candidate_id = candidate.id
);

-- Roll back if the intended complete state was not reached.
DO $$
BEGIN
  IF (SELECT array_agg(id ORDER BY id) FROM talent_insight.jobs)
     IS DISTINCT FROM ARRAY[
       'demo_backend', 'demo_ds', 'demo_hr_ops', 'demo_marketing_ops'
     ]::varchar[]
     OR (SELECT count(*) FROM talent_insight.job_requirements) <> 24
     OR (SELECT count(*) FROM talent_insight.demo_candidates) <> 12
     OR (SELECT count(*) FROM talent_insight.job_candidates) <> 13
  THEN
    RAISE EXCEPTION 'Unexpected catalog counts after retirement';
  END IF;
END $$;

COMMIT;
