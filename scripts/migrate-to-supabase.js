/**
 * Migrate timeline.json → Supabase
 *
 * Usage:
 *   $env:SUPABASE_URL      = "https://<project>.supabase.co"
 *   $env:SUPABASE_SERVICE_KEY = "<service_role_key>"
 *   node scripts/migrate-to-supabase.js
 *
 * Requires: npm install @supabase/supabase-js
 */

const fs = require("fs");
const path = require("path");
const { createClient } = require("@supabase/supabase-js");

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY;

if (!SUPABASE_URL || !SUPABASE_KEY) {
  console.error(
    "Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set as environment variables."
  );
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

const dataPath = path.join(__dirname, "..", "docs", "data", "timeline.json");
const events = JSON.parse(fs.readFileSync(dataPath, "utf8"));

// Normalize: ensure external_links is always an array
const rows = events.map((e) => ({
  id: e.id,
  date: e.date,
  date_precision: e.date_precision ?? "day",
  type: e.type ?? "live",
  importance: e.importance ?? "normal",
  title: e.title ?? null,
  description: e.description ?? null,
  venue: e.venue ?? null,
  city: e.city ?? null,
  tour: e.tour ?? null,
  source_url: e.source_url ?? null,
  source_label: e.source_label ?? null,
  external_links: Array.isArray(e.external_links) ? e.external_links : [],
}));

const BATCH = 100;

async function main() {
  console.log(`Migrating ${rows.length} events to Supabase...`);
  let inserted = 0;
  for (let i = 0; i < rows.length; i += BATCH) {
    const batch = rows.slice(i, i + BATCH);
    const { error } = await supabase
      .from("timeline_events")
      .upsert(batch, { onConflict: "id" });
    if (error) {
      console.error(`Batch ${i}–${i + BATCH} failed:`, error.message);
      process.exit(1);
    }
    inserted += batch.length;
    process.stdout.write(`\r  ${inserted}/${rows.length}`);
  }
  console.log("\nDone.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
