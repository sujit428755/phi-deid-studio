# 🏥 Healthcare PHI De-Identification Studio

**Built by Sujit** · [GitHub](https://github.com/sujit428755) · MIT License

> Automated **first-draft redaction** of Emergency Department clinical notes to the **HIPAA Safe Harbor** standard,
> with a mandatory verification scan, a full audit trail, live quality evaluation, and a human-review workflow.

---

## 1. The problem

A regional hospital's outcomes-research office will share a multi-year corpus of ED clinical notes with a university
partner. The data-use agreement is non-negotiable: **every note must be fully de-identified** — no patient names, dates,
locations, phone numbers, medical record numbers or provider/organisation names — *before a file leaves the hospital*.

Today a small compliance team redacts by hand at a few minutes per note. The study needs **tens of thousands** of notes,
which would take months. The notes are also messy:

| Difficulty | Why it matters |
|---|---|
| ~¾ typed in the EHR, ~¼ **scanned historical** notes run through OCR | OCR introduces its own error pattern (`Jo hn`, `OO4521`) that native notes don't have |
| Several **date formats** (`03/03/2026`, `March 3, 2026`, `3-3-26`, `2026-03-03`) | NER misses two-digit years and dash-separated dates at a noticeably higher rate |
| EHR **copy-forward** quotes a prior visit in full | One patient's name can appear 2–3 times inside one "note" |
| PDF-to-text **line breaks** (`John\nMiller`) | Breaks a name across an entity span |
| Hospital-specific **facility names** (`Riverside East Wing`, `the Comm. Health annex`) | spaCy was never trained on them |
| MRNs and phone numbers | Not *named entities* at all — NER cannot find them |

**The plan is *not* to remove the human.** An automated spaCy-based pass produces a first draft; the compliance
team's job shifts from *redacting from scratch* to *spot-checking and correcting* — a much faster review.

## 2. Why Named Entity Recognition?

This is **not a classification problem** — nothing is labelled "Category A vs B". The task is to **locate and extract
spans** (a name, a date, a place) inside free-flowing narrative. That is exactly what NER does: it tags spans as
`PERSON`, `DATE`, `GPE` (location) or `ORG`, which are then replaced programmatically with `[PERSON]`, `[DATE]`, …

But general-purpose NER **alone is not enough**: MRNs and phone numbers aren't named entities, which is why the
cleaning steps lean heavily on **regex working alongside NER, not instead of it**.

## 3. Architecture

```
 Input file (TXT · CSV · JSON · PDF · DOCX · PNG · JPG · TIFF · BMP)
      │   FileReader  (+ Tesseract OCR for images)
      ▼
 ① Regex pre-pass ........ MRN · phone · e-mail · DOB · SSN      (exact-format PHI NER can't see)
 ② Date normalization .... 8+ written variants  ──►  YYYY-MM-DD
 ③ Copy-forward removal .. strip nested quoted prior notes
 ④ Whitespace cleaning ... re-join line-wrapped names / dates
 ⑤ OCR correction ........ ONLY for notes flagged as scanned
 ⑥ spaCy NER + facility dictionary ... PERSON · DATE · GPE · ORG
      ▼
 ⑦ Verification scan ..... search the output for the patient's REAL identifiers (from structured EHR fields)
 ⑧ Audit log ............. logs/audit_log.csv  (+ logs/edge_cases.csv for failures)
      ▼
 Human review queue  ──►  approved, shareable notes
```

Order matters and is deliberate: structured PHI is removed **before** free text ever reaches spaCy; dates are normalised
**before** NER relies on `DATE`; copy-forward blocks are stripped **before** NER so a second copy of the same name can't
survive; whitespace is fixed **before** NER because entity-span detection is sensitive to broken lines; and verification
runs on the **final output**, against the real identifiers — not just whatever NER happened to flag.

### The 7 data-cleaning requirements → implementation

| # | Requirement (from the use case) | Module | Verified live by |
|---|---|---|---|
| 1 | Regex pre-pass for MRN, phone, e-mail, structured DOB | `processors/regex_processor.py` | self-check #1 |
| 2 | Normalize inconsistent date formats before relying on spaCy | `processors/date_normalizer.py` + ISO safety-net in `ner_redactor.py` | self-check #2 (8/8 formats) |
| 3 | Strip nested copy-forward text before NER | `processors/copy_forward.py` | self-check #3 |
| 4 | OCR correction **only** for the scanned batch | `processors/ocr_corrector.py` + `models/ocr_rules.pkl` | self-check #4 |
| 5 | Standardize whitespace / line-wrap artifacts | `processors/whitespace_cleaner.py` | self-check #5 |
| 6 | Custom hospital facility dictionary supplementing ORG | `processors/ner_redactor.py` + `models/facility_dictionary.pkl` | self-check #6 |
| 7 | Post-redaction verification against known identifiers | `processors/verifier.py` | self-check #7 |

### Expected outcomes → where they are delivered

| Expected outcome | Delivered by |
|---|---|
| First-draft redaction applied; review becomes spot-checking | **Batch** + **Review Queue** tabs |
| Verification is mandatory — it catches what NER and regex miss | `Verifier` (name parts, DOB in every format, phone, MRN, facility, e-mail) |
| Cleaning steps do real de-identification work of their own | **Ablation study** (Evaluation tab) |
| Known misses (nicknames, unusual dates, misspellings) are logged and feed a bigger dictionary / custom NER | `logs/edge_cases.csv` + *“Teach the system”* in the Review Queue |

## 4. The dashboard (`streamlit run streamlitmain.py`)

| Tab | What it gives you |
|---|---|
| 🛡️ **Redact** | Upload any of 10 formats, paste text, or load a demo note. Side-by-side original (PHI underlined) vs. redacted (colour-coded placeholders), KPI cards, entity donut, per-stage impact & latency, verification checks table, an expandable **stage-by-stage pipeline trace**, and downloads (text · JSON compliance report · entities CSV). |
| 📦 **Batch** | Process the bundled corpora or your own CSV. Pass-rate donut, entities per note, redaction-density vs. utility scatter, detector-contribution sunburst, per-note inspector, CSV / JSON / Excel export. |
| 📊 **Evaluation** | Gauges (recall · pass-rate · utility), **recall by identifier** + radar, **identifier-removal heatmap**, scanned-vs-native comparison, latency, a live **ablation study** and **date-format coverage** proof. |
| 👩‍⚕️ **Review Queue** | Failed notes prioritised; reviewer decisions (Approved / Needs fix / Rejected); export of approved notes; add a variant to the facility dictionary and re-run to watch it get caught. |
| 🔎 **EDA Explorer** | Dataset health, scanned split, length distribution, facilities, and a *dirty-data census* (date formats, OCR artefacts, structured PHI) that justifies each cleaning step. |
| 📋 **Audit Log** | Timeline, PASS/FAIL split, filterable log, download, guarded clear. |
| 🏗️ **Architecture & Compliance** | Pipeline diagram and the **live 7-requirement self-check**. |

## 5. How quality is measured

Ground truth is the patient's **structured EHR fields** (name, MRN, DOB, phone, e-mail, facility). For each identifier
that actually appears in the original note we test whether it survives in the redacted output (whitespace- and
punctuation-tolerant, so `Jo hn Miller` counts as a leak of `John Miller`).

* **Identifier recall** — share of identifiers removed (target ≥ 99 %, configurable in `config.py`)
* **Verification pass rate** — share of notes with zero leaked identifiers
* **Text retained** — share of ordinary words kept; a proxy for over-redaction (research utility)
* **Ablation** — every stage switched off in turn, corpus re-scored
* **Date coverage** — each written date variant is pushed through the pipeline and must end as `[DATE]`

Current results on the bundled synthetic data: **sample corpus (5 notes) — 100 % recall, 5/5 PASS, 7/7 requirements
verified**. The 3-note **edge-case set** deliberately contains things the automated pass is known to struggle with
(a variant facility spelling, nicknames, an abbreviated wing name); there, note 102 is correctly **FAILED** by the
verifier and routed to the review queue — this is the safety net working as designed.

> ⚠️ Metrics come from a **tiny synthetic corpus**. They demonstrate the mechanism; they are not a claim about
> production accuracy. Run the same evaluation on a labelled sample of real notes before relying on it.

## 6. Project structure

```
├── streamlitmain.py            # the dashboard (all interactive features)
├── main.py                     # CLI runner
├── eda.py                      # EDA reports  ->  reports/
├── config.py                   # paths, colours, targets
├── create_pickle_files.py      # builds models/*.pkl
├── create_sample_data.py       # builds data/sample_notes.csv + edge_case_notes.csv
├── processors/                 # file_reader · regex_processor · date_normalizer · copy_forward
│                               # whitespace_cleaner · ocr_corrector · ner_redactor · verifier
├── services/
│   ├── pipeline_service.py     # orchestration, stage tracing, ablation hooks
│   └── evaluation_service.py   # recall, heatmap, ablation, date coverage, requirement self-check
├── utils/                      # audit_logger.py · visuals.py (Plotly charts + HTML helpers)
├── models/                     # facility_dictionary.pkl · ocr_rules.pkl
├── data/  logs/  reports/  docs/
└── tests/                      # 19 pytest tests
```

## 7. Setup & run

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python create_pickle_files.py        # once (builds models/*.pkl; not committed)
python create_sample_data.py         # once (skip if you already have data/sample_notes.csv)

streamlit run streamlitmain.py       # dashboard
python main.py                       # CLI batch run -> data/output/redacted_notes.csv
python eda.py                        # EDA reports
python -m pytest tests -q            # test-suite
```

OCR for images needs the [Tesseract](https://github.com/tesseract-ocr/tesseract) binary. It is auto-detected on `PATH`;
otherwise set `TESSERACT_CMD` (env var or `config.py`).

**Batch CSV format:** required `note_text`; optional `note_id, patient_name, mrn, dob, phone, email, facility,
is_scanned`. Identifiers are read as text so MRN `004521` keeps its leading zeros.

## 8. Design decisions & honest limitations

* **Human stays in the loop.** The output is a *draft*. The verifier can only check identifiers it is *given*; with no
  metadata the dashboard says verification had nothing to check rather than showing a false “100 %”.
* **OCR rules are scoped.** Applied only to scanned notes, and letter-confusion rules (`OO`→`00`) only inside tokens that
  already contain digits — so “Good” never becomes “G00d”.
* **Over-redaction control.** Relative dates (“yesterday”, “3 days ago”) and clinical abbreviations (ECG, ED, MRI) are kept;
  they aren't identifiers and removing them hurts research value.
* **Known gaps** (logged, not hidden): nicknames, unusual date phrasing (“the ninth of February”), abbreviated facility
  names (“RE Wing”), misspelled names. The route to fix them is the expanded dictionary or a custom-trained NER model.
* **Placeholders** use `[LOCATION]` for spaCy `GPE`; dates are fully removed (Safe Harbor), not just shifted.
* **Data** is synthetic — no real PHI is used anywhere in this repository.

---

Built by [Sujit](https://github.com/sujit428755). Licensed under MIT.
