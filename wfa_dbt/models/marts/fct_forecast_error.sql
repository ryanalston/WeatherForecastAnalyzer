with 
forecast as 
(
	select 
		city,
		forecast_date_time,
		report_date_time,
		requested_latitude,
		requested_longitude,
		temperature_2m,
		precipitation,
		timestamp_diff(forecast_date_time, report_date_time, hour) as lead_time_hours
	from {{ ref('stg_forecast') }}
),

actual as
(
	select
		observed_date_time,
		requested_latitude,
		requested_longitude,
		temperature_2m,
		precipitation
	from {{ ref('stg_actual') }}
),
joined as
(
	select
		forecast.city,
		forecast.forecast_date_time,
		forecast.report_date_time,
		forecast.requested_latitude,
		forecast.requested_longitude,
		forecast.temperature_2m as temperature_forecast,
		forecast.precipitation as precipitation_forecast,
		actual.temperature_2m as temperature_actual,
		actual.precipitation as precipitation_actual,
		forecast.lead_time_hours
	from forecast
	inner join actual 
	on
		forecast.forecast_date_time = actual.observed_date_time 
		and forecast.requested_latitude = actual.requested_latitude 
		and forecast.requested_longitude = actual.requested_longitude
	where 
		forecast.lead_time_hours >= 0
)

select
	city,
	report_date_time,
	forecast_date_time,
	requested_latitude,
	requested_longitude,
	lead_time_hours,
	temperature_forecast,
	temperature_actual,
	temperature_forecast - temperature_actual as temperature_error,
	precipitation_forecast,
	precipitation_actual,
	precipitation_forecast - precipitation_actual as precipitation_error
from joined
