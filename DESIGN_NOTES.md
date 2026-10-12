WeatherForecastAnalyzer — Design Notes

This document captures the why behind the project's architecture and schema
decisions — context that's too detailed for the README but useful for anyone
(including future-me, or a tool reviewing this code) picking the project back
up.

Core Hypothesis

Forecasts are predictions, not facts — a forecast made for 3pm today isn't the
actual temperature, it's an estimate that should get more accurate the closer
the prediction is made to the actual event. This project captures forecasts
repeatedly over time in order to measure: how does forecast accuracy change as
lead time (the gap between when a forecast was made and the time it's
predicting) shrinks?

Background: Why This Pattern Is Familiar

This project deliberately mirrors a data pattern from prior production work (a
sales/marketing reporting pipeline): a value that isn't final at the moment
it's first observed, but gets more accurate/complete as time passes (e.g.
attribution data trickling in after a conversion date). That system tracked
both the date being reported on and the date the report was run, so historical
values were never overwritten — every observation was preserved as its own row,
segmented by report date rather than event date.

This project reproduces the same shape of problem in a different domain:

Then: a "sale" attributed to a given day, re-estimated in every subsequent
report as attribution data arrived late. Now: a forecast for a given future
moment, re-estimated every time a new pull is made closer to that moment.

Structurally identical. Same schema pattern, same eventual SQL (window
functions partitioning by the target and ordering by report time to get "latest
known value"), different subject matter.

Schema Design

Primary key: RequestedLatitude | RequestedLongitude | ResolvedLatitude |
ResolvedLongitude | ReportDateTime | ForecastDateTime

- RequestedLatitude / RequestedLongitude — the coordinates actually sent to the API for this row. Replaces the earlier single Location field, which assumed one location meant one point. That assumption doesn't hold: a single city can be pinned to multiple query points (denser sampling of forecast tiles within the same city), so City is no longer sufficient to disambiguate a row on its own — see City under Metadata Fields below. RequestedLatitude/RequestedLongitude is what carries that disambiguating role now.
  - Eventually Source will probably need to join the key too (once a second data source is added, the same requested point/forecast moment could be reported by more than one provider). Not a concern yet with a single source in use — noting it here so it isn't forgotten later, not addressing it now.
- ResolvedLatitude / ResolvedLongitude — the coordinates the API actually resolved the forecast to (returned in the response — the API snaps a requested point to its nearest grid tile/station, which is not guaranteed to be the exact point requested). Added to the key alongside RequestedLatitude/RequestedLongitude so downstream analysis can measure forecast accuracy against the tile the data really came from, rather than assuming resolution == the point requested. This also lets later analysis notice when multiple nearby Requested points collapse onto the same Resolved tile, or the reverse.
- ReportDateTime — when this specific forecast was pulled, expressed as the intended cron slot (e.g. 00:00/04:00/08:00/...), not the literal wall-clock moment a request happened to complete. The API does not provide a generation timestamp (confirmed — see Known Gaps), so the original plan of keying off the API's own generation time isn't available. Computed once per pipeline run in Pipeline.py, before the location loop starts and before any retries — every location and every retry attempt in that run reads the same value. This recovers the same retry-safety property the API-timestamp approach was meant to provide: a failed request retried within the same scheduled slot collides on the same ReportDateTime instead of producing a second row for what's actually the same intended observation. The value is computed in Pipeline.py, but attaching it to rows still happens in Transform, alongside Source/Locale, via the metadata dict (see Metadata Fields / Layer Responsibilities below) — kept there so all metadata enrichment stays in one place rather than being split across files.
- ForecastDateTime — the future date/time this forecast row is about (renamed from an earlier Date/Time draft for clarity, since plain Date/Time was ambiguous next to ReportDateTime).

Originally split into separate ForecastDate/ForecastTime columns for
query-ergonomics reasons (rolling up by date alone or time alone without
parsing). Revisited and collapsed back into a single ForecastDateTime column:
BigQuery's native datetime functions (DATE(), EXTRACT(HOUR FROM ...), etc.)
roll up by day or by hour directly off a combined datetime column with no
parsing cost, so the split bought nothing once the raw layer is known to land
in BigQuery specifically. A combined field also mirrors ReportDateTime's shape,
which is itself a datetime.

No timestamp rounding on ForecastDateTime — captured at whatever precision the
API's hourly grid provides. ReportDateTime is the one deliberate exception:
it's intentionally snapped to the scheduled cron slot rather than raw pull
precision, specifically for the retry-collision property described above.
Otherwise the pipeline is expected to be lightweight and fast, so this isn't
expected to cause meaningful key bloat or performance issues.

Partitioning & Clustering (Not Yet Decided)

Distinct from the logical primary key above (which just documents what makes a
row unique — order there is narrative, not physical). Partitioning and
clustering are a separate BigQuery physical-layout decision that determines
query performance, and hasn't been made yet.

Leaning toward: partition on DATE(ReportDateTime), cluster with ReportDateTime
leading the clustering key, since "get the latest report" and
time-range-bounded queries are expected to be the dominant access pattern (same
reasoning as the prior sales-attribution pipeline this project mirrors). Not
committing to this yet — TODO: revisit once there's real query traffic/patterns
to design around, rather than guessing upfront.

Metadata Fields

Passed into the transform step as a metadata dict (not just a single scalar),
since more than one pull-level field is expected over time:

- ReportDateTime — see above
- Source — which API/provider the data came from. Anticipates a future where multiple weather data sources are compared against each other.
- Locale — captured for future-proofing (e.g. multi-source, multi-region expansion) even though only a single locale is in use today. Low priority to build real logic around until a second source/locale is actually added — for now it's effectively a constant value on every row.

Descriptive (Non-Key) Location Fields

- City — a human-readable label for a requested point (e.g. "Elk Grove, CA"). No longer part of the primary key: since a city can be pinned to multiple RequestedLatitude/RequestedLongitude points, City is many-to-one against the key and can't uniquely identify a row on its own. Kept as a descriptive column for readability and for rolling multiple pinned points up to a common city in downstream queries.
- Elevation — the elevation the API resolved at ResolvedLatitude/ResolvedLongitude. Descriptive, not key — carried alongside the resolved coordinates for context, not disambiguation.

Layer Responsibilities (Raw vs. Transform Separation)

Deliberate separation, modeled on the medallion/staging-vs-marts pattern used
in tools like dbt:

- Extract — pulls raw data from the API only. No transformation logic.
- Transform — field name normalization (API's raw names → project schema, e.g. temperature → Temperature), metadata enrichment (attaching ReportDateTime/Source/Locale), and type enforcement (ensuring numeric fields aren't left as strings, handling nulls). Explicitly no computed/derived fields at this layer (e.g. no lead-time calculation, no accuracy scoring).
- Load — writes the transformed DataFrame into BigQuery via google-cloud-bigquery's load_table_from_dataframe().

Why keep computed fields out of ingestion: coupling extract/transform logic to
a specific analysis (e.g. "hours ahead of forecast") means any new analytical
question later would require re-pulling or backfilling data. Landing raw,
unprocessed values keeps the raw table reusable for whatever questions come up
later. All derived analysis (accuracy by lead time, by time-of-day, by season,
etc.) is intended to happen downstream in BigQuery/dbt SQL, not in Python at
ingestion time. Any future translation/localization logic (if Locale ever
becomes more than a placeholder) would follow the same rule — handled via SQL
downstream, not in the transform step.

Duplicate / Repeat Observations (Not Deduplicated At Ingestion)

A successful pull that returns the same values as the previous pull for a
location is still landed as its own row — the pipeline does not compare against
prior data or skip/collapse repeats at Extract/Transform/Load time. This
follows directly from the append-only principle above: an unchanged forecast is
still a real observation ("we checked again and it hadn't changed yet"), not
noise to filter out. Deciding whether/how to treat repeats as meaningful (e.g.
measuring forecast stability, or collapsing consecutive identical values for
display) is deferred to downstream BigQuery/SQL — e.g. a LAG() window function
partitioned by
RequestedLatitude/RequestedLongitude/ResolvedLatitude/ResolvedLongitude/ForecastDateTime
and ordered by ReportDateTime can identify or collapse runs of identical values
whenever that question actually comes up. Ingestion doesn't need to know or
care.

This also simplifies retry handling: a failed pull (non-200 response) is never
appended to Extract's result list, so it contributes zero row candidates — a
failure followed by a successful retry produces exactly one row, not two. The
only case that could produce a genuine same-generation duplicate is two
separate successful pulls landing before the underlying report has actually
changed; the ReportDateTime cron-slot snap (see Schema Design above) collapses
that case when it's a retry within the same scheduled slot, and any other case
is accepted as legitimate data per this section.

Why the LAG() partition above isn't collapsed to
ResolvedLatitude/ResolvedLongitude alone: it's tempting, since the forecast
values are physically determined by the resolved tile, not the requested point
— so two different cities pinned to the same station would produce
byte-identical hourly values, and partitioning on Resolved-only would surface
that automatically as a side effect of dedup. Rejected anyway, because it
conflates two different questions. "Did this city's forecast change since the
last pull" is a per-pin question — collapsing the partition would mean any city
sharing a station with another pin loses its own city-level view, and you'd
only ever discover station-sharing by accident. "Which cities happen to resolve
to the same physical station" is a separate structural question about the data,
and belongs downstream as its own query (e.g. GROUP BY ResolvedLatitude,
ResolvedLongitude HAVING COUNT(DISTINCT City) > 1), not folded into how repeats
get detected. Keeping City in the row grain also means that query — and the
everyday case of just filtering by city name — stays a string match instead of
forcing an esoteric float comparison. Same "land raw, ask questions later"
philosophy as the rest of this section: station-sharing is a data claim to be
made by querying the warehouse, not a decision to bake into ingestion.

Known Gaps / Things To Verify

- Confirmed: Open-Meteo does not return a generation timestamp in its response. Original plan was to key ReportDateTime off the API's own generation time for retry-safety; resolved instead by snapping ReportDateTime to the scheduled cron slot (see Schema Design above), so retry-safety no longer depends on anything the API provides.
- Resolved: cron-slot rounding is a floor to the top of the hour (Pipeline.py: now.replace(minute=0, second=0, microsecond=0)), and the crontab entry runs at minute 0 of every hour (0 * * * *), so the two now agree — no drift concern from a mismatched schedule/rounding granularity.
- Confirm API auth requirements before writing extract.py (most weather APIs require at least a free API key, even without full OAuth).
- Fixed: Extract.get_forecast previously left res unassigned on a non-200 response, so a failed API call raised UnboundLocalError on return res instead of returning None — meaning the documented "a failed pull contributes zero row candidates" behavior didn't actually hold; a single flaky response would crash the entire hourly run rather than being skipped. Fixed by initializing res = None before the status check.
- Fixed: ReportDateTime was typed DATETIME (BigQuery's tz-naive civil type) while Pipeline.py produces it as a tz-aware UTC value (datetime.now(timezone.utc)). Round-tripping through BigQuery meant Load.load() compared a tz-aware in-memory value (incoming_date_time, read straight off the DataFrame before load) against a tz-naive value read back from BigQuery (last_loaded) — raising "Cannot subtract tz-naive and tz-aware datetime-like objects" on every city's second-and-later load. This was silent per city rather than run-crashing because of the fail-soft change above, which made it easy to miss: every city just stopped loading new rows after its first one, logged but not raised. Fixed by changing ReportDateTime to TIMESTAMP in WeatherForecastAnalyzer.json (a real tz-aware BigQuery type) rather than stripping tzinfo in Python, since the value is semantically an absolute UTC instant, not a civil wall-clock reading — same reasoning ForecastDateTime doesn't need (it's built via strptime with no tzinfo, so it was already consistent with its DATETIME column). Required dropping and recreating the forecast table, since BigQuery doesn't support in-place column type changes. ForecastDateTime was changed to TIMESTAMP in the same pass, even though it wasn't implicated in this particular bug (it's never read back into Python for comparison, so no naive/aware mismatch was possible there) — kept it aligned with ReportDateTime because the project's core lead-time calculation (ForecastDateTime - ReportDateTime, see Core Hypothesis above) happens downstream in BigQuery SQL, and BigQuery requires matching types (TIMESTAMP vs TIMESTAMP, not TIMESTAMP vs DATETIME) to diff two datetime columns without an explicit cast at every query site. Transform.py's strptime call still produces a naive datetime for this field; loading a naive value into a TIMESTAMP column is standard BigQuery client behavior — it's interpreted as already being UTC, which matches reality since Extract.py requests the API in UTC.
- Decision: Load.load() was changed from fail-fast to fail-soft per city. Previously, an exception loading any one city's DataFrame into BigQuery (or querying its latest ReportDateTime) re-raised and aborted the whole run, silently skipping every city later in the locations list that cycle. Now each city's block is wrapped individually — a failure is logged (Unable to load city {city}: {e}) and the loop continues to the next city, so one city's BQ/query failure no longer costs other cities their hourly load. Tradeoff accepted deliberately: failures are now easy to miss unless the logs are read, since nothing raises out of a fully-failed run. Revisit if that turns out to matter (e.g. add a summary/alert on partial failure) once there's real log history to judge frequency against.
- Fixed: Porto, Portugal longitude was incorrectly setup, causing data to be pulled for a different area: "Gulf of Asinara, Sardinia", flipped the sign on longitude, and updated BQ table for dates: 2026-08-31 to 2026-10-10 changing only label of field City for 131,544 rows
- Observed: on 2026-10-06 13:00 UTC it appears the resolved longitude changed for the misconfigured Portugal location, changing from 8.625 to 8.6404085, as well as resolved latitude from 41.125 to 41.147305 for Gulf of Asinara, Sardinia
- Fixed: hours were silently missing for whichever city came first in the locations list. pipeline.log showed 152 "api returned: 503" lines through 2026-10-10, ranked by list position: Elk Grove (1st) 94, San Jose (2nd) 24, Los Angeles (3rd) 12, the rest in single digits. Open-Meteo turns away the first requests that arrive exactly at :00, when scheduled jobs everywhere fire at once, and Extract made a single attempt, so the first city lost that hour (Elk Grove was 91 runs behind the best-covered city). Fixed by sending requests through a requests.Session with urllib3 Retry: 5 retries on 429/5xx with exponential backoff and jitter (waits of roughly 0, 4, 8, 16, 32s, so about a minute worst case per city), plus timeout=10 on every request, since requests has no default timeout and a hung connection would otherwise stall the hourly run indefinitely. A request that still fails after the retries is logged and skipped, same as before. Result: from 2026-10-03 until the fix (5 PM PDT 2026-10-10), 30 of 167 hourly runs (18%) were missing at least one city; the first 22 runs after it were all 10/10, with no request exhausting its retries. Retries happen inside urllib3 and aren't logged, so how many 503s were absorbed isn't visible yet (the planned logging module could surface urllib3's DEBUG retry messages).
- Decision: actuals are ERA5T, ERA5's preliminary release (about 5-6 days behind real time). ECMWF replaces it with final ERA5 roughly 2-3 months later, usually with small or no changes. The actuals pipeline does not re-pull already-loaded hours, so raw.actual keeps the preliminary values. Accepted for now; a periodic re-pull of old ranges plus "latest LoadedDateTime wins" in dbt would pick up revisions if they ever matter.
- Observed: forecast and actual values describe different-sized areas. The forecast resolves to squares about 2-3 km wide (resolved points land 1-2 km from the requested pins in the US, about 5 km for Cebu), while era5_seamless uses a 0.1 degree grid (about 10 km; resolved points land 1.6-6.7 km from the US pins and 15 km from Cebu). Part of any measured forecast error is therefore area mismatch rather than forecast skill, most likely where weather changes over short distances (coastline and terrain: Los Angeles, San Jose, Porto, Cebu). Elevations returned by the two APIs match exactly for every pin, so temperature isn't skewed by height differences.
- Observed: ERA5 resolved coordinates carry float32 rounding noise (e.g. 30.300003 for 30.3, -121.399994 for -121.4). Never compare them with =; round to one decimal if grouping by ERA5 square. Requested coordinates are exact (they come from Locations.json).
- Observed: the Gulf of Asinara forecast rows (the pre-fix Porto pin) have no matching actuals, since actuals were only ever pulled for the corrected Porto coordinates, so those rows drop out of any forecast-vs-actual join. Porto's actuals start 2026-08-31 at the correct location, while its forecasts start 2026-10-11 00:00 UTC.
- Observed: ERA5's lag isn't fixed. On 2026-10-10 the archive was filled through 2026-10-05 23:00 UTC (5 days behind); on 2026-10-11 it still ended there (6+ days), so that day's 10:15 run correctly loaded nothing ("nothing new" for every location). No code change needed: unfilled hours come back null and are dropped, so the high-water mark just waits. The dbt freshness threshold for raw.actual is set with this in mind (see dbt Layer).

Future Expansion (Not In Scope For V1)

- Compare multiple weather data sources against each other (accuracy, agreement/disagreement).
- Break down forecast accuracy by time-of-day, season, resolved tile, and location (now that Requested vs. Resolved coordinates are captured separately in the key).
- Correlate accuracy with instrument/equipment metadata (station age, brand, sensor height/type) via dimension tables — moves the project from "pulled some weather data" toward "evaluates forecast reliability across sources and conditions."

Planned Expansion: Actual-Weather Comparison via dbt + BI Tool (Ingest Built 2026-10-10; dbt Staging Built 2026-10-11)

Distinct from the "compare multiple data sources" bullet above (which compares
forecast providers against each other). This is a different comparison:
a single provider's forecast against what actually happened, from the same
provider. It doesn't require a second forecast source to be useful, and it's a
stronger accuracy signal than forecast-vs-forecast convergence, since it checks
predictions against ground truth rather than just watching whether a value
stopped changing.

The ingest half is built: a second raw table, raw.actual, holds observed
weather per location from Open-Meteo's archive endpoint, landed by a parallel
PipelineActual.py that reuses the existing Extract -> Transform -> Load
skeleton. It sits alongside raw.forecast without changing it. Design details
are under "Actuals Ingest" below.

The join/derivation work -- matching a forecast row to the actual observation
for the same RequestedLatitude/RequestedLongitude and hour (ForecastDateTime
= ObservedDateTime; not the resolved coordinates, see "Actuals Ingest"),
computing a per-metric shift (actual minus forecast) and the lead time
(ForecastDateTime - ReportDateTime) -- is intended to live in dbt, staged on
top of the two raw BigQuery tables rather than in Python. This is the concrete
implementation of the "downstream in BigQuery/dbt SQL" principle already
stated under Layer Responsibilities above, not a new architectural direction.
Staging models normalize each raw table; a mart model (something like
fct_forecast_accuracy) does the join and produces the shift/lead-time columns
a BI tool would query directly.

A BI tool (Power BI, Tableau, or Looker Studio -- not yet decided, see below)
would sit on top of that mart, letting the shift be segmented by city, metric,
and time frame (lead-time bucket, hour-of-day, season). Grain of the mart
(long: one row per location/ForecastDateTime/ReportDateTime/metric, vs. wide:
one row per location/ForecastDateTime/ReportDateTime with a delta column per
metric) is also undecided -- pick when the mart is actually built, once real
query/viz patterns are known, same reasoning as the Partitioning & Clustering
section above.

BI tool choice deliberately left open, same status as the partitioning
decision: Looker Studio is the lowest-friction option (free, native BigQuery
connector), Power BI/Tableau are heavier but may be worth it depending on
which roles the finished project is meant to speak to on a resume -- this
project is partly chosen to build hands-on breadth in dbt and a
visualization tool, on top of the original ETL learning goal (see README
Project Inception), so tool choice should factor that in when it's actually
made rather than defaulting to whichever is easiest to wire up.

Actuals Ingest (Built 2026-10-10)

Source: Open-Meteo's archive endpoint with models=era5_seamless pinned
explicitly. ERA5 is a reanalysis: ECMWF reruns a weather model over the past
and constrains it to every available measurement (stations, balloons,
satellites, buoys), so it's the best gridded estimate of what actually
happened. The model has to be pinned because the archive endpoint's default
(best_match) fills the most recent days -- and even hours that haven't
happened yet -- with forecast-model output. Unpinned, the "actuals" would
partly be forecasts and the measured error would shrink toward zero for no
real reason. era5_seamless was chosen over plain era5 for its finer grid
(0.1 degree vs 0.25 degree); both run about 5-6 days behind real time.

Join key: requested coordinates, never resolved. Neither API reads a weather
station; both return values for a grid square, and the resolved coordinates
are that square's center. The forecast and ERA5 use different grids with
different square sizes, so their resolved points essentially never coincide
(e.g. Lakewood Ranch: forecast 27.437/-82.389, ERA5 27.4/-82.4). The only
thing the two tables share is the point that was asked about, so the dbt
join matches RequestedLatitude/RequestedLongitude plus the hour. Resolved
coordinates are still stored on both sides so the distance between the two
squares can be measured later (see Known Gaps).

Schema (ActualSchema.json): the same coordinate, City, Elevation and metric
columns as raw.forecast, with the same names, so the dbt join reads cleanly.
ObservedDateTime is the hour the weather is for. LoadedDateTime is when the
row was loaded, and it is deliberately not part of the key. That's the
difference from ReportDateTime: a forecast issued at 09:00 is a different
fact from one issued at 15:00 for the same hour, so ReportDateTime is part of
the data (and of the key). An observed temperature for a given hour is the
same fact whichever day it's fetched, so LoadedDateTime is only bookkeeping.
It's the exact load time, not snapped to an hour. Model records which ERA5
variant produced the row (ExtractActual.MODEL, so the label can't drift from
what was requested). Metric columns stay REQUIRED; a null reaching BigQuery
fails the load, which is the alarm wanted rather than silently loading gaps.

Incremental load (high-water mark): each run asks BigQuery, per location, for
MAX(ObservedDateTime) at that location's requested coordinates (filtering on
coordinates rather than City, since a label can be wrong -- see the Porto fix
-- and via query parameters rather than string concatenation). It then
requests from that hour's date through today (UTC; the API accepts today,
and a future end_date is a 400), drops rows with nulls, drops rows at or
before the high-water mark, and loads what's left. Consequences:
- No fixed window and no separate backfill mode: an empty table means "start
  at 2026-08-31", so the first run was the backfill (10 locations x 864
  rows, 2026-08-31 00:00 to 2026-10-05 23:00 UTC).
- ERA5's lag is never hardcoded. Hours ERA5 hasn't filled yet come back
  null and are dropped, so the high-water mark only advances to the last
  real hour; if the lag changes, nothing in the code does.
- Days the PC was off heal themselves: the next run's range is simply longer.
  (Forecast gaps can't heal this way -- a forecast that wasn't captured when
  it was issued is gone -- but actuals can always be re-requested.)
- Re-running is safe: a second run immediately after the backfill printed
  "nothing new" for every location.
ObservedDateTime is converted to UTC-aware before comparing with the
high-water mark (BigQuery returns a tz-aware TIMESTAMP; Transform's strptime
produces naive values), avoiding the tz-naive vs tz-aware error described in
Known Gaps.

No drop files for actuals. The forecast pipeline lands raw JSON in drop/
because a forecast can't be fetched again once it's been superseded. ERA5 is
a permanent historical archive, so any missing or suspect range can simply be
pulled again; the drop/archive step would add overhead without protecting
anything.

Code reuse: rather than one generalized pipeline, there are two parallel
pipelines sharing only what's identical, so a change on the actuals side
can't break the hourly forecast job. ExtractActual imports Extract's session
(same retry/timeout behavior) and weather_params (same 12 fields).
Transform.transform_shape is shared: it now stamps every entry of the
metadata dict the caller passes (forecast: report_date_time; actuals:
loaded_date_time and model) and takes the field-translation file as a
required argument (FieldTranslations.json vs ActualFieldTranslations.json),
so it no longer knows anything forecast-specific. Before committing that
change, the old and new transform_shape were run on archived forecast drop
files from three runs (first run, mid-history, latest) and produced identical
DataFrames (pandas assert_frame_equal). LoadActual reuses Load's BigQuery
client and ensure_table; its load() has no one-hour skip rule. Each location
is handled inside its own try/except in PipelineActual, so one location's
failure is logged and the rest still run (same fail-soft tradeoff as
forecast: read pipeline_actual.log). Locations live in Locations.json, read
by both pipelines.

dbt Layer (Started 2026-10-11)

The transform-in-the-warehouse half of the plan above. The dbt project lives
in wfa_dbt/ inside this repo (dbt project names can't contain hyphens or be
"dbt", so the folder isn't just dbt/). It reads the two raw tables and writes
its models to a separate BigQuery dataset, dbt_dev, so raw is never modified
by dbt. Built so far: sources, two staging models, and tests. The
forecast-vs-actual mart is next.

Separate virtualenv (dbt-venv/, gitignored). dbt-bigquery brings its own
version requirements for google-cloud-bigquery, protobuf and friends, and the
pipeline's venv/ pins exact versions in requirements.txt. Installing dbt into
venv/ could quietly upgrade or downgrade a library the hourly cron job
depends on, and the first sign would be a gap in the data. dbt never imports
the pipeline's Python (it only talks to BigQuery), so nothing is lost by
keeping them apart. dbt-venv/ is built on Python 3.11 (Ubuntu 22.04's
default python3 is 3.10, which Google's libraries now warn is past end of
life; 3.11 is installed alongside it). The pipeline venv is still 3.10;
moving it is planned as its own step, since cron runs it every hour. A shell
alias points dbt at dbt-venv/bin/dbt, so no venv activation is needed.

Connection: ~/.dbt/profiles.yml (outside the repo), method oauth, so dbt
uses the same gcloud application-default credentials as the pipelines and
there's no key file to manage or leak. Location US, matching raw (SetupDW.py
created it without a location, which defaults to US; a join across
locations would fail).

Sources (models/staging/_sources.yml): raw.forecast and raw.actual are
declared as sources, and models read them through source() rather than
hardcoded table names, which is what gives dbt the lineage from raw tables
to models. Each has a freshness check (dbt source freshness), which reports
how old the newest row is:
- forecast, on ReportDateTime: warn after 2 hours, error after 6. A
  forecast warning usually means the PC was off.
- actual, on ObservedDateTime (warn after 8 days, error after 10), not
  LoadedDateTime. Runs that find nothing new write nothing, so LoadedDateTime
  can go stale while everything is healthy; what matters is how recent the
  newest observation is, and ERA5 alone keeps that 5-6 days behind (see Known
  Gaps).

Staging (models/staging/stg_forecast.sql, stg_actual.sql): one view per raw
table, same rows, columns renamed to snake_case (ReportDateTime ->
report_date_time). Nothing else: no joins, filters or derived columns, so
staging is a clean 1:1 interface and logic lives in the models built on it.
Views rather than tables because they're just a rename: they cost nothing to
create and always reflect the latest hourly load. Raw keeps its PascalCase
names, since changing them would mean a schema migration on live tables for
no gain once staging exists. models/marts/ is configured to build tables,
for the joined models that get queried repeatedly.

Tests (models/staging/_staging.yml, using the dbt_utils package):
- Grain: the column combination that identifies one row must never repeat.
  stg_forecast: requested lat/lon + report_date_time + forecast_date_time.
  stg_actual: requested lat/lon + observed_date_time. loaded_date_time is
  deliberately left out of the actual grain: if the high-water mark ever
  broke and the same hour loaded twice, the two rows would differ only in
  loaded_date_time, so including it would let exactly that duplicate pass.
- not_null on the timestamps and city in both models.
All 8 passed on the first run (2026-10-11), confirming that neither table has
ever had a duplicate row: Load's one-hour skip rule and the actuals
high-water mark have held across every run so far. package-lock.yml is
committed so a fresh clone installs the same dbt_utils version.
