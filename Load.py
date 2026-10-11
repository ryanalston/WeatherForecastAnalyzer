from google.cloud import bigquery
from datetime import timedelta
import Archive

client = bigquery.Client(project="weatherforecastanalyzer")

def ensure_table(table_ref, schema_path):
    schema = client.schema_from_json(schema_path)
    table = bigquery.Table(table_ref, schema=schema)

    try:
        client.create_table( table, exists_ok=True)
    except Exception as e:
        print(f' Unable to create table: {e}')
        raise

def get_latest_report_date_time(city):
    query_string = "SELECT MAX(ReportDateTime) AS max_report_date_time FROM weatherforecastanalyzer.raw.forecast WHERE City = @city" 
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("city", "STRING", city),
        ]
    )

    job = client.query(query_string, job_config=job_config)
    rows = job.result()
    for row in rows:
        return row['max_report_date_time']

def load(table_ref, df):
    unique_cities = df['City'].unique()
    for city in unique_cities:
        try:
            # only grab frames for current city
            city_df = df[df['City'] == city]
            incoming_date_time = city_df['ReportDateTime'].iloc[0]

            last_loaded = get_latest_report_date_time(city)
            print(f" trying to load city: {city}, with new report from: {incoming_date_time}, latest in BQ: {last_loaded}")
            # check if the last file is at least one hour older than the new file
            if last_loaded is None or (incoming_date_time - last_loaded) >= timedelta(hours=1):
                job = client.load_table_from_dataframe(city_df, table_ref)
                job.result()
                Archive.move_drop_to_archive(city, incoming_date_time)
            else:
                print(f"   skipping load for: {city} with report date: {incoming_date_time}, BQ's most recent report is: {last_loaded}")
        except Exception as e:
            print(f' Unable to load city {city}: {e}')
            continue
