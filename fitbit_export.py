import os
import sys
import json
import uuid
import datetime as dt
import urllib.parse
import webbrowser
import http.server
import socketserver
import requests
import pandas as pd
import csv
import argparse
from dotenv import load_dotenv

"""
Fitbit Daily Exporter (zero‑manual‑token edition)
=================================================
Export the last *n* days (default 8) of daily Fitbit metrics to a CSV with columns:

    Date, Weight, Calories Burned, Steps, Sleep Start Time, Sleep Stop Time, Minutes Asleep

This version automates the OAuth flow: on the first run it pops open a browser,
captures the redirect on a tiny local server, stores tokens in *tokens.json*,
and refreshes them silently on subsequent runs.

Setup
-----
1. Create a *Personal* Fitbit dev app → set callback `http://127.0.0.1:8080/`.
2. Scopes **activity sleep weight profile**.
3. `.env` file with:

       FITBIT_CLIENT_ID=<id>
       FITBIT_CLIENT_SECRET=<secret>

4. `pip install requests pandas python-dotenv`.

Run
---
    python fitbit_export.py                      # 8 days → fitbit_export.csv
    python fitbit_export.py --days 30 --output out.csv  # 30 days → out.csv
    python fitbit_export.py --start 2025-04-01 --end 2025-04-30  # Specific date range
    python fitbit_export.py --date 2025-04-15   # Single date
"""

load_dotenv()

CLIENT_ID = os.getenv("FITBIT_CLIENT_ID")
CLIENT_SECRET = os.getenv("FITBIT_CLIENT_SECRET")
TOKEN_URL = "https://api.fitbit.com/oauth2/token"
API_BASE = "https://api.fitbit.com"
CALLBACK_URI = "http://localhost:8080/"
TOKEN_FILE = "tokens.json"

#----------------------------------------------------------------------
# Token helpers
#----------------------------------------------------------------------

def _load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_tokens(tokens: dict):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f)

_tokens = _load_tokens()
ACCESS_TOKEN = _tokens.get("access_token")
REFRESH_TOKEN = _tokens.get("refresh_token")

_headers = lambda token: {"Authorization": f"Bearer {token}", "Accept-Language": "en_US"}

#----------------------------------------------------------------------
# Interactive authorisation (first‑run only)
#----------------------------------------------------------------------
class _AuthHandler(http.server.BaseHTTPRequestHandler):
    """Capture the ?code=… redirect & stash it on the server object."""
    server_version = "FitbitAuth/0.2"
    def log_message(self, *_):
        pass  # suppress default logging to stderr
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            self.server.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = "<h1>Authorisation received — you may close this window.</h1>"
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_error(400, "Missing code parameter")


def _interactive_authorise() -> dict:
    print("🔑  Opening browser for Fitbit consent…")
    state = uuid.uuid4().hex
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": CALLBACK_URI,
        "scope": "activity sleep weight profile",
        "state": state,
        "expires_in": 604800,
    }
    webbrowser.open(f"https://www.fitbit.com/oauth2/authorize?{urllib.parse.urlencode(params)}")

    with socketserver.TCPServer(("", 8080), _AuthHandler) as httpd:
        httpd.auth_code = None
        while httpd.auth_code is None:
            httpd.handle_request()
        code = httpd.auth_code

    auth = (CLIENT_ID, CLIENT_SECRET)
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code,
        "redirect_uri": CALLBACK_URI,
    }
    resp = requests.post(TOKEN_URL, auth=auth, data=data)
    resp.raise_for_status()
    tokens = resp.json()
    _save_tokens(tokens)
    print("✅  Tokens saved to tokens.json")
    return tokens

#----------------------------------------------------------------------
# Token refresh
#----------------------------------------------------------------------

def _refresh_access_token():
    global ACCESS_TOKEN, REFRESH_TOKEN
    auth = (CLIENT_ID, CLIENT_SECRET)
    data = {"grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN}
    resp = requests.post(TOKEN_URL, auth=auth, data=data)
    resp.raise_for_status()
    tokens = resp.json()
    ACCESS_TOKEN = tokens["access_token"]
    REFRESH_TOKEN = tokens["refresh_token"]
    _save_tokens(tokens)


def _get(url: str) -> dict:
    resp = requests.get(url, headers=_headers(ACCESS_TOKEN))
    if resp.status_code == 401:
        _refresh_access_token()
        resp = requests.get(url, headers=_headers(ACCESS_TOKEN))
    resp.raise_for_status()
    return resp.json()

#----------------------------------------------------------------------
# Metric fetchers
#----------------------------------------------------------------------

def _fetch_day(date_str: str) -> dict:
    print(f"📆 Fetching data for {date_str}...")
    wt = _get(f"{API_BASE}/1/user/-/body/log/weight/date/{date_str}.json")
    weight = wt["weight"][-1]["weight"] if wt["weight"] else None

    act = _get(f"{API_BASE}/1/user/-/activities/date/{date_str}.json")
    steps = act["summary"].get("steps")
    calories = act["summary"].get("caloriesOut")

    slp = _get(f"{API_BASE}/1.2/user/-/sleep/date/{date_str}.json")
    sleep_start = sleep_end = minutes_asleep = None
    if slp.get("sleep"):
        main = next((l for l in slp["sleep"] if l.get("isMainSleep")), slp["sleep"][0])
        sleep_start, sleep_end, minutes_asleep = main["startTime"], main["endTime"], main["minutesAsleep"]

    return {
        "Date": date_str,
        "Weight": weight,
        "Calories Burned": calories,
        "Steps": steps,
        "Sleep Start Time": sleep_start,
        "Sleep Stop Time": sleep_end,
        "Minutes Asleep": minutes_asleep,
    }

#----------------------------------------------------------------------
# Export logic
#----------------------------------------------------------------------

def export_data(date_range: list, outfile: str = "fitbit_export.csv"):
    """
    Export Fitbit data for the given date range to a CSV file.
    Writes data incrementally, one row at a time.
    """
    # CSV column headers
    columns = ["Date", "Weight", "Calories Burned", "Steps", "Sleep Start Time", "Sleep Stop Time", "Minutes Asleep"]
    
    # Create new CSV file with headers or append to existing if it exists
    file_exists = os.path.exists(outfile)
    
    with open(outfile, mode='a' if file_exists else 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        
        # Write headers only if creating a new file
        if not file_exists:
            writer.writeheader()
        
        total_days = len(date_range)
        for i, date_obj in enumerate(date_range, 1):
            try:
                date_str = date_obj.isoformat()
                row_data = _fetch_day(date_str)
                
                # Write single row to CSV immediately
                writer.writerow(row_data)
                f.flush()  # Ensure data is written to disk immediately
                
                print(f"✓ [{i}/{total_days}] Saved data for {date_str}")
            except Exception as e:
                print(f"❌ Error fetching data for {date_str}: {e}")
    
    print(f"✨ Completed! Data saved to {outfile}")


def generate_date_range(start_date, end_date):
    """Generate a list of dates between start_date and end_date (inclusive)."""
    delta = (end_date - start_date).days + 1
    return [start_date + dt.timedelta(days=i) for i in range(delta)]


def parse_date(date_str):
    """Parse date string in YYYY-MM-DD format."""
    try:
        return dt.date.fromisoformat(date_str)
    except ValueError:
        sys.exit(f"❌ Invalid date format: {date_str}. Please use YYYY-MM-DD format.")

#----------------------------------------------------------------------
# Entrypoint
#----------------------------------------------------------------------
if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("❌ Add FITBIT_CLIENT_ID and FITBIT_CLIENT_SECRET to .env first!")

    if not (ACCESS_TOKEN and REFRESH_TOKEN):
        toks = _interactive_authorise()
        ACCESS_TOKEN, REFRESH_TOKEN = toks["access_token"], toks["refresh_token"]

    # Set up argument parser for more flexible date range options
    parser = argparse.ArgumentParser(description="Export Fitbit data to CSV")
    
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument("--days", type=int, default=8,
                     help="Number of days to fetch from today (default: 8)")
    date_group.add_argument("--date", type=str,
                     help="Specific date to fetch (format: YYYY-MM-DD)")
    date_group.add_argument("--start", type=str,
                     help="Start date for range (format: YYYY-MM-DD)")
    
    parser.add_argument("--end", type=str,
                     help="End date for range (format: YYYY-MM-DD)")
    parser.add_argument("--output", type=str, default="fitbit_export.csv",
                     help="Output CSV filename (default: fitbit_export.csv)")
    
    # For backwards compatibility with positional args
    parser.add_argument("days_pos", nargs="?", type=int, 
                      help=argparse.SUPPRESS)
    parser.add_argument("output_pos", nargs="?", type=str,
                      help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Handle backwards compatibility with positional arguments
    if args.days_pos is not None:
        args.days = args.days_pos
    if args.output_pos is not None:
        args.output = args.output_pos

    # Determine date range based on arguments
    today = dt.date.today()
    
    if args.date:
        # Single date
        single_date = parse_date(args.date)
        date_range = [single_date]
        print(f"🗓️ Fetching data for {args.date}")
    elif args.start:
        # Date range with explicit start
        start_date = parse_date(args.start)
        
        # If end date not provided, use today
        end_date = parse_date(args.end) if args.end else today
        
        if start_date > end_date:
            sys.exit("❌ Start date cannot be after end date")
            
        date_range = generate_date_range(start_date, end_date)
        print(f"🗓️ Fetching data from {start_date.isoformat()} to {end_date.isoformat()} ({len(date_range)} days)")
    else:
        # Default: last N days
        days = args.days
        date_range = [today - dt.timedelta(days=i) for i in range(days)]
        print(f"🗓️ Fetching data for the last {days} days")
    
    # Export the data
    export_data(date_range, args.output)
