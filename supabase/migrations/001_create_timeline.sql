-- Base Ball Bear timeline events table
CREATE TABLE IF NOT EXISTS timeline_events (
  id              INTEGER PRIMARY KEY,
  date            TEXT NOT NULL,
  date_precision  TEXT NOT NULL DEFAULT 'day',
  type            TEXT NOT NULL DEFAULT 'live',
  importance      TEXT NOT NULL DEFAULT 'normal',
  title           TEXT,
  description     TEXT,
  venue           TEXT,
  city            TEXT,
  tour            TEXT,
  source_url      TEXT,
  source_label    TEXT,
  external_links  JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common filter/sort patterns
CREATE INDEX IF NOT EXISTS idx_tl_date   ON timeline_events(date);
CREATE INDEX IF NOT EXISTS idx_tl_type   ON timeline_events(type);
CREATE INDEX IF NOT EXISTS idx_tl_tour   ON timeline_events(tour);
CREATE INDEX IF NOT EXISTS idx_tl_city   ON timeline_events(city);

-- Enable Row Level Security
ALTER TABLE timeline_events ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read (GitHub Pages static frontend needs this)
CREATE POLICY "public_read" ON timeline_events
  FOR SELECT USING (true);

-- updated_at auto-update trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tl_updated_at
  BEFORE UPDATE ON timeline_events
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
