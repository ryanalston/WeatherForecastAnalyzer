select
  ObservedDateTime as observed_date_time,
  LoadedDateTime as loaded_date_time,
  Model as model,
  RequestedLatitude as requested_latitude,
  RequestedLongitude as requested_longitude,
  ResolvedLatitude as resolved_latitude,
  ResolvedLongitude as resolved_longitude,
  City as city,
  Elevation as elevation,
  Temperature_2m as temperature_2m,
  RelativeHumidity_2m as relative_humidity_2m,
  DewPoint_2m as dew_point_2m,
  ApparentTemperature as apparent_temperature,
  CloudCover as cloud_cover,
  WindSpeed_10m as wind_speed_10m,
  WindDirection_10m as wind_direction_10m,
  WeatherCode as weather_code,
  Precipitation as precipitation,
  Snowfall as snowfall,
  Rain as rain,
  Showers as showers

from {{ source('raw', 'actual') }}
