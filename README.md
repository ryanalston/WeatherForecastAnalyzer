WeatherForecastAnalyzer

Project Inception:
I wanted to get better at ETL process, so I decided to build an ETL pipeline.
The idea is to pull some sort of future forecasted values at a periodic rate and
capture the changing forecast. Then transforming the data from raw JSON into a
pandas dataframe that will be later loaded into BigQuery.

For the full rationale behind the schema, key design, and tradeoffs, see
DESIGN_NOTES.md. This file is a quick orientation/runbook, not the design doc.

Pipeline Flow

Runs hourly via cron, driven end-to-end by Pipeline.py:

  1. Extract.py queries the Open-Meteo API per configured location.
  2. Archive.py writes each successful pull to drop/ as a JSON file
     (one file per city per run) before anything is transformed or loaded --
     this is the raw, unprocessed record of what the API returned.
  3. Transform.py reshapes the combined raw results into a single pandas
     DataFrame: flattens the hourly arrays into rows, attaches metadata
     (ReportDateTime), and renames fields to the BigQuery-ready schema via
     FieldTranslations.json.
  4. Load.py writes the DataFrame into BigQuery, one city at a time. A city
     is only loaded if its incoming ReportDateTime is at least an hour newer
     than what's already in the table (stale-read guard). On successful
     load, that city's drop file is moved from drop/ to archived/. A
     failure loading one city is logged and skipped -- it does not block
     the rest of that run's cities.

File Responsibilities

  Paths.py     - central place for script_dir, drop_dir, archive_dir so every
                 module resolves paths the same way regardless of cwd (needed
                 since cron doesn't run with the script's directory as cwd).
  Extract.py   - pulls raw forecast data from the Open-Meteo API. No
                 transformation logic. Returns None on a non-200 response so
                 a single location failure doesn't take down the whole run.
  Archive.py   - drop/archived file management. Writes the raw per-city pull
                 to drop/ immediately after extract, then moves it to
                 archived/ once that city's data is successfully loaded.
  Transform.py - field name normalization (API names -> schema names),
                 metadata enrichment (ReportDateTime), type enforcement.
                 Deliberately no computed/derived fields -- see
                 DESIGN_NOTES.md "Layer Responsibilities".
  Load.py      - ensures the BigQuery table exists (via WeatherForecastAnalyzer.json
                 schema) and writes the transformed DataFrame into it.
  SetupDW.py   - one-time setup: creates the BigQuery dataset. Run manually,
                 not part of the hourly pipeline.
  Pipeline.py  - orchestrates the run: computes the cron-slot ReportDateTime,
                 loops locations through Extract -> Archive -> collects
                 results, then runs a single Transform + Load pass.

Table Schema

See WeatherForecastAnalyzer.json for the authoritative field list, and
DESIGN_NOTES.md for the reasoning behind the primary key (Requested/Resolved
lat-long, ReportDateTime, ForecastDateTime) and why City and Elevation are
descriptive rather than key fields.

Running It

  1. Install dependencies: pip install -r requirements.txt (a venv/ is used
     locally; not committed).
  2. Authenticate to GCP (e.g. gcloud auth application-default login) with
     access to the weatherforecastanalyzer project.
  3. One-time: python SetupDW.py to create the BigQuery dataset.
  4. python Pipeline.py to run a single pull manually. Pipeline.py also
     ensures the BigQuery table exists on every run, so no separate manual
     table-creation step is needed.

Scheduling

Runs hourly via crontab, logging to logs/ (gitignored):

  0 * * * * /path/to/venv/bin/python3 /path/to/Pipeline.py >> /path/to/logs/pipeline.log 2>&1

Locations list currently lives inline in Pipeline.py (todo: move to a config
file).
