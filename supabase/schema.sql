-- Run in Supabase SQL editor before deploying with database storage.
-- Each reviewer gets a unique row per poem: review_id = <poem_id>__<reviewer_name>

create table if not exists reviewed_annotations (
  review_id text primary key,
  poem_id text not null,
  language text not null,
  title text,
  review_status text not null,
  reviewer_id text not null,
  reviewer_confidence text,
  reviewed_at timestamptz not null,
  payload jsonb not null
);

create index if not exists idx_reviewed_annotations_poem_id
  on reviewed_annotations (poem_id);

create index if not exists idx_reviewed_annotations_reviewer_id
  on reviewed_annotations (reviewer_id);

create table if not exists review_escalations (
  poem_id text primary key,
  title text,
  language text not null,
  escalated_at timestamptz not null,
  escalated_by text not null,
  agreement text,
  reviewers jsonb,
  status text not null default 'pending_senior_review',
  senior_decision text,
  senior_comment text,
  resolved_at timestamptz,
  resolved_by text
);

create table if not exists review_audit_log (
  id bigint generated always as identity primary key,
  event text not null,
  review_id text,
  poem_id text not null,
  language text not null,
  reviewer_id text not null,
  decision text not null,
  reviewer_confidence text,
  reviewed_at timestamptz not null,
  output_file text
);
