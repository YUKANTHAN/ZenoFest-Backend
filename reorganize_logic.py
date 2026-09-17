"""Reorganize Google Form responses (conditional-by-team-size layout)
into one clean row per team.

Two helper paths are provided:

1. `from_headers(values_with_headers)` - for raw sheets where every column is
   a unique header (normal case). Matches always-on fields by exact header
   text; member fields are matched by header *pattern* and reassembled by
   team size.

2. `from_columns(rows, team_size_map)` - fallback that works purely by
   column number for sheets that become ambiguous.  (Not required if the
   headers are unique.)
"""

# ---------------------------------------------------------------------------
# FIELD MAPS
# ---------------------------------------------------------------------------

# Explicit per-team-size column index (0-based) -> "Food" output slot, in the
# order [leader, member 2, member 3]. The form uses conditional sections, so
# the food answers for each member live in DIFFERENT physical columns depending
# on team size, and for a 3-member team the leader's food question appears
# AFTER the member-2 food question in the raw sheet (verified against rows where
# members chose different foods). Index-based mapping beats scanning header text.
FOOD_COLS_BY_SIZE = {
    1: [21],            # solo: leader only
    2: [26, 29],        # leader, member 2
    3: [14, 13, 18],    # leader, member 2, member 3  (raw order is m2, leader, m3!)
}

# For solo teams the leader's details live in a generic "Name/Contact" block,
# since the "Team Leader Name" question isn't shown for team size 1.
SOLO_NAME_HEADER = "Name"

# Header text used for the "Select Team Size" question. Its value decides which
# conditional section's columns actually hold this team's answers.
TEAM_SIZE_HEADER = "Select Team Size"

# Exact header text -> output field, for always-present columns.
ALWAYS_HEADER = {
    "Timestamp": "Timestamp",
    "Email Address": "Email",
    "Team Name": "Team Name",
    "College Name": "College",
    "Department": "Department",
    "Year": "Year",
    "Year of study": "Year",
    "Team Leader Name": "Leader Name",
    "Team Leader Contact (Phone Number)": "Leader Contact",
    "Team Leader Email": "Leader Email",
    "Select Team Size": "Team Size",
    "Select Technical Event (Choose any 1)": "Tech Event",
    "Select Non-Technical Event (Choose any 1)": "NonTech Event",
    "Food Preference (Choose 1 for the team)": "Food Preference",
    "Upload the payment screenshot ": "Payment Screenshot",
}

# Header keywords (case-insensitive) that identify a member name column.
# The form scatters members across duplicated columns; we scan all columns
# whose header contains "member" + a number and place them by team.
# Every team has exactly 3 members (leader + 2), so we only keep slots 2 and 3.
MAX_MEMBERS = 3
OUTPUT_ORDER_BEFORE_MEMBERS = [
    "Timestamp", "Email", "Team Name", "College", "Department", "Year",
    "Leader Name", "Leader Contact", "Leader Email", "Team Size",
    "Tech Event", "NonTech Event", "Food Preference", "Payment Screenshot",
]
OUTPUT_HEADERS = OUTPUT_ORDER_BEFORE_MEMBERS + [
    f"Member {n} Name" for n in range(2, MAX_MEMBERS + 1)
] + [
    f"Member {n} Email" for n in range(2, MAX_MEMBERS + 1)
] + [
    f"Member {n} Contact" for n in range(2, MAX_MEMBERS + 1)
] + [
    f"Member {n} Food" for n in range(1, MAX_MEMBERS + 1)
]


def make_team_id(tech_event, row_num):
    """Build a ZenoFest team id like ZFPE5 / ZFUI7 / ZFLH12 from the tech
    event the team chose and the sheet row it landed on in the organized
    sheet. Falls back to event initials when nothing known matches."""
    e = (tech_event or "").strip().lower()
    if "project" in e or "expo" in e:
        code = "PE"
    elif "logic" in e or "hunt" in e:
        code = "LH"
    elif "ui" in e or "ux" in e:
        code = "UI"
    else:
        initials = "".join(w[0] for w in str(tech_event).split() if w)[:2].upper()
        code = initials or "XX"
    return f"ZF{code}{int(row_num)}"


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _first_nonempty(values):
    for v in values:
        if _fmt(v):
            return _fmt(v)
    return ""


def _clean_record(meta, members_by_slot, food_candidates, food_by_col=None,
                   member_emails=None, member_contacts=None):
    # Per-member food preferences (leader, member 2, member 3)
    foods = _member_foods(meta.get("Team Size"), food_by_col)

    if not meta.get("Food Preference"):
        meta["Food Preference"] = foods[0] if foods else (
            food_candidates[0] if food_candidates else "")

    if not meta.get("Team Name") and not meta.get("Timestamp"):
        return None

    row = [meta.get(k, "") for k in OUTPUT_ORDER_BEFORE_MEMBERS]
    # Member names
    for n in range(2, MAX_MEMBERS + 1):
        row.append(_first_nonempty(members_by_slot[n]))
    # Member emails
    member_emails = member_emails or {}
    for n in range(2, MAX_MEMBERS + 1):
        row.append(member_emails.get(n, ""))
    # Member contacts
    member_contacts = member_contacts or {}
    for n in range(2, MAX_MEMBERS + 1):
        row.append(member_contacts.get(n, ""))
    # Member foods (leader, m2, m3)
    if foods and len(foods) >= 1:
        row.append(foods[0])  # leader
    else:
        row.append(meta.get("Food Preference", ""))
    for n in range(2, MAX_MEMBERS + 1):
        if foods and len(foods) >= n:
            row.append(foods[n - 1])
        else:
            row.append(meta.get("Food Preference", ""))
    return row


def _member_foods(team_size, food_by_col):
    """Rebuild the member foods as [leader, m2, m3] using the explicit
    per-team-size column map. `food_by_col` maps a raw column index to the
    food value typed there ("" if that column held nothing)."""
    food_by_col = food_by_col or {}
    try:
        key = int(str(team_size).strip())
    except (TypeError, ValueError):
        key = None
    cols = FOOD_COLS_BY_SIZE.get(key) if key is not None else None
    result = []
    if cols:
        result = [_fmt(food_by_col.get(c, "")) for c in cols]
    else:
        result = list(food_by_col.values())[:MAX_MEMBERS]
    while len(result) < MAX_MEMBERS:
        result.append("")
    return result


def from_matrix(headers, rows):
    """headers: list of (possibly duplicated) header strings.
    rows: list of data rows (aligned to headers by position).
    Returns list of clean output rows."""
    import re

    out = []
    for row in rows:
        meta = {}
        members_by_slot = {n: [] for n in range(2, MAX_MEMBERS + 1)}
        member_emails = {}
        member_contacts = {}
        food_candidates = []
        food_by_col = {}
        solo_name = ""
        team_food_set = False

        for c, header in enumerate(headers):
            if header is None:
                continue
            h = str(header)
            low = h.lower()
            value = row[c] if c < len(row) else None
            fmt = _fmt(value)

            if "food preference" in low:
                if fmt:
                    food_candidates.append(fmt)
                    food_by_col[c] = fmt
                continue

            if h == SOLO_NAME_HEADER and fmt and not solo_name:
                solo_name = fmt
                continue

            if h in ALWAYS_HEADER:
                mapped = ALWAYS_HEADER[h]
                if mapped == "Food Preference":
                    if fmt:
                        meta.setdefault("Food Preference", fmt)
                        if not team_food_set:
                            food_by_col[c] = fmt
                            team_food_set = True
                else:
                    if fmt and not meta.get(mapped):
                        meta[mapped] = fmt
                continue

            if "member" in low:
                m = re.search(r"member\s*(2|3)", h, re.IGNORECASE)
                if m:
                    slot = int(m.group(1))
                    if "email" in low:
                        if slot in (2, 3) and fmt and slot not in member_emails:
                            member_emails[slot] = fmt
                    elif "contact" in low:
                        if slot in (2, 3) and fmt and slot not in member_contacts:
                            member_contacts[slot] = fmt
                    elif slot in members_by_slot and fmt:
                        members_by_slot[slot].append(fmt)

        if solo_name and str(meta.get("Team Size", "")).strip() == "1" \
                and not meta.get("Leader Name"):
            meta["Leader Name"] = solo_name

        clean = _clean_record(meta, members_by_slot, food_candidates, food_by_col,
                              member_emails, member_contacts)
        if clean is not None:
            out.append(clean)

    return out


def from_headers(values_with_headers):
    """values_with_headers: list of dicts from gspread's values_with_headers().
    Returns list of clean output rows (list of lists)."""
    out = []

    for record in values_with_headers:
        meta = {}
        members_by_slot = {n: [] for n in range(2, MAX_MEMBERS + 1)}
        member_emails = {}
        member_contacts = {}
        food_candidates = []
        food_by_col = {}
        solo_name = ""
        team_food_set = False
        import re

        for col_idx, (header, value) in enumerate(record.items()):
            if header is None:
                continue
            h = str(header)
            low = h.lower()
            fmt = _fmt(value)

            if "food preference" in low:
                if fmt:
                    food_candidates.append(fmt)
                    food_by_col[col_idx] = fmt
                continue

            if h == SOLO_NAME_HEADER and fmt and not solo_name:
                solo_name = fmt
                continue

            if h in ALWAYS_HEADER:
                mapped = ALWAYS_HEADER[h]
                if mapped == "Food Preference":
                    if fmt:
                        meta.setdefault("Food Preference", fmt)
                        if not team_food_set:
                            food_by_col[col_idx] = fmt
                            team_food_set = True
                else:
                    if fmt and not meta.get(mapped):
                        meta[mapped] = fmt
                continue

            if "member" in low:
                m = re.search(r"member\s*(2|3)", h, re.IGNORECASE)
                if m:
                    slot = int(m.group(1))
                    if "email" in low:
                        if slot in (2, 3) and fmt and slot not in member_emails:
                            member_emails[slot] = fmt
                    elif "contact" in low:
                        if slot in (2, 3) and fmt and slot not in member_contacts:
                            member_contacts[slot] = fmt
                    elif slot in members_by_slot and fmt:
                        members_by_slot[slot].append(fmt)

        if solo_name and str(meta.get("Team Size", "")).strip() == "1" \
                and not meta.get("Leader Name"):
            meta["Leader Name"] = solo_name

        clean = _clean_record(meta, members_by_slot, food_candidates, food_by_col,
                              member_emails, member_contacts)
        if clean is not None:
            out.append(clean)

    return out
