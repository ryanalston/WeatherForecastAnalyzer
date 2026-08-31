WeatherForecastAnalyzer
Project Inception:
I wanted to get better at ETL process, so I decided to build an ETL pipeline.
The idea is to pull some sort of future forecasted values at a periodic rate and
capture the changing forecast.  Then transforming the data from raw JSON into a
pandas dataframe that will be later loaded into BigQuery.  

Table Schema
Primary Key
  RequestedLatitude, RequestedLongitude
    the coordinates we send to the API for this row. A city can be pinned to
    multiple points, so these (not the city name) are what disambiguate rows.
  ResolvedLatitude, ResolvedLongitude
    the coordinates the API actually resolved the forecast to. Captured
    alongside the requested point so accuracy can be measured against the
    real grid tile, not just the point we asked for.
  ReportDateTime
    the generation date + time, date that we pull the report
  ForecastDate, ForecastTime
    the future date/time this row is a forecast for

Important Fields
  City
    descriptive label only, not part of the key (many rows can share a city)
  temperature
  humidity
  etc will add more as i get api output

Extract.py
 - create accessor function to retieve weather data using our auth
 - parse extra metadata into dict to be supplied to Transform
 - we need to keep track of ReportDateTime (primary key) this is the generation
 date time of the report and will be generated via our code, and will be used  
 to prevent stale reads from inserting new records

Transform.py
 - Field Name Normalization, eg. temperature->Temperature, date->ForecastDate,
 time->ForecastTime
 - Metadata enrichment, eg. adding API source, setting key fields
 (ReportDateTime)
 - Type Enforcement

Load.py
 - Import BigQuery class
 - Write Pandas data frame to BigQuery weather pipeline data set
