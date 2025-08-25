import os
import sys
import configparser
from datetime import datetime, timedelta

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def load_log_retention_days():
    config = configparser.ConfigParser()
    try:
        ini_path = resource_path("station.ini")
        config.read(ini_path)
        return config.getint("SETTINGS", "log_deletion_days", fallback=4)
    except Exception:
        return 4

def cleanup_old_logs(log_folder):
    deletion_days = load_log_retention_days()
    cutoff_date = datetime.now() - timedelta(days=deletion_days)

    if not os.path.exists(log_folder):
        print(f"Log folder does not exist: {log_folder}")
        return

    for filename in os.listdir(log_folder):
        file_path = os.path.join(log_folder, filename)
        if os.path.isfile(file_path):
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            if file_time < cutoff_date:
                try:
                    os.remove(file_path)
                    print(f"Deleted old log file: {file_path}")
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")

if __name__ == "__main__":
    # Check for command-line argument for log_folder
    if len(sys.argv) > 1:
        log_folder = sys.argv[1]
    else:
        # Default folder if no argument is provided
        log_folder = os.path.join(os.path.dirname(__file__), "logs")
    cleanup_old_logs(log_folder)