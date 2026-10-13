select 
	div(lead_time_hours, 24) as lead_day,
	avg(abs(temperature_error)) as temp_mae,
	avg(temperature_error) as temp_bias,
	count(*) as forecast_count
from 
	{{ ref('fct_forecast_error') }} 
group by 
	lead_day 
