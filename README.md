# ZenoFest Registration Reorganizer

Automatically converts new Google Form registrations into **one clean row per
team** and appends them to an **organized Google Sheet shared in Drive** —
with no manual work after setup.

```
[Google Form] --> raw responses Sheet (Drive)
        |
        |   Apps Script "onFormSubmit" trigger  (OR a scheduler calls /sync)
        v
[Python backend deployed for free on Render/Railway]
        |   reads raw sheet, cleans + reorganizes each new response
        v
[organized Sheet created + shared in Google Drive]
```

---

## What the backend does

- Reads the raw responses tab of the form's Google Sheet.
- Reorganizes each response (which has scatter/blank cells because the form is
  **conditional by team size**) into a clean single row.
- Appends **only rows that aren't already there** (dedup by timestamp + team
  name), so re-running is safe.
- Auto-creates the organized spreadsheet and shares it with whoever you want.

---

## Part 1 — One-time Google setup (about 15 min)

### 1. Create a Google service account
1. Go to <https://console.cloud.google.com> and create a project.
2. Enable these APIs: **Google Sheets API** and **Google Drive API**.
3. Go to **APIs & Services → Credentials → Create Credentials → Service account**.
4. Create a key: open the service account → **Keys → Add Key → JSON**.
   It downloads a `service_account.json` file — place it in this `backend/`
   folder. **Never commit it** (it's in `.gitignore`).

### 2. Share your raw sheet with the service account
1. Open your **raw responses Google Sheet** (the form output).
2. Click **Share** and add the service account email
   (the long `....@....iam.gserviceaccount.com` address from the JSON file)
   with **Editor** permission.

### 3. Get your Sheet IDs
- `RAW_SHEET_ID`: the long ID in the raw sheet's URL:
  `docs.google.com/spreadsheets/d/<THIS-IS-THE-ID>/edit`.
- `RAW_TAB_NAME`: the tab name, usually `Form Responses 1`.

---

## Part 2 — Configure and run locally

Copy `.env.example` to `.env` and fill it in:

```ini
GOOGLE_SERVICE_ACCOUNT=service_account.json
RAW_SHEET_ID=<your raw responses sheet ID>
RAW_TAB_NAME=Form Responses 1
ORGANIZED_SHEET_ID=            # leave blank -> will be created automatically
ORGANIZED_SHARE_EMAILS=you@gmail.com,teammate@gmail.com   # who to share with
WEBHOOK_TOKEN=use-a-long-random-secret
```

Do a one-shot sync to create + share the organized sheet:

```powershell
pip install -r requirements.txt
python app.py sync
```

It will print `Appended N team row(s)` and create
**"ZenoFest Registration - Organized"** in your Drive, shared with the emails
you listed. Run it again — it appends nothing (dedup works).

---

## Part 3 — Automate on every new registration

Choose **either** the webhook or polling path.

### Option A (recommended): Webhook trigger via Apps Script
This is instant and uses no extra running resources.

1. Open the raw responses sheet → **Extensions → Apps Script**.
2. Paste the contents of `cloud_function.gs`.
3. Set two script properties (or edit the defaults at the top of the file):
   - `BACKEND_URL` = your deployed URL + `/webhook`
   - `WEBHOOK_TOKEN` = the same secret as in `.env`
4. **Run the `configureTrigger` function once** to install the submit trigger.
5. Grant permissions when prompted.

Now every form submission automatically calls your backend.

### Option B: Polling
Add `python app.py sync` to a scheduled job (free Cron by **cron-job.org**,
or a Render **Cron Job**) that hits `https://YOUR-APP.onrender.com/sync`
every few minutes. Use this if you can't add Apps Script.

---

## Part 4 — Deploy for free

Recommended hosts (all have free tiers; Render is easiest):

### Render (free)
1. Push this `backend/` folder to a GitHub repo.
2. On Render: **New → Web Service → connect your repo**. Select node_type
   grouping: the service auto-detects from `render.yaml` (Flask, `python app.py server`).
3. In the dashboard **Environment** set the same variables as your `.env`
   (leave `ORGANIZED_SHEET_ID` blank the first time).
4. Deploy. Note the public URL, e.g. `https://zenofest-registration.onrender.com`.
5. Use that URL for `BACKEND_URL` in the Apps Script.

> Free hosts **sleep** after inactivity and wake on the next request. The
> Apps Script webhook wakes it and processes the submission (may add ~30s on
> first cold start). For fastest cold starts, use **Railway** or upgrade.

### Railway / Google Cloud Run / PythonAnywhere
Same idea: install `requirements.txt`, run `python app.py server`, expose the
public URL, set env vars.

---

## Testing and caveats

- **Team sizes still to map:** only team-size-3 registrations exist so far, so
  `MEMBER_BY_SIZE` (in `reorganize_logic.py`) only confirms size 3. When you get
  size-2 and size-4 submissions, the member columns for those may need updating.
  Run `python test_sync.py` to confirm cleaning before deploying.
- **Contacts** for members 2+ aren't reliably separated yet (source doesn't map
  them cleanly) — those cells stay blank until mapped.
- The raw sheet must be **shared with the service account** or the backend gets
  permission errors.

## Local demo
`python test_sync.py` runs the whole sync against the bundled sample
(`NEXYRA Registration (Responses).xlsx`) with no cloud calls, so you can see
the cleaned output before connecting real sheets.
