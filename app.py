"""
ZenoFest Registration Reorganizer - Python backend
====================================================
Reads the Google Form's raw responses Sheet, reorganizes each response into
one clean row per team, and appends it to an organized sheet that is created
and shared in Google Drive.

Two modes (deploy for free on Render/Railway):

  WEBHOOK MODE (recommended)
      A Google Apps Script bound to the raw sheet sends each new submission
      to POST /webhook. No always-on polling needed.

  POLLING MODE
      A scheduler calls /sync on an interval; the app diffs raw vs organized
      and appends anything new.

Setup
-----
1) Enable the Google Sheets + Drive APIs and download a service account JSON
   (see README). Put it at ./service_account.json or set GOOGLE_SERVICE_ACCOUNT.
2) Share the raw responses spreadsheet with the service account email.
3) Create .env with:
       GOOGLE_SERVICE_ACCOUNT=service_account.json
       RAW_SHEET_ID=<id of the raw responses Google Sheet>
       RAW_TAB_NAME=Form Responses 1
       ORGANIZED_SHEET_ID=<id of the organized sheet (leave blank to auto-create)>
       WEBHOOK_TOKEN=<a shared secret>
       PORT=8080
   3b) Optional: ORGANIZED_SHARE_EMAILS=you@gmail.com,teammate@gmail.com
       to auto-share the organized sheet with reader/writer rights.
4) Run locally:  python app.py sync      (one-shot)
              or  python app.py server   (starts webhook + /sync server)
"""
import os
import re
import sys
import json
import hmac
import hashlib
import signal
from datetime import datetime

from dotenv import load_dotenv
import gspread
from google.oauth2 import service_account

import reorganize_logic as rl

load_dotenv()

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
SA_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "service_account.json")
# Allow passing the service-account key inline as an env var (for deploy
# platforms that can't serve file uploads like Render). If set, it takes
# precedence and gets written to SA_JSON_PATH below.
SA_JSON_CONTENT = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
SA_JSON_PATH = os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", SA_JSON)
RAW_SHEET_ID = os.environ.get("RAW_SHEET_ID", "")
RAW_TAB_NAME = os.environ.get("RAW_TAB_NAME", "Form Responses 1")
ORGANIZED_SHEET_ID = os.environ.get("ORGANIZED_SHEET_ID", "").strip()
SHARE_EMAILS = [
    e.strip()
    for e in os.environ.get("ORGANIZED_SHARE_EMAILS", "").split(",")
    if e.strip()
]
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "")


def get_client():
    path = SA_JSON
    if SA_JSON_CONTENT:
        # Support inline service-account JSON (Render env vars can't be files).
        path = SA_JSON_PATH
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(SA_JSON_CONTENT)
    creds = service_account.Credentials.from_service_account_file(
        path, scopes=SCOPE
    )
    return gspread.authorize(creds)


def open_raw_sheet(client):
    return client.open_by_key(RAW_SHEET_ID).worksheet(RAW_TAB_NAME)


def get_or_create_organized(client):
    """Create the organized sheet in Drive if it doesn't exist; share it."""
    if ORGANIZED_SHEET_ID:
        return client.open_by_key(ORGANIZED_SHEET_ID).sheet1

    # Create a new spreadsheet and put headers on it.
    name = "ZenoFest Registration - Organized"
    sheet = client.create(name)
    ws = sheet.sheet1
    ws.update("A1", [rl.OUTPUT_HEADERS])
    for email in SHARE_EMAILS:
        sheet.share(email, perm_type="user", role="writer")
    # Share as anyone-with-the-link can view (so it's shareable in Drive).
    try:
        client.insert_permission(sheet.id, None, perm_type="anyone", role="reader")
    except Exception as exc:  # pragma: no cover
        print("warning: could not set public link:", exc)
    return ws


def _row_key(row):
    """Timestamp + team name as a stable identity for dedup."""
    ts = row[0] if row else ""
    team = row[2] if len(row) > 2 else ""
    return (str(ts), str(team))


def _new_rows_info(rows, start_row):
    """Build the per-row metadata the Apps Script needs to send emails,
    including the generated ZenoFest team id."""
    import reorganize_logic as rl

    def field(row, name):
        try:
            return row[rl.OUTPUT_HEADERS.index(name)]
        except (ValueError, IndexError):
            return ""

    info = []
    for i, row in enumerate(rows):
        sheet_row = start_row + i
        tech_event = field(row, "Tech Event")
        team_id = rl.make_team_id(tech_event, sheet_row)
        info.append({
            "row": sheet_row,
            "team_id": team_id,
            "email": field(row, "Email"),
            "team_name": field(row, "Team Name"),
            "college": field(row, "College"),
            "leader_name": field(row, "Leader Name"),
            "leader_contact": field(row, "Leader Contact"),
            "team_size": field(row, "Team Size"),
            "tech_event": tech_event,
            "non_tech_event": field(row, "NonTech Event"),
            "food_preference": field(row, "Food Preference"),
            "leader_food": field(row, "Member 1 Food"),
            "members": [
                {"name": field(row, "Member 2 Name"), "contact": field(row, "Member 2 Contact"), "food": field(row, "Member 2 Food")},
                {"name": field(row, "Member 3 Name"), "contact": field(row, "Member 3 Contact"), "food": field(row, "Member 3 Food")},
            ],
        })
    return info


def sync(client=None, raw_ws=None, organized_ws=None):
    """One sync pass: read raw, reorganize, append only NEW rows.
    Returns (appended_count, [row_info, ...])."""
    client = client or get_client()
    raw_ws = raw_ws or open_raw_sheet(client)
    organized_ws = organized_ws or get_or_create_organized(client)

    raw_matrix = raw_ws.get_all_values()
    if not raw_matrix:
        print("Raw sheet is empty.")
        return 0, []

    headers = raw_matrix[0]
    data_rows = raw_matrix[1:]
    clean_rows = rl.from_matrix(headers, data_rows)
    if not clean_rows:
        print("No new raw responses to process.")
        return 0, []

    # Existing identity set in the organized sheet.
    existing_keys = set()
    existing = organized_ws.get_all_values()
    if existing:
        existing_keys = {_row_key(r) for r in existing[1:]}

    to_append = []
    for row in clean_rows:
        if _row_key(row) in existing_keys:
            continue
        to_append.append(row)
        existing_keys.add(_row_key(row))

    if not to_append:
        print("No new responses to append.")
        return 0, []

    # Header may be missing if sheet was created empty; ensure it.
    first = organized_ws.get_all_values()
    if not first or all(not c for c in first[0]):
        organized_ws.update(range_name="A1", values=[rl.OUTPUT_HEADERS])
        start_row = 2
    else:
        start_row = len(first) + 1
    organized_ws.append_rows(to_append, value_input_option="USER_ENTERED")
    print(f"Appended {len(to_append)} team row(s).")

    return len(to_append), _new_rows_info(to_append, start_row)


# ---------------------------------------------------------------------------
# Server (webhook + /sync) via Flask
# ---------------------------------------------------------------------------
def create_app(client=None):
    from flask import Flask, request, jsonify

    app = Flask(__name__)
    app.config["CLIENT"] = client

    def _authorized(req):
        token = req.headers.get("X-Webhook-Token", "")
        if not WEBHOOK_TOKEN:
            return True  # no token configured -> open (dev only)
        return hmac.compare_digest(token, WEBHOOK_TOKEN)

    @app.post("/webhook")
    def webhook():
        if not _authorized(request):
            return jsonify({"error": "unauthorized"}), 401
        try:
            # Trigger a full sync. The Apps Script just needs to call this
            # endpoint on each new submission; the backend re-reads the raw
            # sheet and appends only rows that aren't in the organized sheet.
            n, rows = sync(app.config["CLIENT"])
            return jsonify({
                "ok": True,
                "appended": n,
                "rows": rows,
                "status": "synced",
            }), 200
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.get("/sync")
    def sync_endpoint():
        try:
            n, rows = sync(app.config["CLIENT"])
            return jsonify({"ok": True, "appended": n, "rows": rows}), 200
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": str(exc)}), 500

    @app.get("/health")
    def health():
        return jsonify({"ok": True}), 200

    @app.get("/team-id-sample")
    def team_id_sample():
        """Small dev helper: preview the team id format for each event."""
        import reorganize_logic as rl

        events = ["Project Expo", "UI/UX Design", "Logic Hunt"]
        return jsonify({"samples": [
            {"event": e, "team_id": rl.make_team_id(e, 12)} for e in events
        ]}), 200

    return app


def main():
    print("ZenoFest Registration Reorganizer")
    print("=" * 40)
    if not RAW_SHEET_ID:
        print("ERROR: RAW_SHEET_ID is not set. Create a .env file (see README).")
        sys.exit(1)

    mode = sys.argv[1] if len(sys.argv) > 1 else "sync"
    if mode == "sync":
        sync()
    elif mode == "server":
        port = int(os.environ.get("PORT", "8080"))
        client = get_client()
        app = create_app(client)
        print(f"Starting server on port {port} ...")
        app.run(host="0.0.0.0", port=port, threaded=True)
    else:
        print(f"Unknown mode: {mode}. Use 'sync' or 'server'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
