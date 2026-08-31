from google.cloud import bigquery

client = bigquery.Client()
dataset = bigquery.Dataset('weatherforecastanalyzer.raw')
dataset = client.create_dataset(dataset, exists_ok=True)
