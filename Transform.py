import pandas as pd, json

def transform_shape( location_forecasts, metadata ):
    # capture report gen time and parse location_forecasts into result
    cron_top_of_hour = metadata['cron_top_of_hour']
    result = []
    # traverse location_forecasts for each city
    for location in location_forecasts:
        try:
            hourly = location['hourly']
            # zip hourly data into row and set metdata fields
            for values in zip(*hourly.values()):
                row = dict(zip(hourly.keys(), values))
                row["city"]                 = location["city"]
                row["requested_latitude"]   = location["latitude"]
                row["requested_longitude"]  = location["longitude"]
                row["resolved_latitude"]    = location["resolved_latitude"]
                row["resolved_longitude"]   = location["resolved_longitude"]
                row["elevation"]            = location["elevation"]
                row["report_date_time"]     = cron_top_of_hour
                result.append(row)
        except (KeyError, IndexError) as e:
            print(f"Skipping malformed location: {location}\n{e}")
            continue
            
    # use built result to instantiate and return a DF
    df = pd.DataFrame(result)
   
    # we need to convert the field names in the df to BQ ready names
    try:
        with open("FieldTranslations.json") as f:
            field_map = json.load(f)
    except FileNotFoundError as e:
        print(f" Field Translation file not found: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f" Translation file is not valid JSON: {e}")
        raise

    df = df.rename(columns=field_map)
    # sanity check on the rename
    check_cols  = set(field_map.values())
    actual_cols = set(df.columns)

    if not check_cols.issubset(actual_cols):
        missing = check_cols - actual_cols
        print(f" dataframe field rename did not produce expecting columns, missing: {missing}")
        raise ValueError(f"  dataframe column rename failed, missing: {missing}")
    return df
