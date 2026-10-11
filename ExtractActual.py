import requests
from Extract import session, weather_params

MODEL = "era5_seamless"

def get_actual(location, start_date, end_date):
    endpoint = "https://archive-api.open-meteo.com/v1/archive"
    params = {
            "latitude"          : location["latitude"],
            "longitude"         : location["longitude"],
            "timezone"          : "UTC",
            "temperature_unit"  : "fahrenheit",
            "hourly"            : (",").join(weather_params),
            "start_date"        : start_date.isoformat(),
            "end_date"          : end_date.isoformat(),
            "models"            : MODEL
            }

    print(f" querying api against: {location['city']} {start_date} to {end_date}")
    try:
        r = session.get(endpoint, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"  request failed! {e}")
        return None
    if(r.status_code != 200):
        print(f"  api returned: {r.status_code} {r.text[:200]}")
        return None
    # capture the city's hourly data into tmp and append
    res = location.copy()
    body = r.json()
    res["hourly"]               = body["hourly"]
    res["resolved_latitude"]    = body["latitude"]
    res["resolved_longitude"]   = body["longitude"]
    res["elevation"]            = body["elevation"]
    return res    
