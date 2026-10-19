# ==========================================================
# Central configuration for the PHI De-Identification System
# ==========================================================

# ---------- Paths (original settings, unchanged) ----------
DATASET_PATH = "data/sample_notes.csv"

FACILITY_MODEL_PATH = "models/facility_dictionary.pkl"

OCR_RULES_PATH = "models/ocr_rules.pkl"

AUDIT_LOG_PATH = "logs/audit_log.csv"

OUTPUT_FOLDER = "data/output"

# ---------- Additional paths ----------
EDGE_CASE_LOG_PATH = "logs/edge_cases.csv"

REPORTS_FOLDER = "reports"

CHARTS_FOLDER = "reports/charts"

# ---------- Tesseract (optional override) ----------
# Leave as None to auto-detect. On Windows set the full path, or export
# the TESSERACT_CMD environment variable.
TESSERACT_CMD = None

# ---------- Supported upload formats ----------
SUPPORTED_FORMATS = [
    "txt", "csv", "json", "pdf", "docx",
    "png", "jpg", "jpeg", "tiff", "bmp",
]

# ---------- PHI label -> colour (used across the dashboard) ----------
PHI_COLORS = {
    "PERSON": "#ef476f",
    "DATE": "#ffb703",
    "ORG": "#118ab2",
    "LOCATION": "#06d6a0",
    "EMAIL": "#8338ec",
    "PHONE": "#fb5607",
    "MRN": "#d00000",
    "DOB": "#ff006e",
    "SSN": "#3a0ca3",
}

# ---------- Compliance targets shown in the dashboard ----------
TARGET_IDENTIFIER_RECALL = 0.99   # share of known identifiers removed
TARGET_PASS_RATE = 1.00           # every note must pass verification
