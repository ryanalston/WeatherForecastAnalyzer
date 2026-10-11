import os, json
from datetime import datetime, timezone

import Extract, Archive, Transform, Load
from Paths import script_dir

# create list for metadata associated with dataset
metadata = {}

# set cron_top_of_hour to the floor of now eg. drop mins, secs, etc
now = datetime.now(timezone.utc)
cron_top_of_hour = now.replace(minute=0, second=0, microsecond=0)
metadata["report_date_time"] = cron_top_of_hour

# reference to BQ table 
table_ref   = "weatherforecastanalyzer.raw.forecast"
schema_path = os.path.join(script_dir, "WeatherForecastAnalyzer.json")
field_translations = os.path.join(script_dir, "FieldTranslations.json")
locations_path = os.path.join(script_dir, "Locations.json")

Load.ensure_table(table_ref, schema_path)

try:
    with open(locations_path) as f:
        locations = json.load(f)
except FileNotFoundError as e:
    print(f" Locations file not found: {e}")
    raise
except json.JSONDecodeError as e:
    print(f" Locations file is not valid JSON: {e}")
    raise

print(f" Pipeline initiated ... beginning data pull at: {cron_top_of_hour}")
results = []
for location in locations:
    data = Extract.get_forecast(location)
    if data is not None:
        Archive.write_drop_file(data, cron_top_of_hour)
        results.append(data)
if results:
    print(f"  Extracted {len(results)} data points across {len(locations)} locations")
    df = Transform.transform_shape(results, metadata, field_translations)
    Load.load(table_ref, df)


