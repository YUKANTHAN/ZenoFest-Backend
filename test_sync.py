"""Offline test of the sync + reorganize logic using the local sample xlsx
as a stand-in for the raw Google Sheet (no real API calls)."""
import openpyxl
import app
import reorganize_logic as rl


class FakeWorksheet:
    def __init__(self, rows):
        self.rows = rows

    def get_all_records(self):
        if not self.rows:
            return []
        header = self.rows[0]
        records = []
        for r in self.rows[1:]:
            records.append({header[c]: r[c] for c in range(len(header))})
        return records

    def get_all_values(self):
        return self.rows

    def append_rows(self, rows, value_input_option=None):
        for r in rows:
            self.rows.append(r)

    def update(self, name, data):
        for i, r in enumerate(data):
            self.rows = [r] + self.rows[1:]


def build_raw_from_xlsx(path):
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    rows = []
    for r in range(1, ws.max_row + 1):
        rows.append([ws.cell(r, c).value for c in range(1, ws.max_column + 1)])
    return rows


def test():
    raw_rows = build_raw_from_xlsx(r"..\NEXYRA Registration (Responses).xlsx")
    raw_ws = FakeWorksheet(raw_rows)
    organized_ws = FakeWorksheet([list(rl.OUTPUT_HEADERS)])

    # Monkeypatch app.sync helpers to use fakes
    n, rows = app.sync(FakeClient(), raw_ws, organized_ws)
    assert n == 1, f"expected 1 append, got {n}"
    assert len(rows) == 1, f"expected 1 row info, got {len(rows)}"
    assert rows[0]["team_id"], f"expected a team_id, got {rows[0]['team_id']}"
    print(f"PASS: first sync appended 1 team row (team_id={rows[0]['team_id']})")

    # Second sync should dedup -> append 0
    n2, rows2 = app.sync(FakeClient(), raw_ws, organized_ws)
    assert n2 == 0, f"expected 0 on second sync, got {n2}"
    assert len(rows2) == 0, f"expected no rows on second sync, got {len(rows2)}"
    print("PASS: second sync appended nothing (dedup works)")

    print("\nFinal organized rows:")
    for r in organized_ws.rows:
        print("  ", r)


class FakeClient:
    def __init__(self):
        pass


if __name__ == "__main__":
    test()
