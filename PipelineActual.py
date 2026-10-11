import os, json
from datetime import datetime, timezone, date 

import pandas as pd

import ExtractActual, Transform, LoadActual
from Paths import script_dir

BACKFILL_START = date(2026, 8, 31)

# reference to BQ table 
TABLE_REF   = "weatherforecastanalyzer.raw.actual"
schema_path = os.path.join(script_dir, "ActualSchema.json")
field_translations  = os.path.join(script_dir, "ActualFieldTranslations.json")
locations_path = os.path.join(script_dir, "Locations.json")

now = datetime.now(timezone.utc)
today = now.date()

# create list for metadata associated with dataset
metadata = {"loaded_date_time": now,
            "model": ExtractActual.MODEL
            }


try:
    with open(locations_path) as f:
        locations = json.load(f)
except FileNotFoundError as e:
    print(f" Locations file not found: {e}")
    raise
except json.JSONDecodeError as e:
    print(f" Locations file is not valid JSON: {e}")
    raise


LoadActual.ensure_table(TABLE_REF, schema_path)

print(f" Pipeline initiated ... beginning data pull at: {now}")
for location in locations:
    try:
        hwm = LoadActual.get_high_water_mark(location, TABLE_REF)
        start = BACKFILL_START if hwm is None else hwm.date()
        print(f" {location['city']}, { 'nothing is loaded yet' if hwm is None else hwm}, from {start} to {today}")
        data = ExtractActual.get_actual(location, start, today)
        if data is None:
            continue
        df = Transform.transform_shape([data], metadata, field_translations)
        df['ObservedDateTime'] = pd.to_datetime(df['ObservedDateTime'], utc=True)
        df = df.dropna()
        if hwm is not None:
            df = df[df['ObservedDateTime'] > hwm]
        if df.empty:
            print(f"  nothing new")
            continue
        LoadActual.load(TABLE_REF, df)
    except Exception as e:
        print(f"  {location['city']} failed: {e}")
