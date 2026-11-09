CREATE TABLE securities (
 canonical_code text PRIMARY KEY, code text NOT NULL, name text NOT NULL, exchange text NOT NULL,
 type text NOT NULL, list_status text NOT NULL, provider text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(), identity_jsonb jsonb NOT NULL
);
CREATE TABLE market_snapshots (
 id uuid PRIMARY KEY, canonical_code text NOT NULL, as_of_date date, provider text NOT NULL,
 fetched_at timestamptz NOT NULL, raw_jsonb jsonb NOT NULL, qfq_source_jsonb jsonb NOT NULL,
 normalized_jsonb jsonb NOT NULL, calendar_jsonb jsonb NOT NULL, quality_jsonb jsonb NOT NULL,
 source_jsonb jsonb NOT NULL, input_sha256 text NOT NULL
);
CREATE TABLE disclosures (
 doc_id text PRIMARY KEY, canonical_code text, title text NOT NULL, published_at timestamptz,
 official_url text NOT NULL, pdf_path text, pdf_sha256 text, pages_jsonb jsonb NOT NULL,
 fetch_status text NOT NULL, metadata_jsonb jsonb NOT NULL
);
CREATE TABLE analysis_runs (
 run_id uuid PRIMARY KEY, requested_code text NOT NULL, canonical_code text, created_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','COMPLETED','PARTIAL','FAILED')), stage text NOT NULL,
 market_snapshot_id uuid REFERENCES market_snapshots(id), report_jsonb jsonb, tech_rule_version text NOT NULL,
 prompt_version text, report_hash text, error_jsonb jsonb
);
CREATE INDEX analysis_history ON analysis_runs (requested_code, created_at DESC);
CREATE TABLE plan_evaluations (
 id uuid PRIMARY KEY, plan_id uuid NOT NULL, base_run_id uuid NOT NULL REFERENCES analysis_runs(run_id),
 target_date date NOT NULL, evaluated_at timestamptz NOT NULL, status text NOT NULL,
 input_sha256 text NOT NULL, record_jsonb jsonb NOT NULL,
 UNIQUE(plan_id,target_date,input_sha256)
);
CREATE INDEX evaluation_history ON plan_evaluations(base_run_id,evaluated_at);
CREATE FUNCTION reject_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN RAISE EXCEPTION 'immutable evidence: append a new record'; END;
$$;
CREATE TRIGGER immutable_market BEFORE UPDATE OR DELETE ON market_snapshots FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation();
CREATE TRIGGER immutable_disclosure BEFORE UPDATE OR DELETE ON disclosures FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation();
CREATE TRIGGER immutable_evaluation BEFORE UPDATE OR DELETE ON plan_evaluations FOR EACH ROW EXECUTE FUNCTION reject_evidence_mutation();
CREATE FUNCTION protect_terminal_run() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
  IF OLD.status IN ('COMPLETED','PARTIAL','FAILED') OR TG_OP='DELETE' THEN RAISE EXCEPTION 'terminal analysis is immutable'; END IF;
  RETURN NEW;
 END;
$$;
CREATE TRIGGER immutable_terminal BEFORE UPDATE OR DELETE ON analysis_runs FOR EACH ROW EXECUTE FUNCTION protect_terminal_run();
