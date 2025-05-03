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
from dotenv import load_dotenv

"""
Fitbit Daily Exporter (zero‑manual‑token edition)
=================================================
Export the last *n* days (default 8) of daily Fitbit metrics to a CSV with columns:

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
    python fitbit_export.py            # 8 days → fitbit_export.csv
    python fitbit_export.py 30 out.csv # 30 days → out.csv
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

def export_last_n_days(n: int = 8, outfile: str = "fitbit_export.csv"):
    today = dt.date.today()
    rows = [_fetch_day((today - dt.timedelta(days=i)).isoformat()) for i in range(n)]
    pd.DataFrame(rows).to_csv(outfile, index=False)
    print(f"✨  Saved {outfile} with {n} days of data.")

#----------------------------------------------------------------------
# Entrypoint
#----------------------------------------------------------------------
if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("❌  Add FITBIT_CLIENT_ID and FITBIT_CLIENT_SECRET to .env first!")

    if not (ACCESS_TOKEN and REFRESH_TOKEN):
        toks = _interactive_authorise()
        ACCESS_TOKEN, REFRESH_TOKEN = toks["access_token"], toks["refresh_token"]

    days = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    csv_name = sys.argv[2] if len(sys.argv) > 2 else "fitbit_export.csv"
    export_last_n_days(days, csv_name)
