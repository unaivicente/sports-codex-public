CREATE TABLE ontology_versions (
    ontology_version TEXT PRIMARY KEY,
    ontology_id TEXT NOT NULL,
    sport_id TEXT,
    sport_display_name TEXT,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE model_versions (
    model_version TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_kind TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'local',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    promoted_at TEXT
);

CREATE TABLE videos (
    video_id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    local_path TEXT NOT NULL,
    content_type TEXT,
    duration_seconds REAL CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    timebase TEXT NOT NULL DEFAULT 'seconds',
    frame_rate REAL CHECK (frame_rate IS NULL OR frame_rate > 0),
    byte_size INTEGER CHECK (byte_size IS NULL OR byte_size >= 0),
    content_sha256 TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE evidence_records (
    evidence_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    modality TEXT NOT NULL,
    timestamp REAL NOT NULL CHECK (timestamp >= 0),
    evidence_type TEXT NOT NULL,
    value_json TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    source_model_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY (source_model_version) REFERENCES model_versions(model_version)
);

CREATE TABLE predictions (
    prediction_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    timestamp REAL NOT NULL CHECK (timestamp >= 0),
    interval_start REAL NOT NULL CHECK (interval_start >= 0),
    interval_end REAL NOT NULL CHECK (interval_end > interval_start),
    duration_seconds INTEGER NOT NULL DEFAULT 1 CHECK (duration_seconds = 1),
    timebase TEXT NOT NULL DEFAULT 'seconds',
    label TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    model_version TEXT NOT NULL,
    ontology_version TEXT NOT NULL,
    inference_config_json TEXT NOT NULL DEFAULT '{}',
    post_correction_model_agreement REAL CHECK (
        post_correction_model_agreement IS NULL
        OR (post_correction_model_agreement >= 0 AND post_correction_model_agreement <= 1)
    ),
    confidence_delta REAL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY (model_version) REFERENCES model_versions(model_version),
    FOREIGN KEY (ontology_version) REFERENCES ontology_versions(ontology_version)
);

CREATE TABLE prediction_evidence (
    prediction_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (prediction_id, evidence_id),
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id) ON DELETE CASCADE,
    FOREIGN KEY (evidence_id) REFERENCES evidence_records(evidence_id) ON DELETE RESTRICT
);

CREATE TABLE learning_modes (
    learning_mode TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO learning_modes (learning_mode, description)
VALUES
    ('training', 'High-authority correction mode for training-ready feedback.'),
    ('soft', 'Lower-authority correction mode for weak learning signals.');

CREATE TABLE reviewer_roles (
    reviewer_role TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO reviewer_roles (reviewer_role, description)
VALUES
    ('internal', 'Trusted internal reviewer.'),
    ('external', 'External or general reviewer.'),
    ('admin', 'Administrator or expert reviewer.'),
    ('unknown', 'Reviewer role has not been established.');

CREATE TABLE corrections (
    correction_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    interval_start REAL NOT NULL CHECK (interval_start >= 0),
    interval_end REAL NOT NULL CHECK (interval_end > interval_start),
    original_label TEXT,
    corrected_label TEXT,
    correction_type TEXT NOT NULL CHECK (
        correction_type IN ('confirm', 'modify', 'delete', 'add', 'ontology_gap')
    ),
    edit_operation TEXT NOT NULL CHECK (
        edit_operation IN ('none', 'split', 'merge', 'relabel', 'boundary_adjust')
    ),
    learning_mode TEXT NOT NULL CHECK (learning_mode IN ('training', 'soft')),
    reviewer_id TEXT NOT NULL,
    reviewer_role TEXT NOT NULL CHECK (reviewer_role IN ('internal', 'external', 'admin', 'unknown')),
    reviewer_confidence REAL NOT NULL CHECK (reviewer_confidence >= 0 AND reviewer_confidence <= 1),
    trust_weight REAL NOT NULL CHECK (trust_weight >= 0 AND trust_weight <= 1),
    source_prediction_id TEXT,
    source_model_version TEXT NOT NULL,
    ontology_version TEXT NOT NULL,
    evidence_snapshot_json TEXT NOT NULL,
    post_correction_model_agreement REAL CHECK (
        post_correction_model_agreement IS NULL
        OR (post_correction_model_agreement >= 0 AND post_correction_model_agreement <= 1)
    ),
    confidence_delta REAL,
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        review_status IN ('pending', 'accepted', 'rejected', 'needs_review')
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    notes TEXT,
    CHECK (correction_type = 'add' OR source_prediction_id IS NOT NULL),
    CHECK (correction_type != 'ontology_gap' OR trust_weight = 0),
    CHECK (review_status = 'accepted' OR trust_weight = 0),
    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
    FOREIGN KEY (source_prediction_id) REFERENCES predictions(prediction_id),
    FOREIGN KEY (source_model_version) REFERENCES model_versions(model_version),
    FOREIGN KEY (ontology_version) REFERENCES ontology_versions(ontology_version),
    FOREIGN KEY (learning_mode) REFERENCES learning_modes(learning_mode),
    FOREIGN KEY (reviewer_role) REFERENCES reviewer_roles(reviewer_role)
);

CREATE TABLE correction_trust_metadata (
    correction_id TEXT PRIMARY KEY,
    policy_version TEXT NOT NULL,
    validity_status TEXT NOT NULL CHECK (
        validity_status IN ('pending', 'valid', 'invalid', 'needs_review')
    ),
    assigned_trust_weight REAL NOT NULL CHECK (
        assigned_trust_weight >= 0 AND assigned_trust_weight <= 1
    ),
    reviewer_reliability REAL CHECK (
        reviewer_reliability IS NULL
        OR (reviewer_reliability >= 0 AND reviewer_reliability <= 1)
    ),
    consensus_count INTEGER NOT NULL DEFAULT 0 CHECK (consensus_count >= 0),
    contradiction_count INTEGER NOT NULL DEFAULT 0 CHECK (contradiction_count >= 0),
    assignment_reason TEXT NOT NULL,
    signals_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (correction_id) REFERENCES corrections(correction_id) ON DELETE CASCADE
);

CREATE INDEX idx_videos_local_path ON videos(local_path);
CREATE INDEX idx_predictions_video_time ON predictions(video_id, timestamp);
CREATE INDEX idx_predictions_versions ON predictions(model_version, ontology_version);
CREATE INDEX idx_evidence_video_time ON evidence_records(video_id, timestamp);
CREATE INDEX idx_corrections_video_interval ON corrections(video_id, interval_start, interval_end);
CREATE INDEX idx_corrections_learning_review ON corrections(learning_mode, reviewer_role, review_status);
CREATE INDEX idx_correction_trust_status ON correction_trust_metadata(validity_status, assigned_trust_weight);
