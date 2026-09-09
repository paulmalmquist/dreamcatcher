-- Run in a DEDICATED state database as the migration owner, not the API role.
-- WORK-CONNECT: managed-postgres. Provision the actual login using company IAM.
-- The gateway login must be a non-owner, non-superuser, NOBYPASSRLS role.
CREATE TABLE IF NOT EXISTS app_records (
  app_id text NOT NULL, user_id text NOT NULL, collection text NOT NULL,
  key text NOT NULL, value text NOT NULL, version integer NOT NULL,
  updated double precision NOT NULL, PRIMARY KEY(app_id,user_id,collection,key)
);
CREATE TABLE IF NOT EXISTS state_requests (
  app_id text NOT NULL, user_id text NOT NULL, idempotency_key text NOT NULL,
  request_digest text NOT NULL, result text NOT NULL, created double precision NOT NULL,
  PRIMARY KEY(app_id,user_id,idempotency_key)
);
ALTER TABLE app_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_records FORCE ROW LEVEL SECURITY;
ALTER TABLE state_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE state_requests FORCE ROW LEVEL SECURITY;
-- Policy creation intentionally fails if already present: review existing policy
-- changes as a migration; do not silently replace it during application startup.
CREATE POLICY app_user_records ON app_records
  USING (app_id=current_setting('dc.app_id',true) AND user_id=current_setting('dc.user_id',true))
  WITH CHECK (app_id=current_setting('dc.app_id',true) AND user_id=current_setting('dc.user_id',true));
CREATE POLICY app_user_requests ON state_requests
  USING (app_id=current_setting('dc.app_id',true) AND user_id=current_setting('dc.user_id',true))
  WITH CHECK (app_id=current_setting('dc.app_id',true) AND user_id=current_setting('dc.user_id',true));
REVOKE ALL ON app_records,state_requests FROM PUBLIC;
-- After provisioning the real gateway login, grant only SELECT, INSERT, UPDATE
-- on these two tables. No DDL, ownership, role administration or direct app access.
-- Table owners/BYPASSRLS credentials must never be DC_STATE_DATABASE_URL.
