import io
import json
import os
import pickle
import tempfile
import time

import pandas as pd
import streamlit as st

from config import (AUDIT_LOG_PATH, DATASET_PATH, FACILITY_MODEL_PATH, PHI_COLORS,
                    SUPPORTED_FORMATS, TARGET_IDENTIFIER_RECALL)
from processors.file_reader import FileReader
from processors.date_normalizer import DateNormalizer
from services.pipeline_service import PHIDeidentificationPipeline, STAGES, load_dataset
import services.evaluation_service as ev
import utils.visuals as vz

# ==========================================
# Streamlit Config
# ==========================================

st.set_page_config(
    page_title="PHI De-Identification Studio",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.block-container { padding-top: 3.2rem; max-width: 1350px; }
.hero { background: linear-gradient(120deg,#3a0ca3 0%,#6c5ce7 45%,#00b4d8 100%);
  border-radius: 22px; padding: 30px 38px; color: white; margin-bottom: 18px;
  box-shadow: 0 12px 34px rgba(108,92,231,.35); position: relative; overflow: hidden; }
.hero:after { content:""; position:absolute; right:-60px; top:-60px; width:260px; height:260px;
  border-radius:50%; background:rgba(255,255,255,.10); }
.hero h1 { margin:0; font-size: 2.15rem; font-weight: 800; letter-spacing:-.5px; color:white; }
.hero p { margin:.4rem 0 0 0; opacity:.92; font-size:1.02rem; max-width: 900px; }
.pill { display:inline-block; padding:4px 12px; margin:10px 6px 0 0; border-radius:999px;
  background:rgba(255,255,255,.18); font-size:.78rem; font-weight:600; backdrop-filter: blur(4px); }
.kpi-row { display:grid; grid-template-columns: repeat(auto-fit,minmax(140px,1fr)); gap:14px; margin: 8px 0 18px 0; }
.kpi { background:white; border-radius:16px; padding:16px 18px; border-left:6px solid var(--c);
  box-shadow:0 4px 16px rgba(30,30,80,.07); transition: transform .15s; }
.kpi:hover { transform: translateY(-3px); }
.kpi-icon { font-size:1.3rem; }
.kpi-label { font-size:.74rem; text-transform:uppercase; letter-spacing:.8px; color:#7a7a9a; font-weight:600; }
.kpi-value { font-size:1.9rem; font-weight:800; color:var(--c); line-height:1.15; }
.kpi-sub { font-size:.78rem; color:#8b8ba7; }
.note-box { background:white; border:1px solid #e7e8f5; border-radius:14px; padding:16px 18px;
  line-height:1.9; font-size:.95rem; box-shadow:0 2px 10px rgba(30,30,80,.05); min-height:120px; }
.ph { display:inline-block; color:white; font-weight:700; font-size:.76rem; padding:2px 9px;
  border-radius:8px; margin:0 2px; }
.legend { margin: 4px 0 12px 0; }
.hl { padding:1px 3px; border-radius:4px; }
.badge { color:white; padding:3px 12px; border-radius:999px; font-weight:700; font-size:.8rem; }
.flow { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:10px 0 18px 0; }
.step { background:white; border-radius:14px; padding:10px 16px; font-weight:600; font-size:.85rem;
  box-shadow:0 3px 12px rgba(30,30,80,.08); border-top:4px solid var(--c); }
.arrow { color:#a0a0c0; font-size:1.2rem; font-weight:700; }
.section-title { font-size:1.15rem; font-weight:700; margin:22px 0 6px 0; color:#1b1b3a; }
.stTabs [data-baseweb="tab-list"] { gap:6px; background:white; padding:6px; border-radius:14px;
  box-shadow:0 3px 12px rgba(30,30,80,.06); }
.stTabs [data-baseweb="tab"] { border-radius:10px; padding:8px 16px; font-weight:600; }
.stTabs [aria-selected="true"] { background: linear-gradient(120deg,#6c5ce7,#00b4d8); color:white !important; }
[data-testid="stSidebar"] { background: linear-gradient(180deg,#1b1b3a 0%,#2d1b69 100%); }
[data-testid="stSidebar"] * { color:#f1f1ff !important; }
[data-testid="stSidebar"] input { color:#1b1b3a !important; }
div[data-testid="stMetric"] { background:white; border-radius:14px; padding:10px 14px;
  box-shadow:0 3px 12px rgba(30,30,80,.06); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ==========================================
# Load Components (cached: spaCy loads once)
# ==========================================

@st.cache_resource(show_spinner="Loading spaCy model & resources...")
def load_pipeline():
    return PHIDeidentificationPipeline()


pipeline = load_pipeline()
reader = FileReader()
logger = pipeline.audit_logger


def show(fig):
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def table(df, **kw):
    try:
        st.dataframe(df, width="stretch", **kw)
    except TypeError:
        st.dataframe(df, use_container_width=True, **kw)


def html(x):
    st.markdown(x, unsafe_allow_html=True)


def section(t):
    html(f'<div class="section-title">{t}</div>')


def to_excel(sheets):
    buf = io.BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            for name, df in sheets.items():
                df.to_excel(w, sheet_name=name[:31], index=False)
        return buf.getvalue()
    except Exception:
        return None


@st.cache_data
def bundled(name):
    path = {"sample": DATASET_PATH, "edge": "data/edge_case_notes.csv"}[name]
    return load_dataset(path)


# ==========================================
# Session state
# ==========================================

for k, v in {"single": None, "single_sig": None, "batch": None, "ablation": None,
             "selfcheck": None, "decisions": {}, "uploaded_batch": None}.items():
    st.session_state.setdefault(k, v)


def run_batch(df, name, log=True):
    bar = st.progress(0, text="Processing notes...")
    out, traces = pipeline.process_dataset(
        df, save=True, file_name=name, log=log,
        progress=lambda i, n: bar.progress(i / n, text=f"Processing note {i}/{n}"))
    bar.empty()
    st.session_state.batch = {"out": out, "traces": traces, "name": name, "df": df}
    st.session_state.ablation = None


# ==========================================
# Sidebar
# ==========================================

with st.sidebar:
    st.markdown("## 🏥 PHI Studio")
    st.caption("HIPAA Safe Harbor · first-draft redaction")

    st.header("Verification Metadata")
    st.caption("Known identifiers from the structured EHR fields - the verifier "
               "searches the redacted output for every one of them.")
    patient_name = st.text_input("Patient Name")
    mrn = st.text_input("MRN")
    dob = st.text_input("DOB")
    with st.expander("More identifiers (optional)"):
        phone_meta = st.text_input("Phone")
        email_meta = st.text_input("Email")
        facility_meta = st.text_input("Facility")

    st.header("Processing Options")
    scan_mode = st.radio(
        "OCR correction",
        ["Auto-detect", "Scanned note", "Natively typed"],
        help="OCR fixes are applied ONLY to scanned/historical notes - applying them "
             "to natively-typed text would introduce new errors.")
    write_audit = st.toggle("Write to audit log", value=True)

    st.header("Supported Formats")
    st.write(" · ".join(f.upper() for f in SUPPORTED_FORMATS))

    st.divider()
    st.caption("PHI colour legend")
    html(vz.legend_html())

metadata = {"patient_name": patient_name, "mrn": mrn, "dob": dob,
            "phone": phone_meta, "email": email_meta, "facility": facility_meta}

# ==========================================
# Hero
# ==========================================

html("""
<div class="hero">
  <h1>🏥 Healthcare PHI De-Identification Studio</h1>
  <p>Automated first-draft redaction of clinical notes before human review - a regex pre-pass and
  spaCy NER working together, a mandatory verification scan, a full audit trail and live quality evaluation.</p>
  <span class="pill">Regex + spaCy NER</span><span class="pill">OCR-aware</span>
  <span class="pill">Copy-forward safe</span><span class="pill">Verification scan</span>
  <span class="pill">Audit-ready</span><span class="pill">Human-in-the-loop</span>
</div>
""")

tab_redact, tab_batch, tab_eval, tab_review, tab_eda, tab_audit, tab_arch = st.tabs([
    "🛡️ Redact", "📦 Batch", "📊 Evaluation", "👩‍⚕️ Review Queue",
    "🔎 EDA Explorer", "📋 Audit Log", "🏗️ Architecture & Compliance"])

# ======================================================================
# TAB 1 - SINGLE DOCUMENT
# ======================================================================
with tab_redact:

    c1, c2 = st.columns([3, 2])
    with c1:
        uploaded_file = st.file_uploader("Upload File", type=SUPPORTED_FORMATS)
    with c2:
        pasted = st.text_area("...or paste a note", height=110,
                              placeholder="Paste clinical text here and press Redact")
        cc1, cc2 = st.columns(2)
        run_paste = cc1.button("Redact pasted text", type="primary")
        run_demo = cc2.button("Try a demo note")

    text, source_name, is_image = None, None, False

    if uploaded_file is not None:
        ext = os.path.splitext(uploaded_file.name)[1]
        raw = uploaded_file.getvalue()
        source_name, is_image = uploaded_file.name, ext.lower() in FileReader.IMAGE_EXT
        if ext.lower() == ".csv":
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
            tmp.write(raw); tmp.close()
            df_up = load_dataset(tmp.name)
            if "note_text" in df_up.columns:
                st.session_state.uploaded_batch = (uploaded_file.name, df_up)
                st.info(f"📦 **{uploaded_file.name}** has a `note_text` column ({len(df_up)} notes) "
                        "- open the **Batch** tab to process it as a dataset with full evaluation.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(raw)
            temp_path = tmp_file.name
        try:
            with st.spinner("Reading uploaded file..."):
                text = reader.read_file(temp_path)
        except Exception as e:
            st.error(f"Error: {e}")
    elif run_paste and pasted.strip():
        text, source_name = pasted, "pasted_text"
    elif run_demo:
        row = bundled("sample").iloc[2]
        text, source_name = row["note_text"], "demo_note"
        metadata = {k: row[k] for k in ("patient_name", "mrn", "dob", "phone", "email", "facility")}
        st.caption("Demo note loaded with its matching verification identifiers.")

    if text is not None:
        scanned = {"Auto-detect": is_image, "Scanned note": True, "Natively typed": False}[scan_mode]
        sig = (source_name, hash(text), scanned, tuple(sorted(metadata.items())), write_audit)
        if sig != st.session_state.single_sig:
            with st.status("Running de-identification pipeline...", expanded=False) as stt:
                st.session_state.single = pipeline.process_text(
                    text, is_scanned=scanned, metadata=metadata,
                    note_id="Uploaded_File" if uploaded_file else source_name,
                    file_name=source_name, log=write_audit)
                st.session_state.single_sig = sig
                stt.update(label="Pipeline complete", state="complete")

    t = st.session_state.single
    if t is None:
        html('<div class="note-box" style="text-align:center;color:#8b8ba7">'
             '⬆️ Upload a document, paste text or try the demo note to see the pipeline in action.</div>')
    else:
        v = t["verification"]
        ok = v["status"] == "PASS"
        compliance = 100 if ok else round(100 * sum(c["result"] == "PASS" for c in v["checks"])
                                          / max(1, v["checks_performed"]))
        words = len(t["original_text"].split())
        html(vz.kpi_row([
            ("Entities redacted", t["entities_found"], "regex + NER", "#6c5ce7", "🛡️"),
            ("Verification", v["status"], f"{v['checks_performed']} checks run",
             "#06d6a0" if ok else "#ef476f", "✅" if ok else "⚠️"),
            ("Compliance rate", f"{compliance}%", "identifier checks passed", "#00b4d8", "📈"),
            ("Words", words, f"{len(t['original_text'])} characters", "#ffb703", "📝"),
            ("Text retained", f"{100*ev.utility_retention(t):.0f}%", "research utility", "#8338ec", "🔬"),
            ("Latency", f"{t['total_ms']:.0f} ms", "end-to-end", "#ff7b00", "⚡"),
        ]))

        if not v["verified"]:
            st.warning("⚠️ No verification identifiers were supplied, so the safety-net scan had nothing to "
                       "check. Enter the patient's name / MRN / DOB in the sidebar - verification is "
                       "mandatory before data leaves the institution.")
        elif ok:
            st.success("PASS - none of the supplied identifiers were found in the redacted output.")
        else:
            st.error("FAIL - potential PHI remains. Manual review required.")

        section("Original vs. Redacted")
        html(vz.legend_html())
        left, right = st.columns(2)
        with left:
            st.caption("Original extracted text (detected PHI underlined)")
            html(vz.highlight_original(t["original_text"], t["entities"]))
            st.text_area("Original Text", t["original_text"], height=120, key="original_text",
                         label_visibility="collapsed")
        with right:
            st.caption("Redacted output")
            html(vz.highlight_redacted(t["redacted_text"]))
            st.text_area("Redacted Text", t["redacted_text"], height=120, key="redacted_text",
                         label_visibility="collapsed")

        section("Analytics")
        a, b, c = st.columns(3)
        with a:
            if t["breakdown"]:
                show(vz.donut_entities(t["breakdown"]))
            else:
                st.info("No PHI entities detected.")
        with b:
            show(vz.stage_impact(t["stages"]))
        with c:
            lat = pd.DataFrame([{"stage": s["name"], "avg_ms": s["ms"]} for s in t["stages"]]
                               + [{"stage": "Verification", "avg_ms": t["verify_ms"]}])
            show(vz.stage_time(lat))

        section("Verification Result")
        if v["checks"]:
            chk = pd.DataFrame(v["checks"])
            table(chk.style.map(lambda x: "background-color:#c9f5e5;font-weight:700" if x == "PASS"
                                else ("background-color:#ffd6dd;font-weight:700" if x == "FAIL" else ""),
                                subset=["result"]))
        for issue in v["issues"]:
            st.write(f"- ❌ {issue}")

        section("Pipeline Trace - watch the text change stage by stage")
        html('<div class="flow">' + '<span class="arrow">→</span>'.join(
            f'<span class="step" style="--c:{vz.PALETTE[i % 8]}">{s["name"]}'
            f'{" ✔" if s["changed"] else ""}</span>' for i, s in enumerate(t["stages"])) + "</div>")
        for i, s in enumerate(t["stages"], 1):
            with st.expander(f"{i}. {s['name']}  ·  {s['ms']:.1f} ms  ·  "
                             f"{'text changed' if s['changed'] else 'no change'}"):
                st.json(s["info"], expanded=False)
                st.text_area("Output after this stage", s["after"], height=90, key=f"stage_{i}")

        section("Detected Entities")
        ent_df = pd.DataFrame(t["entities"])
        if not ent_df.empty:
            table(ent_df[["label", "text", "source"]])

        section("Compliance Summary")
        st.caption("OCR/Text Extraction → Regex → Date Normalization → Copy-Forward Removal → "
                   "Whitespace Cleaning → OCR Correction → NER → Verification → Audit Logging")
        st.success("✅ PHI detection · ✅ Redaction · "
                   + ("✅ Verification passed" if ok else "❌ Verification failed - manual review")
                   + " · ✅ Audit log generated · ✅ Output ready for review")

        section("Download")
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇️ Redacted text", t["redacted_text"], "redacted_output.txt", "text/plain")
        report = {k: t[k] for k in ("note_id", "entities_found", "breakdown", "verification",
                                    "is_scanned", "total_ms")}
        d2.download_button("⬇️ JSON compliance report", json.dumps(report, indent=2, default=str),
                           "compliance_report.json", "application/json")
        d3.download_button("⬇️ Entities CSV", ent_df.to_csv(index=False) if not ent_df.empty else "",
                           "entities.csv", "text/csv")

# ======================================================================
# TAB 2 - BATCH
# ======================================================================
with tab_batch:
    section("Batch de-identification")
    st.caption("Process a whole corpus: rows need a `note_text` column; optional `patient_name, mrn, dob, "
               "phone, email, facility, is_scanned` columns enable per-note verification and evaluation.")
    options = ["Bundled sample corpus (5 notes)", "Bundled edge cases (3 notes)", "Both bundled sets"]
    if st.session_state.uploaded_batch:
        options.append(f"Uploaded: {st.session_state.uploaded_batch[0]}")
    choice = st.selectbox("Dataset", options)
    b1, b2 = st.columns([1, 3])
    go_batch = b1.button("🚀 Run batch", type="primary")
    log_batch = b2.toggle("Write batch results to audit log", value=True)

    if go_batch:
        if choice.startswith("Bundled sample"):
            run_batch(bundled("sample"), "sample_notes.csv", log_batch)
        elif choice.startswith("Bundled edge"):
            run_batch(bundled("edge"), "edge_case_notes.csv", log_batch)
        elif choice.startswith("Both"):
            run_batch(pd.concat([bundled("sample"), bundled("edge")], ignore_index=True),
                      "sample+edge", log_batch)
        else:
            run_batch(st.session_state.uploaded_batch[1], st.session_state.uploaded_batch[0], log_batch)

    B = st.session_state.batch
    if not B:
        st.info("Choose a dataset and press **Run batch**.")
    else:
        out, traces = B["out"], B["traces"]
        summ = ev.note_summary(traces)
        passed = int((summ["status"] == "PASS").sum())
        html(vz.kpi_row([
            ("Notes processed", len(out), B["name"], "#6c5ce7", "📄"),
            ("Entities redacted", int(out["entities_found"].sum()), f"{out['entities_found'].mean():.1f} per note", "#00b4d8", "🛡️"),
            ("Pass rate", f"{100*passed/len(out):.0f}%", f"{passed}/{len(out)} passed", "#06d6a0", "✅"),
            ("Need review", len(out) - passed, "failed verification", "#ef476f", "⚠️"),
            ("Scanned notes", int(summ["scanned"].eq("Scanned").sum()), "OCR-corrected", "#ffb703", "🖨️"),
            ("Avg latency", f"{summ['ms'].mean():.0f} ms", "per note", "#ff7b00", "⚡"),
        ]))
        ent_tbl = ev.entity_table(traces)
        c1, c2 = st.columns([1, 2])
        with c1:
            show(vz.status_pie(summ))
        with c2:
            show(vz.entities_stacked(ent_tbl))
        c3, c4 = st.columns(2)
        with c3:
            show(vz.density_scatter(summ))
        with c4:
            show(vz.source_sunburst(ev.source_contribution(traces)))

        section("Results")
        f = st.multiselect("Filter by status", ["PASS", "FAIL"], default=["PASS", "FAIL"])
        view = out[out["verification_status"].isin(f)]
        table(view[["note_id", "entities_found", "verification_status", "is_scanned", "issues",
                    "processing_ms", "redacted_text"]])

        pick = st.selectbox("Inspect a note", out["note_id"].tolist())
        tr = next(x for x in traces if x["note_id"] == pick)
        l, r = st.columns(2)
        l.caption("Original"); l.markdown(vz.highlight_original(tr["original_text"], tr["entities"]), unsafe_allow_html=True)
        r.caption("Redacted"); r.markdown(vz.highlight_redacted(tr["redacted_text"]), unsafe_allow_html=True)

        section("Download")
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇️ redacted_notes.csv", out.to_csv(index=False), "redacted_notes.csv", "text/csv")
        d2.download_button("⬇️ JSON", out.to_json(orient="records", indent=2), "redacted_notes.json",
                           "application/json")
        xl = to_excel({"redacted_notes": out, "entities": ent_tbl, "summary": summ})
        if xl:
            d3.download_button("⬇️ Excel workbook", xl, "phi_report.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ======================================================================
# TAB 3 - EVALUATION
# ======================================================================
with tab_eval:
    section("Evaluation dashboard")
    st.caption("Ground truth = the structured EHR identifiers of each note. For every identifier that appears "
               "in the original text we test whether it survives in the redacted output.")
    if not st.session_state.batch:
        if st.button("Run evaluation on the bundled corpora", type="primary"):
            run_batch(pd.concat([bundled("sample"), bundled("edge")], ignore_index=True),
                      "sample+edge", write_audit)
            st.rerun()
        st.info("Run a batch first (Batch tab) or use the button above.")
    else:
        B = st.session_state.batch
        if st.button("➕ Re-run on sample + edge cases (includes known-hard notes)"):
            run_batch(pd.concat([bundled("sample"), bundled("edge")], ignore_index=True),
                      "sample+edge", write_audit)
            st.rerun()
        B = st.session_state.batch
        traces = B["traces"]
        matrix = ev.identifier_matrix(traces)
        rec = ev.recall_by_type(matrix)
        overall = 100 * ev.overall_recall(rec)
        summ = ev.note_summary(traces)
        pass_rate = 100 * (summ["status"] == "PASS").mean()
        leaks = int(rec["leaked"].sum())

        g1, g2, g3 = st.columns(3)
        with g1:
            show(vz.gauge(overall, "Identifier recall", 100 * TARGET_IDENTIFIER_RECALL))
        with g2:
            show(vz.gauge(pass_rate, "Verification pass rate", 100))
        with g3:
            show(vz.gauge(summ["utility_pct"].mean(), "Text retained (utility)", None, steps=(30, 50)))
        if leaks:
            st.warning(f"{leaks} identifier(s) leaked past the automated pass - these are exactly what the "
                       "verification scan and the human reviewer exist to catch.")
        else:
            st.success("No known identifier leaked.")

        e1, e2 = st.columns(2)
        with e1:
            show(vz.recall_bar(rec, TARGET_IDENTIFIER_RECALL))
        with e2:
            show(vz.radar(rec))
        show(vz.leak_heatmap(matrix))

        e3, e4 = st.columns(2)
        with e3:
            show(vz.group_bars(ev.group_comparison(traces, matrix)))
        with e4:
            show(vz.stage_time(ev.stage_latency(traces)))

        section("Ablation study - what does each cleaning stage actually contribute?")
        st.caption("Each stage is switched off in turn and the whole corpus re-scored (audit log untouched).")
        if st.button("Run ablation study"):
            with st.spinner("Re-running pipeline with each stage disabled..."):
                st.session_state.ablation = ev.run_ablation(pipeline, B["df"])
        if st.session_state.ablation is not None:
            abl = st.session_state.ablation
            show(vz.ablation_fig(abl))
            table(abl.round(1))

        section("Date-format coverage (cleaning requirement #2)")
        cov = ev.date_format_coverage(pipeline)
        table(cov.style.map(lambda x: "background-color:#c9f5e5" if x == "Yes"
                            else ("background-color:#ffd6dd" if x == "MISSED" else ""), subset=["caught"]))

        section("Download evaluation")
        st.download_button("⬇️ Recall report (CSV)", rec.to_csv(index=False), "recall_by_identifier.csv", "text/csv")

# ======================================================================
# TAB 4 - REVIEW QUEUE
# ======================================================================
with tab_review:
    section("Human review queue")
    st.caption("The plan never removes the human reviewer - the reviewer spot-checks and corrects the "
               "automated draft. Failed notes are prioritised; misses become dictionary entries.")
    B = st.session_state.batch
    if not B:
        st.info("Run a batch to populate the queue.")
    else:
        out = B["out"]
        q = out[["note_id", "verification_status", "entities_found", "issues"]].copy()
        q["priority"] = q["verification_status"].map({"FAIL": "🔴 High", "PASS": "🟢 Spot-check"})
        q["decision"] = q["note_id"].map(lambda n: st.session_state.decisions.get(n, "Pending"))
        q = q.sort_values("priority")
        edited = st.data_editor(
            q, hide_index=True, key="review_editor",
            column_config={"decision": st.column_config.SelectboxColumn(
                "Reviewer decision", options=["Pending", "Approved", "Needs fix", "Rejected"])},
            disabled=["note_id", "verification_status", "entities_found", "issues", "priority"])
        st.session_state.decisions = dict(zip(edited["note_id"], edited["decision"]))
        cnt = edited["decision"].value_counts()
        html(vz.kpi_row([
            ("Pending", int(cnt.get("Pending", 0)), "", "#ffb703", "⏳"),
            ("Approved", int(cnt.get("Approved", 0)), "", "#06d6a0", "✅"),
            ("Needs fix", int(cnt.get("Needs fix", 0)), "", "#ef476f", "🛠️"),
            ("Rejected", int(cnt.get("Rejected", 0)), "", "#8338ec", "🚫"),
        ]))
        approved = out[out["note_id"].isin(edited.loc[edited["decision"] == "Approved", "note_id"])]
        st.download_button("⬇️ Export approved notes (safe to share)",
                           approved[["note_id", "redacted_text"]].to_csv(index=False),
                           "approved_notes.csv", "text/csv", disabled=approved.empty)

        section("Teach the system: expand the facility dictionary")
        st.caption("Edge cases the automated pass misses (variant spellings of facility names) are added here; "
                   "re-run the batch to see them caught. Persisted to `models/facility_dictionary.pkl`.")
        nf = st.text_input("New facility name / variant", placeholder="e.g. comm health annex")
        if st.button("➕ Add to dictionary") and nf.strip():
            with open(FACILITY_MODEL_PATH, "rb") as fh:
                fac = pickle.load(fh)
            if nf.strip() not in fac:
                fac.append(nf.strip())
                with open(FACILITY_MODEL_PATH, "wb") as fh:
                    pickle.dump(fac, fh)
                pipeline.ner_redactor.facilities = fac
                st.success(f"Added '{nf}'. Re-run the batch to apply it.")
            else:
                st.info("Already in the dictionary.")
        st.write("Current dictionary:", ", ".join(f"`{x}`" for x in pipeline.ner_redactor.facilities))

    section("Logged edge cases (feeds future dictionary / custom NER training)")
    edge = logger.read_edge_cases()
    if edge.empty:
        st.caption("No verification failures logged yet.")
    else:
        table(edge.tail(20))

# ======================================================================
# TAB 5 - EDA
# ======================================================================
with tab_eda:
    section("Exploratory data analysis")
    src = st.radio("Dataset", ["Sample corpus", "Edge cases", "Batch dataset in memory"], horizontal=True)
    if src == "Batch dataset in memory" and st.session_state.batch:
        eda_df = st.session_state.batch["df"].copy()
    else:
        eda_df = bundled("edge" if src == "Edge cases" else "sample").copy()
    eda_df["text_length"] = eda_df["note_text"].str.len()
    eda_df["word_count"] = eda_df["note_text"].str.split().str.len()
    if "is_scanned" in eda_df:
        eda_df["scanned"] = eda_df["is_scanned"].map({True: "Scanned", False: "Native"})
    html(vz.kpi_row([
        ("Records", len(eda_df), "", "#6c5ce7", "🗂️"),
        ("Columns", eda_df.shape[1], "incl. derived", "#00b4d8", "🧱"),
        ("Missing values", int(eda_df.isna().sum().sum()), "", "#06d6a0", "🕳️"),
        ("Duplicates", int(eda_df.duplicated().sum()), "", "#ffb703", "♊"),
        ("Avg words", f"{eda_df['word_count'].mean():.0f}", "per note", "#8338ec", "🔤"),
    ]))
    x1, x2, x3 = st.columns(3)
    if "scanned" in eda_df:
        with x1: show(vz.pie(eda_df["scanned"], "Scanned vs. native", ["#ef476f", "#00b4d8"]))
    with x2: show(vz.histogram(eda_df, "text_length", "Text length distribution"))
    if "facility" in eda_df:
        with x3:
            fc = eda_df["facility"].value_counts()
            show(vz.bar(fc.index.tolist(), fc.values.tolist(), "Facility distribution", "#06d6a0"))

    section("Why the pipeline looks the way it does - dirty-data census")
    import re as _re
    dn = DateNormalizer()
    fmt = {"MM/DD/YYYY": r"\b\d{1,2}/\d{1,2}/\d{4}\b", "D-M-YY": r"\b\d{1,2}-\d{1,2}-\d{2}\b",
           "YYYY-MM-DD": r"\b\d{4}-\d{2}-\d{2}\b", "Month D, YYYY": r"\b[A-Z][a-z]+ \d{1,2}, \d{4}\b"}
    fmt_counts = {k: int(eda_df["note_text"].apply(lambda s: len(_re.findall(p, s))).sum()) for k, p in fmt.items()}
    ocr_terms = {"Split names (Jo hn)": r"\b[A-Z][a-z]? [a-z]{1,2}\b(?= [A-Z])", "O/0 confusion (OO4521)": r"\b[A-Za-z]*\d*O+\d+\w*\b",
                 "Copy-forward blocks": r"(?i)copy-forward", "Line-break artifacts": r"\n"}
    ocr_counts = {k: int(eda_df["note_text"].apply(lambda s: len(_re.findall(p, s))).sum()) for k, p in ocr_terms.items()}
    phi_terms = {"E-mail": r"[\w.+-]+@[\w-]+\.[\w.]+", "Phone": r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|\b\d{10}\b", "MRN": r"(?i)MRN\s*[:#]?\s*\w+", "DOB": r"(?i)DOB\s*:"}
    phi_counts = {k: int(eda_df["note_text"].apply(lambda s: len(_re.findall(p, s))).sum()) for k, p in phi_terms.items()}
    y1, y2, y3 = st.columns(3)
    with y1: show(vz.bar(list(fmt_counts), list(fmt_counts.values()), "Date formats in the wild", "#ffb703"))
    with y2: show(vz.bar(list(ocr_counts), list(ocr_counts.values()), "Data-quality artefacts", "#ef476f"))
    with y3: show(vz.bar(list(phi_counts), list(phi_counts.values()), "Structured PHI occurrences", "#8338ec"))
    st.caption("Multiple date formats → normalization. OCR & line-break artefacts → correction & whitespace "
               "cleaning. Copy-forward → nested-quote stripping. Structured PHI → regex pre-pass.")

    section("Dataset preview")
    table(eda_df.drop(columns=["note_text"]).head(20))
    st.download_button("⬇️ EDA dataset", eda_df.to_csv(index=False), "eda_processed_dataset.csv", "text/csv")

# ======================================================================
# TAB 6 - AUDIT LOG
# ======================================================================
with tab_audit:
    section("📋 Audit Log Dashboard")
    audit = logger.read_log()
    if audit.empty:
        st.info("The audit log is empty - process a note first.")
    else:
        pc = int(audit["verification_status"].eq("PASS").sum())
        fc = int(audit["verification_status"].eq("FAIL").sum())
        html(vz.kpi_row([
            ("Total log entries", len(audit), "", "#6c5ce7", "🧾"),
            ("PASS records", pc, "", "#06d6a0", "✅"),
            ("FAIL records", fc, "", "#ef476f", "❌"),
            ("Entities logged", int(audit["entities_found"].sum()), "", "#00b4d8", "🛡️"),
            ("Files", audit["file_name"].nunique(), "distinct", "#ffb703", "📁"),
        ]))
        a1, a2 = st.columns([2, 1])
        with a1:
            show(vz.timeline(audit))
        with a2:
            show(vz.status_pie(audit.rename(columns={"verification_status": "status"})))
        flt = st.multiselect("Filter by status", ["PASS", "FAIL"], default=["PASS", "FAIL"], key="audit_flt")
        table(audit[audit["verification_status"].isin(flt)].tail(200).iloc[::-1])
        st.caption("Latest entries shown first.")
        d1, d2 = st.columns([1, 3])
        d1.download_button("⬇️ Download audit log", audit.to_csv(index=False), "audit_log.csv", "text/csv")
        with d2.expander("Danger zone"):
            if st.checkbox("I understand this permanently clears the audit trail") and st.button("Clear audit log"):
                logger.clear(); st.rerun()

# ======================================================================
# TAB 7 - ARCHITECTURE & COMPLIANCE
# ======================================================================
with tab_arch:
    section("System architecture")
    steps = ["Input file", "File reader / Tesseract OCR", "Regex pre-pass", "Date normalization",
             "Copy-forward removal", "Whitespace cleaning", "OCR correction (scanned only)",
             "spaCy NER + facility dictionary", "Verification scan", "Audit log", "Human review"]
    html('<div class="flow">' + '<span class="arrow">→</span>'.join(
        f'<span class="step" style="--c:{vz.PALETTE[i % 8]}">{s}</span>' for i, s in enumerate(steps)) + "</div>")
    st.markdown("""
**Why NER, not classification?** Nothing is being labelled Category A vs. B - the task is to *locate spans*
(a name, a date, a place) inside free text. But general-purpose NER alone is not enough: MRNs and phone numbers
are not named entities, so the regex pre-pass does real de-identification work alongside spaCy.
""")
    section("Live compliance self-check - the 7 data-cleaning requirements")
    if st.button("▶️ Run self-check", type="primary") or st.session_state.selfcheck is None:
        st.session_state.selfcheck = ev.run_self_check(pipeline)
    sc = st.session_state.selfcheck
    n_ok = int((sc["status"] == "PASS").sum())
    st.progress(n_ok / len(sc), text=f"{n_ok}/{len(sc)} requirements verified live")
    table(sc.style.map(lambda x: "background-color:#c9f5e5;font-weight:700" if x == "PASS"
                       else ("background-color:#ffd6dd;font-weight:700" if x == "FAIL" else ""), subset=["status"]))

    section("Expected outcomes")
    outcomes = pd.DataFrame([
        ["First-draft redaction applied, review becomes spot-checking", "Batch + Review Queue tabs"],
        ["Verification step is mandatory, catches what NER/regex miss", "Verifier (name parts, DOB formats, phone, MRN, facility)"],
        ["Cleaning steps are real de-identification work", "Ablation study on Evaluation tab"],
        ["Edge cases logged → expanded dictionary / custom NER", "logs/edge_cases.csv + 'Teach the system'"],
    ], columns=["Expected outcome", "Where it is delivered"])
    table(outcomes)
    st.caption(f"Audit log file: `{AUDIT_LOG_PATH}` · Synthetic data only - no real PHI is ever used.")
