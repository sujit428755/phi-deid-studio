"""
Evaluation layer - turns pipeline traces into measurable quality metrics.

Ground truth comes from the structured EHR fields of each note
(name, MRN, DOB, phone, e-mail, facility). For every identifier that
actually appears in the original text we test whether it survives in the
redacted output; that gives a real per-identifier recall, not a guess.
"""
import re

import pandas as pd
from dateutil import parser

from services.pipeline_service import STAGES

ID_TYPES = ["Name", "MRN", "DOB", "Phone", "Email", "Facility"]


def _squash(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _dob_forms(dob):
    forms = {_squash(dob)}
    try:
        d = parser.parse(str(dob))
        for f in ("%Y-%m-%d", "%m/%d/%Y", "%-m/%-d/%Y", "%m/%d/%y", "%-m-%-d-%y", "%B %-d, %Y"):
            forms.add(_squash(d.strftime(f)))
    except Exception:
        pass
    return {f for f in forms if f}


def _present(kind, meta, text):
    """Is this identifier found in `text`? (whitespace/punctuation tolerant)"""
    sq = _squash(text)
    val = meta.get(kind_key(kind), "")
    if not str(val).strip():
        return None                                   # no ground truth
    if kind == "DOB":
        return any(f in sq for f in _dob_forms(val))
    if kind == "Phone":
        digits = re.sub(r"\D", "", val)[-10:]
        return digits in re.sub(r"\D", "", text)
    if kind == "MRN":
        return _squash(val).lstrip("mrn") in sq if len(_squash(val)) >= 4 else None
    return _squash(val) in sq


def kind_key(kind):
    return {"Name": "patient_name", "MRN": "mrn", "DOB": "dob",
            "Phone": "phone", "Email": "email", "Facility": "facility"}[kind]


def identifier_matrix(traces):
    """
    Per-note x identifier outcome:
      'removed' | 'LEAKED' | 'n/a' (identifier never appeared in the original)
    """
    rows = []
    for t in traces:
        meta = t["metadata"]
        row = {"note_id": t["note_id"]}
        for kind in ID_TYPES:
            before = _present(kind, meta, t["original_text"])
            after = _present(kind, meta, t["redacted_text"])
            if before is None or (not before and kind != "Name"):
                row[kind] = "n/a"
            elif after:
                row[kind] = "LEAKED"
            else:
                row[kind] = "removed"
        rows.append(row)
    return pd.DataFrame(rows)


def recall_by_type(matrix):
    out = []
    for kind in ID_TYPES:
        col = matrix[kind]
        removed = int((col == "removed").sum())
        leaked = int((col == "LEAKED").sum())
        total = removed + leaked
        out.append({
            "identifier": kind,
            "present": total,
            "removed": removed,
            "leaked": leaked,
            "recall": (removed / total) if total else 1.0,
        })
    return pd.DataFrame(out)


def overall_recall(recall_df):
    total = recall_df["present"].sum()
    return (recall_df["removed"].sum() / total) if total else 1.0


def utility_retention(trace):
    """Share of ordinary (non-placeholder) words kept - proxy for over-redaction."""
    orig = len(trace["original_text"].split())
    kept = len([w for w in trace["redacted_text"].split() if not re.fullmatch(r"\W*\[[A-Z_]+\]\W*", w)])
    return kept / orig if orig else 1.0


def note_summary(traces):
    rows = []
    for t in traces:
        rows.append({
            "note_id": t["note_id"],
            "scanned": "Scanned" if t["is_scanned"] else "Native",
            "entities": t["entities_found"],
            "status": t["verification_status"],
            "words": len(t["original_text"].split()),
            "density_pct": 100 * t["entities_found"] / max(1, len(t["original_text"].split())),
            "utility_pct": 100 * utility_retention(t),
            "ms": t["total_ms"],
        })
    return pd.DataFrame(rows)


def source_contribution(traces):
    """Which detector produced each entity: regex / spacy / dictionary."""
    rows = []
    for t in traces:
        for e in t["entities"]:
            rows.append({"note_id": t["note_id"], "label": e["label"], "source": e["source"]})
    return pd.DataFrame(rows, columns=["note_id", "label", "source"])


def entity_table(traces):
    rows = []
    for t in traces:
        for e in t["entities"]:
            rows.append({"note_id": t["note_id"], "label": e["label"],
                         "text": e["text"], "source": e["source"]})
    return pd.DataFrame(rows, columns=["note_id", "label", "text", "source"])


def stage_latency(traces):
    acc = {}
    for t in traces:
        for s in t["stages"]:
            acc.setdefault(s["name"], []).append(s["ms"])
        acc.setdefault("Verification", []).append(t["verify_ms"])
    return pd.DataFrame(
        [{"stage": k, "avg_ms": sum(v) / len(v)} for k, v in acc.items()]
    )


def group_comparison(traces, matrix):
    df = note_summary(traces).merge(matrix, on="note_id")
    rows = []
    for grp, g in df.groupby("scanned"):
        removed = sum((g[k] == "removed").sum() for k in ID_TYPES)
        leaked = sum((g[k] == "LEAKED").sum() for k in ID_TYPES)
        rows.append({
            "group": grp,
            "notes": len(g),
            "avg_entities": g["entities"].mean(),
            "pass_rate": 100 * (g["status"] == "PASS").mean(),
            "recall": 100 * removed / (removed + leaked) if (removed + leaked) else 100,
            "utility_pct": g["utility_pct"].mean(),
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Ablation: switch each pipeline stage off in turn and re-measure.
# Shows what every cleaning requirement actually contributes.
# ----------------------------------------------------------------------
def run_ablation(pipeline, df):
    from processors.date_normalizer import DateNormalizer
    date_rx = DateNormalizer()._combined

    def score(disabled):
        _, tr = pipeline.process_dataset(df, save=False, log=False, disabled=disabled)
        m = identifier_matrix(tr)
        r = recall_by_type(m)
        return {
            "recall_pct": 100 * overall_recall(r),
            "pass_pct": 100 * sum(t["verification_status"] == "PASS" for t in tr) / len(tr),
            "leaks": int(r["leaked"].sum()),
            "residual_dates": sum(len(date_rx.findall(t["redacted_text"])) for t in tr),
            "avg_entities": sum(t["entities_found"] for t in tr) / len(tr),
        }

    rows = [{"configuration": "Full pipeline", **score(None)}]
    for key, label in STAGES:
        rows.append({"configuration": f"without {label}", **score({key})})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Date-format coverage (cleaning requirement #2): prove every written
# variant of the same date is actually caught, rather than assuming.
# ----------------------------------------------------------------------
DATE_VARIANTS = [
    "03/03/2026", "March 3, 2026", "3-3-26", "2026-03-03",
    "3 Mar 2026", "Mar 3rd, 2026", "03-03-2026", "3/3/26",
]


def date_format_coverage(pipeline):
    rows = []
    for v in DATE_VARIANTS:
        out = pipeline.process_text(f"Patient seen on {v} for review.", log=False)
        normalized = next((c["normalized"] for s in out["stages"] if s["key"] == "dates"
                           for c in s["info"].get("changes", [])), "-")
        caught = "[DATE]" in out["redacted_text"] and v not in out["redacted_text"]
        rows.append({"format": v, "normalized_to": normalized,
                     "caught": "Yes" if caught else "MISSED",
                     "output": out["redacted_text"]})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------
# Live compliance self-check: one executable test per cleaning requirement
# in the use-case document. Used by the dashboard and by the test-suite.
# ----------------------------------------------------------------------
def run_self_check(pipeline):
    checks = []

    def add(req, module, fn):
        try:
            ok, detail = fn()
        except Exception as exc:                       # pragma: no cover
            ok, detail = False, f"error: {exc}"
        checks.append({"requirement": req, "module": module,
                       "status": "PASS" if ok else "FAIL", "evidence": detail})

    def r1():
        o = pipeline.process_text("MRN: 004521 call (555) 019-2231 mail a.b@x.com", log=False)
        t = o["redacted_text"]
        return all(k in t for k in ("[MRN]", "[PHONE]", "[EMAIL]")), t

    def r2():
        cov = date_format_coverage(pipeline)
        n = int((cov["caught"] == "Yes").sum())
        return n == len(cov), f"{n}/{len(cov)} date formats caught & normalised"

    def r3():
        txt = "Copy-forward note:\n'John Miller was seen 03/03/2026 and discharged.'\n\nNew visit: stable."
        o = pipeline.process_text(txt, log=False, metadata={"patient_name": "John Miller"})
        return "Miller" not in o["redacted_text"] and "New visit" in o["redacted_text"], o["redacted_text"]

    def r4():
        s = pipeline.process_text("Jo hn Miller MRN OO4521", is_scanned=True, log=False)
        n = pipeline.process_text("Jo hn Miller MRN OO4521", is_scanned=False, log=False)
        ocr_s = [x for x in s["stages"] if x["key"] == "ocr"][0]["changed"]
        ocr_n = [x for x in n["stages"] if x["key"] == "ocr"][0]["changed"]
        return ocr_s and not ocr_n, f"scanned changed={ocr_s}, native changed={ocr_n}"

    def r5():
        o = pipeline.process_text("Seen by John\nMiller today.", log=False)
        return "Miller" not in o["redacted_text"], o["redacted_text"]

    def r6():
        o = pipeline.process_text("Visit at Riverside East Wing and the Comm. Health annex.", log=False)
        return o["redacted_text"].count("[ORG]") >= 2, o["redacted_text"]

    def r7():
        v = pipeline.verifier.verify("John Miller MRN 004521", "John Miller", "004521", "1985-03-03")
        ok = pipeline.verifier.verify("[PERSON] [MRN]", "John Miller", "004521", "1985-03-03")
        return v["status"] == "FAIL" and ok["status"] == "PASS", f"leak->{v['status']}, clean->{ok['status']}"

    add("1. Regex pre-pass for MRN / phone / e-mail / DOB", "regex_processor.py", r1)
    add("2. Normalize inconsistent date formats", "date_normalizer.py", r2)
    add("3. Strip nested copy-forward text", "copy_forward.py", r3)
    add("4. OCR fixes for scanned-batch notes only", "ocr_corrector.py", r4)
    add("5. Standardize whitespace / line-wraps", "whitespace_cleaner.py", r5)
    add("6. Custom facility-name dictionary for ORG", "ner_redactor.py + facility_dictionary.pkl", r6)
    add("7. Post-redaction verification vs. known identifiers", "verifier.py", r7)
    return pd.DataFrame(checks)
