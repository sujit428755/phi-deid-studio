import pytest
from processors.regex_processor import RegexProcessor
from processors.date_normalizer import DateNormalizer
from processors.copy_forward import CopyForwardRemover
from processors.whitespace_cleaner import WhitespaceCleaner
from processors.ocr_corrector import OCRCorrector
from processors.verifier import Verifier


def test_regex_structured_phi():
    o = RegexProcessor().process("MRN: 004521, (555) 019-2231, 555.882.1200, a@b.com, DOB: 03/03/1985, 123-45-6789")
    t = o["clean_text"]
    for tok in ("[MRN]", "[PHONE]", "[EMAIL]", "[DOB]", "[SSN]"):
        assert tok in t
    assert o["redaction_counts"]["phones"] == 2


@pytest.mark.parametrize("raw", ["03/03/2026", "March 3, 2026", "3-3-26", "2026-03-03", "3 Mar 2026"])
def test_date_normalizer(raw):
    assert DateNormalizer().normalize_text(f"seen {raw}.") == "seen 2026-03-03."


def test_copy_forward_removes_quote_but_keeps_new_visit():
    t = "Copy-forward note:\n'Michael Brown was seen 03/03/2026 and discharged.'\n\nNew visit:\nPatient reports improvement."
    r = CopyForwardRemover().remove_copy_forward(t)
    assert "Michael" not in r and "New visit" in r


def test_copy_forward_ignores_ordinary_apostrophes():
    t = "The patient's mother said the doctor's advice was helpful today."
    assert CopyForwardRemover().remove_copy_forward(t) == t


def test_whitespace():
    assert WhitespaceCleaner().clean("John\nMiller \t\t seen") == "John Miller seen"


def test_ocr_only_for_scanned():
    c = OCRCorrector()
    assert c.correct_text("Jo hn MRN OO4521", True) == "John MRN 004521"
    assert c.correct_text("Jo hn MRN OO4521", False) == "Jo hn MRN OO4521"
    assert "Good" in c.correct_text("Good result", True)          # no collateral damage


def test_verifier_pass_and_fail():
    v = Verifier()
    assert v.verify("[PERSON] [MRN]", "John Miller", "004521", "1985-03-03")["status"] == "PASS"
    assert v.verify("Mr Miller MRN 004521", "John Miller", "004521", "1985-03-03")["status"] == "FAIL"
    assert v.verify("born 03/03/1985", "", "", "1985-03-03")["status"] == "FAIL"     # DOB in another format
    assert v.verify("call 5550192231", "", "", "", phone="(555) 019-2231")["status"] == "FAIL"
