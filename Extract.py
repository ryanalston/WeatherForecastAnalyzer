import requests

weather_params = [
        "temperature_2m",
        "relative_humidity_2m",
        "dew_point_2m",
        "apparent_temperature",
        "cloud_cover",
        "wind_speed_10m",
        "wind_direction_10m",
        "weather_code",
        "precipitation",
        "snowfall",
        "rain",
        "showers",
        ]

def get_forecast( location ):
    endpoint = "https://api.open-meteo.com/v1/forecast?"
    params = {
            "latitude"          : location["latitude"],
            "longitude"         : location["longitude"],
            "timezone"          : "UTC",
            "temperature_unit"  : "fahrenheit", 
            "hourly"            : (",").join(weather_params),
            }
        
    print(f" querying api against: {location['city']}")
    r = requests.get( endpoint, params )
    if(r.status_code != 200):
        print(f"  api returned: {r.status_code}")
    elif(r.status_code == 200):
        # capture the city's hourly data into tmp and append
        res = location.copy()
        res["hourly"]               = r.json()["hourly"]
        res["resolved_latitude"]    = r.json()["latitude"]
        res["resolved_longitude"]   = r.json()["longitude"]
        res["elevation"]            = r.json()["elevation"]
    return res    
