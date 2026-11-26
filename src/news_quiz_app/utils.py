from datetime import datetime


def log(msg: str):
    # Print a message with a timestamp
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
