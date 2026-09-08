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

# Exact header text -> output field, for always-present columns.
ALWAYS_HEADER = {
    "Timestamp": "Timestamp",
    "Email Address": "Email",
    "Team Name": "Team Name",
    "College Name": "College",
    "Department & Year": "Department & Year",
    "Team Leader Name": "Leader Name",
    "Team Leader Contact (Phone Number)": "Leader Contact",
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
    "Timestamp", "Email", "Team Name", "College", "Department & Year",
    "Leader Name", "Leader Contact", "Team Size",
    "Tech Event", "NonTech Event", "Food Preference", "Payment Screenshot",
]
OUTPUT_HEADERS = OUTPUT_ORDER_BEFORE_MEMBERS + [
    f"Member {n} Name" for n in range(2, MAX_MEMBERS + 1)
] + [
    f"Member {n} Contact" for n in range(2, MAX_MEMBERS + 1)
]


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


def _clean_record(meta, members_by_slot, food_candidates):
    if not meta.get("Food Preference") and food_candidates:
        meta["Food Preference"] = food_candidates[0]

    if not meta.get("Team Name") and not meta.get("Timestamp"):
        return None

    row = [meta.get(k, "") for k in OUTPUT_ORDER_BEFORE_MEMBERS]
    for n in range(2, MAX_MEMBERS + 1):
        row.append(_first_nonempty(members_by_slot[n]))
    for n in range(2, MAX_MEMBERS + 1):
        row.append("")  # contacts not mapped yet
    return row


def from_matrix(headers, rows):
    """headers: list of (possibly duplicated) header strings.
    rows: list of data rows (aligned to headers by position).
    Returns list of clean output rows."""
    import re

    out = []
    for row in rows:
        meta = {}
        members_by_slot = {n: [] for n in range(2, MAX_MEMBERS + 1)}
        food_candidates = []

        for c, header in enumerate(headers):
            if header is None:
                continue
            h = str(header)
            low = h.lower()
            value = row[c] if c < len(row) else None
            fmt = _fmt(value)

            if h in ALWAYS_HEADER:
                mapped = ALWAYS_HEADER[h]
                if mapped == "Food Preference":
                    if fmt:
                        meta.setdefault("Food Preference", fmt)
                else:
                    # Keep first non-empty across duplicate headers
                    if fmt and not meta.get(mapped):
                        meta[mapped] = fmt
                continue

            if "food preference" in low:
                if fmt:
                    food_candidates.append(fmt)
                continue

            if "member" in low:
                m = re.search(r"member\s*([2-4])", h, re.IGNORECASE)
                if m:
                    slot = int(m.group(1))
                    if slot in members_by_slot and fmt:
                        members_by_slot[slot].append(fmt)

        clean = _clean_record(meta, members_by_slot, food_candidates)
        if clean is not None:
            out.append(clean)

    return out


def from_headers(values_with_headers):
    """values_with_headers: list of dicts from gspread's values_with_headers().
    Returns list of clean output rows (list of lists)."""
    out = []

    for record in values_with_headers:
        meta = {}
        members_by_slot = {n: [] for n in range(2, MAX_MEMBERS + 1)}  # slot -> names
        food_candidates = []
        import re

        for header, value in record.items():
            if header is None:
                continue
            h = str(header)
            low = h.lower()

            # Always-on exact fields
            if h in ALWAYS_HEADER:
                mapped = ALWAYS_HEADER[h]
                fmt = _fmt(value)
                if mapped == "Food Preference":
                    if fmt:
                        meta.setdefault("Food Preference", fmt)
                else:
                    if fmt and not meta.get(mapped):
                        meta[mapped] = fmt
                continue

            # Duplicate "Food Preference ..." variants -> keep first non-empty
            if "food preference" in low:
                if _fmt(value):
                    food_candidates.append(_fmt(value))
                continue

            # Member name detection: header like "Member 2 Name", "Member 3 Name 3"
            if "member" in low:
                m = re.search(r"member\s*([2-4])", h, re.IGNORECASE)
                if m:
                    slot = int(m.group(1))
                    if slot in members_by_slot and _fmt(value):
                        members_by_slot[slot].append(_fmt(value))

        clean = _clean_record(meta, members_by_slot, food_candidates)
        if clean is not None:
            out.append(clean)

    return out
