import os
import time

import pandas as pd

from config import OUTPUT_FOLDER
from processors.regex_processor import RegexProcessor
from processors.date_normalizer import DateNormalizer
from processors.copy_forward import CopyForwardRemover
from processors.whitespace_cleaner import WhitespaceCleaner
from processors.ocr_corrector import OCRCorrector
from processors.ner_redactor import NERRedactor
from processors.verifier import Verifier

from utils.audit_logger import AuditLogger


# Stage keys (used for tracing, ablation and the dashboard)
STAGES = [
    ("regex", "Regex pre-pass"),
    ("dates", "Date normalization"),
    ("copy_forward", "Copy-forward removal"),
    ("whitespace", "Whitespace cleaning"),
    ("ocr", "OCR correction"),
    ("ner", "NER + facility dictionary"),
]

REGEX_KEY_TO_LABEL = {
    "emails": "EMAIL", "phones": "PHONE", "mrns": "MRN",
    "dobs": "DOB", "ssns": "SSN",
}


def _clean(value):
    """NaN / None -> '' so downstream string checks are safe."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def load_dataset(path_or_buffer):
    """Read a notes CSV keeping identifiers as text (MRN 004521 must not become 4521)."""
    df = pd.read_csv(path_or_buffer, dtype=str, keep_default_na=False)
    if "is_scanned" in df.columns:
        df["is_scanned"] = df["is_scanned"].str.strip().str.lower().isin(["true", "1", "yes"])
    return df


class PHIDeidentificationPipeline:
    """
    Orchestrates the full de-identification workflow:

      Regex -> Dates -> Copy-forward -> Whitespace -> OCR -> NER
            -> Verification -> Audit logging
    """

    def __init__(self):

        self.regex_processor = RegexProcessor()
        self.date_normalizer = DateNormalizer()
        self.copy_forward_remover = CopyForwardRemover()
        self.whitespace_cleaner = WhitespaceCleaner()
        self.ocr_corrector = OCRCorrector()
        self.ner_redactor = NERRedactor()
        self.verifier = Verifier()
        self.audit_logger = AuditLogger()

        os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # =====================================
    # Core: process one piece of text
    # =====================================

    def process_text(
        self,
        text,
        is_scanned=False,
        metadata=None,
        note_id="adhoc",
        file_name="text_input",
        log=True,
        disabled=None,
    ):
        """
        Run the whole pipeline and return a full trace.

        metadata : dict with optional patient_name / mrn / dob / phone / email
        disabled : set of stage keys to skip (used for the ablation study)
        """
        disabled = set(disabled or [])
        metadata = metadata or {}
        original = _clean(text)
        current = original
        stages = []
        entities = []
        t_start = time.perf_counter()

        def timed(key, label, fn):
            nonlocal current
            t0 = time.perf_counter()
            before = current
            if key in disabled:
                info = {"skipped": True}
            else:
                current, info = fn(current)
                info["skipped"] = False
            stages.append({
                "key": key,
                "name": label,
                "before": before,
                "after": current,
                "ms": (time.perf_counter() - t0) * 1000,
                "info": info,
                "changed": before != current,
            })

        # ---- 1. Regex
        regex_counts = {}

        def _regex(t):
            nonlocal regex_counts
            out = self.regex_processor.process(t)
            regex_counts = out["redaction_counts"]
            entities.extend(out["matches"])
            return out["clean_text"], {"counts": out["redaction_counts"],
                                      "total": sum(out["redaction_counts"].values())}
        timed("regex", "Regex pre-pass", _regex)

        # ---- 2. Dates
        def _dates(t):
            new, changes = self.date_normalizer.normalize_with_report(t)
            return new, {"changes": changes, "total": len(changes)}
        timed("dates", "Date normalization", _dates)

        # ---- 3. Copy-forward
        def _cf(t):
            new, n = self.copy_forward_remover.remove_with_report(t)
            return new, {"blocks_removed": n, "total": n}
        timed("copy_forward", "Copy-forward removal", _cf)

        # ---- 4. Whitespace
        def _ws(t):
            new = self.whitespace_cleaner.clean(t)
            return new, {"chars_removed": len(t) - len(new), "total": 0}
        timed("whitespace", "Whitespace cleaning", _ws)

        # ---- 5. OCR (scanned notes only)
        def _ocr(t):
            new, applied = self.ocr_corrector.correct_with_report(t, is_scanned)
            return new, {"applied": applied, "is_scanned": bool(is_scanned),
                         "total": len(applied)}
        timed("ocr", "OCR correction", _ocr)

        # ---- 6. NER
        ner_out = {}

        def _ner(t):
            nonlocal ner_out
            ner_out = self.ner_redactor.redact(t)
            entities.extend({**e, "source": e["source"]} for e in ner_out["entities"])
            return ner_out["redacted_text"], {
                "breakdown": ner_out["breakdown"],
                "total": ner_out["entities_found"],
                "non_phi_dates_skipped": ner_out["non_phi_dates_skipped"],
            }
        timed("ner", "NER + facility dictionary", _ner)

        redacted_text = current
        regex_entities = sum(regex_counts.values()) if regex_counts else 0
        ner_entities = ner_out.get("entities_found", 0)
        entities_found = regex_entities + ner_entities

        # ---- 7. Verification
        t0 = time.perf_counter()
        verification = self.verifier.verify(
            redacted_text=redacted_text,
            patient_name=_clean(metadata.get("patient_name")),
            mrn=_clean(metadata.get("mrn")),
            dob=_clean(metadata.get("dob")),
            phone=_clean(metadata.get("phone")),
            email=_clean(metadata.get("email")),
            facility=_clean(metadata.get("facility")),
        )
        verify_ms = (time.perf_counter() - t0) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000

        breakdown = {}
        for e in entities:
            breakdown[e["label"]] = breakdown.get(e["label"], 0) + 1

        # ---- 8. Audit
        if log:
            self.audit_logger.log_event(
                note_id=note_id,
                file_name=file_name,
                entities_found=entities_found,
                verification_status=verification["status"],
                is_scanned=is_scanned,
                processing_ms=total_ms,
                issues=verification["issues"],
            )

        return {
            "note_id": note_id,
            "original_text": original,
            "redacted_text": redacted_text,
            "entities_found": entities_found,
            "entities": entities,
            "breakdown": breakdown,
            "regex_counts": regex_counts,
            "stages": stages,
            "verification": verification,
            "verification_status": verification["status"],
            "is_scanned": bool(is_scanned),
            "metadata": {k: _clean(v) for k, v in metadata.items()},
            "verify_ms": verify_ms,
            "total_ms": total_ms,
        }

    # =====================================
    # Process Single Record (dataset row)
    # =====================================

    def process_record(self, row, file_name="sample_notes.csv", log=True, disabled=None):

        metadata = {k: row.get(k, "") for k in
                    ("patient_name", "mrn", "dob", "phone", "email", "facility")}

        trace = self.process_text(
            row["note_text"],
            is_scanned=bool(row.get("is_scanned", False)),
            metadata=metadata,
            note_id=row.get("note_id", "adhoc"),
            file_name=file_name,
            log=log,
            disabled=disabled,
        )
        # Keep the original result keys and add the full trace
        return {
            "note_id": trace["note_id"],
            "original_text": trace["original_text"],
            "redacted_text": trace["redacted_text"],
            "entities_found": trace["entities_found"],
            "verification_status": trace["verification_status"],
            "trace": trace,
        }

    # =====================================
    # Process Whole Dataset
    # =====================================

    def process_dataset(self, dataset_path, save=True, progress=None, file_name=None,
                        log=True, disabled=None):
        """dataset_path may be a CSV path or a DataFrame."""
        df = dataset_path if isinstance(dataset_path, pd.DataFrame) else load_dataset(dataset_path)
        fname = file_name or (os.path.basename(dataset_path)
                              if isinstance(dataset_path, str) else "uploaded_dataframe")

        rows, traces = [], []
        n = len(df)
        for i, (_, row) in enumerate(df.iterrows(), start=1):
            res = self.process_record(row.to_dict(), file_name=fname, log=log, disabled=disabled)
            t = res.pop("trace")
            traces.append(t)
            res["is_scanned"] = t["is_scanned"]
            res["issues"] = "; ".join(t["verification"]["issues"])
            res["processing_ms"] = round(t["total_ms"], 2)
            for label, cnt in t["breakdown"].items():
                res[f"n_{label}"] = cnt
            rows.append(res)
            if progress:
                progress(i, n)

        out = pd.DataFrame(rows)
        count_cols = [c for c in out.columns if c.startswith("n_")]
        out[count_cols] = out[count_cols].fillna(0).astype(int)

        if save:
            out.to_csv(os.path.join(OUTPUT_FOLDER, "redacted_notes.csv"), index=False)

        return out, traces
