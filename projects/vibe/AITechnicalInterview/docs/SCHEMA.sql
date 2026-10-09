-- PostgreSQL schema for AI Technical Interview Platform
-- Generated from SQLAlchemy models; use alembic for migrations in production.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE employers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    resume_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE interview_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL REFERENCES employers(id),
    name VARCHAR(255) NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    job_description_text TEXT,
    format_selection_mode VARCHAR(32) DEFAULT 'auto',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE template_competencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES interview_templates(id) ON DELETE CASCADE,
    skill VARCHAR(128) NOT NULL,
    level VARCHAR(64) NOT NULL,
    weight INTEGER DEFAULT 10,
    source VARCHAR(32) DEFAULT 'manual'
);

CREATE TABLE template_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID UNIQUE NOT NULL REFERENCES interview_templates(id) ON DELETE CASCADE,
    ai_behavior JSONB DEFAULT '{}',
    scoring_rules JSONB DEFAULT '{}',
    evaluation_priorities JSONB DEFAULT '[]',
    interview_mode_settings JSONB DEFAULT '{}'
);

CREATE TABLE template_allowed_formats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES interview_templates(id) ON DELETE CASCADE,
    format_name VARCHAR(64) NOT NULL
);

CREATE TABLE interviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL REFERENCES employers(id),
    candidate_id UUID REFERENCES candidates(id),
    template_id UUID REFERENCES interview_templates(id),
    status VARCHAR(32) DEFAULT 'created',
    access_token VARCHAR(64) UNIQUE NOT NULL,
    job_description_text TEXT,
    resume_text TEXT,
    format_selection_mode VARCHAR(32) DEFAULT 'auto',
    allowed_formats JSONB DEFAULT '[]',
    selected_format VARCHAR(64),
    duration_minutes INTEGER DEFAULT 60,
    editor_language VARCHAR(32) DEFAULT 'python',
    editor_content TEXT DEFAULT '',
    editor_version INTEGER DEFAULT 0,
    editor_seq INTEGER DEFAULT 0,
    ai_settings JSONB DEFAULT '{}',
    media_camera BOOLEAN DEFAULT FALSE,
    media_microphone BOOLEAN DEFAULT FALSE,
    media_screenshare BOOLEAN DEFAULT FALSE,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE competencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    skill VARCHAR(128) NOT NULL,
    level VARCHAR(64) NOT NULL,
    weight INTEGER DEFAULT 10,
    source VARCHAR(32) DEFAULT 'inferred',
    coverage_score FLOAT DEFAULT 0,
    confirmed BOOLEAN DEFAULT FALSE
);

CREATE TABLE interview_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB DEFAULT '{}',
    offset_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    speaker VARCHAR(32) NOT NULL,
    text TEXT NOT NULL,
    offset_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID UNIQUE NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    competency_scores JSONB DEFAULT '{}',
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    communication_assessment JSONB DEFAULT '{}',
    code_quality_assessment JSONB DEFAULT '{}',
    honesty_signals JSONB DEFAULT '{}',
    confidence_level FLOAT DEFAULT 0,
    recommendation VARCHAR(32) NOT NULL,
    final_summary TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE recordings_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    stream_type VARCHAR(32) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    chunk_count INTEGER DEFAULT 0,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE code_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    language VARCHAR(32),
    trigger VARCHAR(64),
    offset_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE code_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    actor VARCHAR(32) NOT NULL,
    action VARCHAR(64) NOT NULL,
    range_data JSONB DEFAULT '{}',
    text_before TEXT,
    text_after TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE editor_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    actor VARCHAR(32) NOT NULL,
    action VARCHAR(64) NOT NULL,
    lines VARCHAR(32),
    payload JSONB DEFAULT '{}'
);

CREATE INDEX idx_interviews_token ON interviews(access_token);
CREATE INDEX idx_interviews_employer ON interviews(employer_id);
CREATE INDEX idx_code_ops_interview_seq ON code_operations(interview_id, seq);
