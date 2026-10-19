import pandas as pd
import pytest
from services.pipeline_service import PHIDeidentificationPipeline, load_dataset
import services.evaluation_service as ev


@pytest.fixture(scope="module")
def pipe():
    return PHIDeidentificationPipeline()


def test_ner_redacts_person_date_org_location(pipe):
    o = pipe.ner_redactor.redact("John Miller visited Riverside East Wing in Mumbai on 2026-03-03.")
    t = o["redacted_text"]
    assert "[PERSON]" in t and "[ORG]" in t and "[LOCATION]" in t and "[DATE]" in t
    assert "[[" not in t


def test_no_double_wrapped_placeholders(pipe):
    o = pipe.process_text("DOB: 1985-03-03 seen", log=False)
    assert "[[" not in o["redacted_text"]


def test_sample_dataset_passes_verification(pipe):
    out, traces = pipe.process_dataset("data/sample_notes.csv", save=False, log=False)
    assert (out["verification_status"] == "PASS").all()
    assert ev.overall_recall(ev.recall_by_type(ev.identifier_matrix(traces))) == 1.0


def test_facility_variant_is_caught(pipe):
    o = pipe.ner_redactor.redact("She attended the comm health annex on 2026-08-17.")
    assert "comm health annex" not in o["redacted_text"].lower()


def test_unknown_facility_is_flagged_not_silently_passed(pipe):
    """Verifier must still FAIL when a facility is genuinely not in the dictionary."""
    saved = list(pipe.ner_redactor.facilities)
    pipe.ner_redactor.facilities = [f for f in saved if "annex" not in f.lower()]
    try:
        out, _ = pipe.process_dataset("data/edge_case_notes.csv", save=False, log=False)
        assert "FAIL" in set(out["verification_status"])
    finally:
        pipe.ner_redactor.facilities = saved


def test_mrn_leading_zero_preserved():
    assert load_dataset("data/sample_notes.csv")["mrn"].iloc[0] == "004521"


def test_all_seven_requirements_pass(pipe):
    sc = ev.run_self_check(pipe)
    assert (sc["status"] == "PASS").all(), sc[sc["status"] != "PASS"]
