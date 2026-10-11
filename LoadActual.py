from google.cloud import bigquery
from Load import client, ensure_table

def get_high_water_mark(location, table_ref):
    query_string = f"SELECT MAX(ObservedDateTime) AS max_observed_date_time FROM `{table_ref}` WHERE RequestedLatitude = @req_lat AND RequestedLongitude = @req_lon"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("req_lat", "FLOAT64", location["latitude"]),
            bigquery.ScalarQueryParameter("req_lon", "FLOAT64", location["longitude"]),
        ]
    )
    job = client.query(query_string, job_config=job_config)
    rows = job.result()
    for row in rows:
        return row['max_observed_date_time']

def load(table_ref, df):
    job = client.load_table_from_dataframe(df, table_ref)
    job.result()
    print(f"  loaded {job.output_rows} rows (df had {len(df)})")

