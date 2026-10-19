import csv
import os
from datetime import datetime

import pandas as pd

from config import AUDIT_LOG_PATH, EDGE_CASE_LOG_PATH


class AuditLogger:
    """
    Append-only audit trail (traceability + compliance reporting).

    Every processed note writes one row to logs/audit_log.csv.
    Notes that FAIL verification are also written to
    logs/edge_cases.csv so misses can later feed an expanded
    dictionary or a custom NER model.
    """

    COLUMNS = [
        "timestamp",
        "note_id",
        "file_name",
        "entities_found",
        "verification_status",
        "is_scanned",
        "processing_ms",
        "issues",
    ]

    EDGE_COLUMNS = ["timestamp", "note_id", "file_name", "issues"]

    def __init__(self, log_path=AUDIT_LOG_PATH, edge_path=EDGE_CASE_LOG_PATH):
        self.log_path = log_path
        self.edge_path = edge_path
        self._ensure_file(self.log_path, self.COLUMNS)
        self._ensure_file(self.edge_path, self.EDGE_COLUMNS)

    # ------------------------------------------------------
    def _ensure_file(self, path, columns):
        """Create the file, or migrate an older narrower schema."""
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)

        if not os.path.exists(path) or os.path.getsize(path) == 0:
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(columns)
            return

        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        header = rows[0] if rows else []
        if header == columns:
            return

        # Old / placeholder schema -> migrate, keeping whatever we can
        migrated = []
        for r in rows[1:]:
            rec = dict(zip(header, r))
            migrated.append([rec.get(c, "") for c in columns])
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(migrated)

    # ------------------------------------------------------
    def log_event(
        self,
        note_id,
        file_name,
        entities_found,
        verification_status,
        is_scanned=None,
        processing_ms=None,
        issues=None,
    ):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        issues_txt = "; ".join(issues) if issues else ""

        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                ts,
                note_id,
                file_name,
                entities_found,
                verification_status,
                "" if is_scanned is None else bool(is_scanned),
                "" if processing_ms is None else round(float(processing_ms), 2),
                issues_txt,
            ])

        if verification_status == "FAIL":
            with open(self.edge_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([ts, note_id, file_name, issues_txt])

    # ------------------------------------------------------
    def read_log(self):
        try:
            df = pd.read_csv(self.log_path)
        except Exception:
            return pd.DataFrame(columns=self.COLUMNS)
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        return df

    def read_edge_cases(self):
        try:
            return pd.read_csv(self.edge_path)
        except Exception:
            return pd.DataFrame(columns=self.EDGE_COLUMNS)

    def clear(self):
        for p, cols in ((self.log_path, self.COLUMNS), (self.edge_path, self.EDGE_COLUMNS)):
            with open(p, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(cols)
