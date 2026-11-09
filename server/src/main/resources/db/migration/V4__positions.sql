CREATE TABLE positions (
 canonical_code text PRIMARY KEY REFERENCES securities(canonical_code),
 quantity integer NOT NULL CHECK (quantity BETWEEN 0 AND 999999999),
 unit_cost numeric(18,6),
 on_ma55_trigger text CHECK (on_ma55_trigger IN ('REVIEW_REDUCTION','REVIEW_EXIT')),
 source text NOT NULL DEFAULT 'MANUAL' CHECK (source = 'MANUAL'),
 confirmed_at timestamptz NOT NULL,
 updated_at timestamptz NOT NULL,
 version bigint NOT NULL CHECK (version > 0),
 CHECK (quantity > 0 OR (unit_cost IS NULL AND on_ma55_trigger IS NULL))
);

CREATE INDEX market_position_reference ON market_snapshots (canonical_code, as_of_date DESC, fetched_at DESC)
 WHERE quality_jsonb->>'reliable' = 'true' AND as_of_date IS NOT NULL;
