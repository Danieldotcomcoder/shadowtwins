-- 0002: explicit operator requeues (retry failed / rerun uncertain) start a fresh retry budget.
-- `attempts` keeps counting every attempt for the audit trail; the retry limit applies to
-- attempts - retry_base.
ALTER TABLE jobs ADD COLUMN retry_base INTEGER NOT NULL DEFAULT 0
