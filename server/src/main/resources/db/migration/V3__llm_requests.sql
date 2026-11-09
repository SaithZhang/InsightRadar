CREATE TABLE llm_requests (
 id uuid PRIMARY KEY,
 cache_key text NOT NULL,
 requested_at timestamptz NOT NULL DEFAULT now(),
 reserved_usd numeric(10,2) NOT NULL CHECK (reserved_usd > 0),
 result_jsonb jsonb
);
CREATE INDEX llm_cached_results ON llm_requests (cache_key, requested_at DESC) WHERE result_jsonb IS NOT NULL;
CREATE INDEX llm_monthly_reservations ON llm_requests (requested_at);
