-- Additive migration: existing uploads and immutable source records are preserved.
CREATE TABLE IF NOT EXISTS app_lifecycle(app_id TEXT PRIMARY KEY REFERENCES apps(id), payload TEXT NOT NULL, revision INTEGER NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS job_lease_limits(job_id TEXT PRIMARY KEY REFERENCES platform_jobs(id), deadline REAL NOT NULL);
CREATE TABLE IF NOT EXISTS release_assurance(submission_id TEXT PRIMARY KEY REFERENCES submissions(id), image TEXT NOT NULL, observed REAL NOT NULL, expires REAL NOT NULL, passed INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS analytical_reviews(submission_id TEXT PRIMARY KEY REFERENCES submissions(id), image TEXT NOT NULL, reviewer TEXT NOT NULL, evidence_uri TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS app_query_windows(app_id TEXT NOT NULL, window_start INTEGER NOT NULL, requests INTEGER NOT NULL, PRIMARY KEY(app_id,window_start));
CREATE TABLE IF NOT EXISTS query_cadence(app_id TEXT NOT NULL,user_id TEXT NOT NULL,reference TEXT NOT NULL,last_started REAL NOT NULL,PRIMARY KEY(app_id,user_id,reference));
