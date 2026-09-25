-- 0001: initial schema. Append-only history: later changes add new numbered files.

CREATE TABLE packs (
    pack_id        TEXT PRIMARY KEY,
    benchmark_id   TEXT NOT NULL,
    split          TEXT NOT NULL,
    ranked         INTEGER NOT NULL,
    pack_hash      TEXT NOT NULL,
    policy_hash    TEXT,
    versions_json  TEXT NOT NULL,
    manifest_json  TEXT NOT NULL,
    loaded_at      TEXT NOT NULL
);

CREATE TABLE instances (
    instance_id    TEXT PRIMARY KEY,
    benchmark_id   TEXT NOT NULL,
    pack_id        TEXT NOT NULL REFERENCES packs(pack_id),
    tier           TEXT NOT NULL,
    ord            INTEGER NOT NULL,
    content_hash   TEXT NOT NULL,
    tokens_max     INTEGER,
    instance_json  TEXT NOT NULL
);
CREATE INDEX instances_pack ON instances(pack_id, ord);

CREATE TABLE certificates (
    instance_id      TEXT PRIMARY KEY REFERENCES instances(instance_id),
    core_hash        TEXT NOT NULL,
    max_objective    INTEGER NOT NULL,
    verified         INTEGER NOT NULL,
    certificate_json TEXT NOT NULL
);

CREATE TABLE catalog_snapshots (
    snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    provider       TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    content_hash   TEXT NOT NULL,
    model_count    INTEGER NOT NULL,
    data_json      TEXT NOT NULL
);

CREATE TABLE endpoint_snapshots (
    snapshot_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    provider       TEXT NOT NULL,
    model_id       TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    data_json      TEXT NOT NULL
);
CREATE INDEX endpoint_snapshots_model ON endpoint_snapshots(provider, model_id, snapshot_id);

CREATE TABLE prefs (
    key            TEXT PRIMARY KEY,
    value_json     TEXT NOT NULL
);

CREATE TABLE runs (
    run_id               TEXT PRIMARY KEY,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    completed_at         TEXT,
    provider             TEXT NOT NULL,
    model_id             TEXT NOT NULL,
    endpoint             TEXT,
    profile_id           TEXT NOT NULL,
    profile_json         TEXT NOT NULL,
    mode                 TEXT NOT NULL,
    track                TEXT NOT NULL,
    pack_id              TEXT NOT NULL REFERENCES packs(pack_id),
    pack_hash            TEXT NOT NULL,
    repetitions          INTEGER NOT NULL,
    ranked               INTEGER NOT NULL,
    ranked_reasons_json  TEXT NOT NULL,
    is_mock              INTEGER NOT NULL,
    suite_version        TEXT NOT NULL,
    versions_json        TEXT NOT NULL,
    request_template_json TEXT NOT NULL,
    fingerprint          TEXT NOT NULL,
    catalog_snapshot_id  INTEGER,
    model_meta_json      TEXT NOT NULL,
    state                TEXT NOT NULL,
    state_reason         TEXT,
    spend_limit_usd      REAL NOT NULL,
    concurrency          INTEGER NOT NULL,
    allow_unknown_pricing INTEGER NOT NULL,
    pricing_json         TEXT NOT NULL,
    pricing_known        INTEGER NOT NULL,
    spent_usd            REAL NOT NULL DEFAULT 0,
    reserved_usd         REAL NOT NULL DEFAULT 0,
    note                 TEXT
);
CREATE INDEX runs_model ON runs(model_id, created_at);

CREATE TABLE jobs (
    job_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL REFERENCES runs(run_id),
    instance_id      TEXT NOT NULL REFERENCES instances(instance_id),
    tier             TEXT NOT NULL,
    repetition       INTEGER NOT NULL,
    ord              INTEGER NOT NULL,
    state            TEXT NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    not_before       TEXT,
    lease_owner      TEXT,
    lease_expires_at TEXT,
    reserved_usd     REAL NOT NULL DEFAULT 0,
    last_error       TEXT,
    evaluation_id    INTEGER,
    updated_at       TEXT NOT NULL,
    UNIQUE (run_id, instance_id, repetition)
);
CREATE INDEX jobs_run_state ON jobs(run_id, state, ord);
CREATE INDEX jobs_lease ON jobs(state, lease_expires_at);

CREATE TABLE attempts (
    attempt_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              INTEGER NOT NULL REFERENCES jobs(job_id),
    run_id              TEXT NOT NULL,
    number              INTEGER NOT NULL,
    state               TEXT NOT NULL,     -- prepared | sent | response | failed | ambiguous | abandoned
    worker_id           TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    sent_at             TEXT,
    finished_at         TEXT,
    request_json        TEXT NOT NULL,
    prompt_hash         TEXT NOT NULL,
    reservation_usd     REAL NOT NULL DEFAULT 0,
    http_status         INTEGER,
    error_category      TEXT,
    error_message       TEXT,
    retryable           INTEGER,
    generation_id       TEXT,
    provider_name       TEXT,
    response_model      TEXT,
    finish_reason       TEXT,
    native_finish_reason TEXT,
    content             TEXT,
    refusal             TEXT,
    reasoning_chars     INTEGER,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    reasoning_tokens    INTEGER,
    cost_usd            REAL,
    cost_source         TEXT,              -- reported | estimated | reserved_uncertain | none
    latency_ms          REAL,
    response_json       TEXT,
    rerun_of_attempt    INTEGER
);
CREATE INDEX attempts_job ON attempts(job_id, number);

CREATE TABLE evaluations (
    evaluation_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id            INTEGER NOT NULL REFERENCES jobs(job_id),
    attempt_id        INTEGER NOT NULL REFERENCES attempts(attempt_id),
    run_id            TEXT NOT NULL,
    instance_id       TEXT NOT NULL,
    valid             INTEGER NOT NULL,
    category          TEXT,
    score             REAL NOT NULL,
    raw_objective     INTEGER,
    max_objective     INTEGER NOT NULL,
    evaluator_version TEXT NOT NULL,
    certificate_hash  TEXT NOT NULL,
    envelope_json     TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX evaluations_run ON evaluations(run_id);

CREATE TABLE events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    type         TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX events_run ON events(run_id, event_id);

CREATE TABLE workers (
    worker_id    TEXT PRIMARY KEY,
    pid          INTEGER NOT NULL,
    started_at   TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    state        TEXT NOT NULL
);

CREATE TABLE practice_attempts (
    practice_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id     TEXT NOT NULL REFERENCES instances(instance_id),
    created_at      TEXT NOT NULL,
    edit_json       TEXT NOT NULL,
    valid           INTEGER NOT NULL,
    score           REAL NOT NULL
);
