WeatherForecastAnalyzer

Project Inception: I wanted to get better at ETL process, so I decided to build
an ETL pipeline. The idea is to pull some sort of future forecasted values at a
periodic rate and capture the changing forecast. Then transforming the data
from raw JSON into a pandas dataframe that will be later loaded into BigQuery.

For the full rationale behind the schema, key design, and tradeoffs, see
DESIGN_NOTES.md. This file is a quick orientation/runbook, not the design doc.

All code in this project was written independently as a hands-on learning
exercise.  Claude was used in a code-review and debugging-partner role
throughout.  It was responsible for catching bugs, questioning design
decisions, and explaining concepts, but didn't write the implementation.  This
README and DESIGN_NOTES.md were drafted with Claude's assistance, based on
design decisions made during development.

Pipeline Flow

Runs hourly via cron, driven end-to-end by Pipeline.py:

  1. Extract.py queries the Open-Meteo API per configured location.
  2. Archive.py writes each successful pull to drop/ as a JSON file (one file
     per city per run) before anything is transformed or loaded -- this is the
     raw, unprocessed record of what the API returned.
  3. Transform.py reshapes the combined raw results into a single pandas
     DataFrame: flattens the hourly arrays into rows, attaches metadata
     (ReportDateTime), and renames fields to the BigQuery-ready schema via
     FieldTranslations.json.
  4. Load.py writes the DataFrame into BigQuery, one city at a time. A city is
     only loaded if its incoming ReportDateTime is at least an hour newer than
     what's already in the table (stale-read guard). On successful load, that
     city's drop file is moved from drop/ to archived/. A failure loading one
     city is logged and skipped -- it does not block the rest of that run's
     cities.

Actuals Pipeline Flow

A second, independent pipeline, PipelineActual.py, lands observed weather
(Open-Meteo's archive endpoint, ERA5 reanalysis via models=era5_seamless) into
raw.actual, for comparing forecasts against what actually happened. It runs on
its own schedule and doesn't touch the forecast pipeline. Per location:

  1. LoadActual.get_high_water_mark finds the latest ObservedDateTime already
     loaded for that location's requested coordinates (none on the first run,
     which then starts at 2026-08-31 -- so the first run is the backfill).
  2. ExtractActual.get_actual requests from that date through today (UTC).
  3. Transform.py reshapes it exactly as for forecasts, using
     ActualFieldTranslations.json and stamping LoadedDateTime and Model.
  4. Rows with nulls (hours ERA5 hasn't filled yet; it runs ~5 days behind)
     and rows at or before the high-water mark are dropped.
  5. LoadActual.load writes what's left; if nothing is left, the location is
     logged as "nothing new". A failing location is logged and skipped.

No drop/archive step: ERA5 is a permanent archive, so anything missing can be
pulled again. See DESIGN_NOTES.md "Actuals Ingest" for the reasoning.

File Responsibilities

  - Paths.py - central place for script_dir, drop_dir, archive_dir so every module resolves paths the same way regardless of cwd (needed since cron doesn't run with the script's directory as cwd).
  - Extract.py - pulls raw forecast data from the Open-Meteo API. No transformation logic. Requests go through a shared requests.Session that retries 429/5xx responses with exponential backoff and jitter, with a 10s timeout per request. Returns None when a request still fails, so a single location failure doesn't take down the whole run.
  - Archive.py - drop/archived file management. Writes the raw per-city pull to drop/ immediately after extract, then moves it to archived/ once that city's data is successfully loaded.
  - Transform.py - shared by both pipelines: flattens the hourly arrays into rows, stamps every entry of the metadata dict the caller passes (ReportDateTime for forecasts; LoadedDateTime and Model for actuals), and renames fields using the translation file the caller passes. Deliberately no computed/derived fields -- see DESIGN_NOTES.md "Layer Responsibilities".
  - Load.py - ensures the BigQuery table exists (via WeatherForecastAnalyzer.json schema) and writes the transformed DataFrame into it.
  - SetupDW.py - one-time setup: creates the BigQuery dataset. Run manually, not part of the hourly pipeline.
  - Pipeline.py - orchestrates the forecast run: computes the cron-slot ReportDateTime, loops locations through Extract -> Archive -> collects results, then runs a single Transform + Load pass.
  - ExtractActual.py - pulls a date range of observed weather from Open-Meteo's archive endpoint (model pinned via MODEL), reusing Extract's session and field list. Returns the same shape as Extract.get_forecast so Transform can handle both.
  - LoadActual.py - high-water-mark query (parameterized, keyed on requested coordinates) and the raw.actual load. Reuses Load's BigQuery client and ensure_table.
  - PipelineActual.py - orchestrates the actuals run, one location at a time (see Actuals Pipeline Flow).
  - Locations.json - the list of locations (city label + requested coordinates). Read by PipelineActual.py; Pipeline.py still has its own inline copy.
  - ActualSchema.json / ActualFieldTranslations.json - raw.actual's schema and API-name -> column-name map (the forecast equivalents are WeatherForecastAnalyzer.json and FieldTranslations.json).

Table Schema

See WeatherForecastAnalyzer.json (raw.forecast) and ActualSchema.json
(raw.actual) for the authoritative field lists, and
DESIGN_NOTES.md for the reasoning behind the primary key (Requested/Resolved
lat-long, ReportDateTime, ForecastDateTime) and why City and Elevation are
descriptive rather than key fields.

Running It

  1. Install dependencies: pip install -r requirements.txt (a venv/ is used
     locally; not committed).
  2. Authenticate to GCP (e.g. gcloud auth application-default login) with
     access to the weatherforecastanalyzer project.
  3. One-time: python SetupDW.py to create the BigQuery dataset.
  4. python Pipeline.py to run a single pull manually. Pipeline.py also ensures
     the BigQuery table exists on every run, so no separate manual
     table-creation step is needed.

Scheduling

Runs hourly via crontab, logging to logs/ (gitignored):

  0 * * * * /path/to/venv/bin/python3 /path/to/Pipeline.py >>
  /path/to/logs/pipeline.log 2>&1

The actuals pipeline runs from its own crontab entry, logging to
logs/pipeline_actual.log. It works out its own date range each run, so the
schedule only needs to be "at least once a day while the machine is on"; a
missed day just means a longer range next time.

Locations: PipelineActual.py reads Locations.json; Pipeline.py still has an
inline copy (todo: switch it to Locations.json too).

Planned Expansion

Built: a second raw table for actual/observed weather (raw.actual, see
Actuals Pipeline Flow). Not yet started: a dbt layer joining it against
raw.forecast to compute forecast-vs-actual shift by lead time, and a BI tool
(Power BI/Tableau/Looker Studio, undecided) on top of that for
city/metric/time-frame segmentation.
See DESIGN_NOTES.md's "Planned Expansion" section for the reasoning.
