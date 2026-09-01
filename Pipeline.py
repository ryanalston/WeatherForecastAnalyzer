import Extract, Archive, Transform, Load, os
from datetime import datetime, timezone
from Paths import script_dir

# create list for metadata associated with dataset
metadata = {}

# set cron_top_of_hour to the floor of now eg. drop mins, secs, etc
now = datetime.now(timezone.utc)
cron_top_of_hour = now.replace(minute=0, second=0, microsecond=0)
metadata["cron_top_of_hour"] = cron_top_of_hour

# reference to BQ table 
table_ref   = "weatherforecastanalyzer.raw.forecast"
schema_path = os.path.join(script_dir, "WeatherForecastAnalyzer.json")

Load.ensure_table(table_ref, schema_path)

# todo move to config file
locations = [
        { "city" : "Elk Grove, CA", "latitude" :38.418129, "longitude" : -121.393257 },
        { "city" : "San Jose, CA", "latitude" : 37.334789, "longitude" : -121.888138 },
        { "city" : "Los Angeles, CA", "latitude" : 34.052235, "longitude" : -118.243683 },
        { "city" : "Seattle, WA", "latitude" : 47.603230, "longitude" : -122.330276 },
        { "city" : "Austin, TX", "latitude" : 30.26759, "longitude" : -97.74299 },
        { "city" : "Kansas City, KS", "latitude" : 39.1142, "longitude" : -94.6275 },
        { "city" : "Lakewood Ranch, FL", "latitude" : 27.42648, "longitude" : -82.37609 },
        { "city" : "New York City, NY", "latitude" : 40.71453, "longitude" : -74.00172 },
        { "city" : "Porto, Portugal", "latitude" : 41.1496, "longitude" : 8.61099 },
        { "city" : "Cebu City, Philippines", "latitude" : 10.3167, "longitude" : 123.8907 },
        ]

print(f" Pipeline initiated ... beginning data pull at: {cron_top_of_hour}")
results = []
for location in locations:
    data = Extract.get_forecast(location)
    if data is not None:
        Archive.write_drop_file(data, cron_top_of_hour)
        results.append(data)
if results:
    print(f"  Extracted {len(results)} data points across {len(locations)} locations")
    df = Transform.transform_shape(results,metadata)
    Load.load(table_ref, df)


