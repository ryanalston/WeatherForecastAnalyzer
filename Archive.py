from datetime import datetime, timezone
import json, os, shutil

# get a handle on the drop/archived directories we may end up writing to

script_dir  = os.path.dirname(os.path.abspath(__file__))
drop_dir    = os.path.join(script_dir, "drop")
archive_dir = os.path.join(script_dir, "archived")

os.makedirs(drop_dir, exist_ok=True)
os.makedirs(archive_dir, exist_ok=True)

def format_cron_time(cron):
    return cron.strftime("%Y%m%dT%H%M%S")

def generate_drop_file_name(city, cron):
    # sanition rules:
    # " " --> "-"   delimitter between words in city
    # "," --> "."   delimitter between city and state 
    # "_"           delimitter between sanitized location and sanitized datetime string
    sanitized = city.replace(", ",".").replace(" ", "-")
    return sanitized + "_" + format_cron_time(cron)

def write_drop_file(data, cron_top_of_hour):
    filename = generate_drop_file_name(data['city'], cron_top_of_hour)
    filepath = os.path.join(drop_dir, filename)
    if os.path.exists(filepath):
        print(f" Warning: drop file already exists, not overwriting: {filepath}")
        return filepath
    try:
        with open(filepath, "w") as f:
            json.dump(data,f)
    except OSError as e:
        print(f"Failed to write the file to drop directory: {filepath}: {e}")
        raise
    return filepath

def move_drop_to_archive(city, cron):
    filename            = generate_drop_file_name(city, cron)
    archive_filepath    = os.path.join(archive_dir, filename)
    drop_filepath       = os.path.join(drop_dir, filename)
    try:
        shutil.move(drop_filepath, archive_filepath)
    except (OSError, shutil.Error) as e:
        print(f"Failed to move {drop_filepath} to archive {archive_filepath}\n{e}")
        raise
