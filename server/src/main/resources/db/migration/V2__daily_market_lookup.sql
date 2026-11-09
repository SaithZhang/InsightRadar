ALTER TABLE market_snapshots ADD COLUMN requested_code text;
CREATE INDEX market_snapshot_fetch_day ON market_snapshots (provider, fetched_at DESC);
