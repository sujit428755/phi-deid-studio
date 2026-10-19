import pickle
import re
import spacy

from config import FACILITY_MODEL_PATH


class NERRedactor:
    """
    Stage 6 - spaCy NER (PERSON / DATE / GPE / ORG) supplemented by
    (a) a hospital-specific facility dictionary and
    (b) a regex safety-net for canonical ISO dates, because spaCy's DATE
        label is known to miss dash-separated / two-digit-year styles.

    Overlapping detections are resolved (dictionary > regex > spaCy, then
    longest span) so replacement never corrupts the text.
    """

    LABEL_MAP = {
        "PERSON": "[PERSON]",
        "DATE": "[DATE]",
        "ORG": "[ORG]",
        "GPE": "[LOCATION]",
    }

    PRIORITY = {"dictionary": 3, "regex": 2, "spacy": 1}

    # Relative / duration expressions are not identifying dates
    NON_PHI_DATE = re.compile(
        r"^(today|yesterday|tomorrow|tonight|now|daily|weekly|monthly|"
        r"(the\s+)?(last|next|past|previous)\s+\w+|"
        r"\d+\s*[-\s]?(second|minute|hour|day|week|month)s?(\s+ago)?|"
        r"(a|an|one|two|three|four|five|six|seven|several)\s+"
        r"(second|minute|hour|day|week|month)s?(\s+ago)?)$",
        re.IGNORECASE,
    )

    ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
    PLACEHOLDER = re.compile(r"\[[A-Z_]+\]")

    # Common clinical abbreviations spaCy's news-trained model mistakes for
    # organisations / people / places. Not PHI, so keep them for research utility.
    CLINICAL_ALLOWLIST = {
        "ecg", "ekg", "ed", "er", "icu", "ehr", "emr", "mri", "ct", "cbc",
        "bp", "hr", "iv", "copd", "hiv", "hpi", "pmh", "rx", "dx", "hx",
        "x-ray", "xray", "covid", "covid-19", "ent", "gi", "nsaid", "nsaids",
    }

    def __init__(self):

        self.nlp = spacy.load("en_core_web_sm")

        with open(FACILITY_MODEL_PATH, "rb") as file:
            self.facilities = pickle.load(file)

    # ------------------------------------------------------
    @staticmethod
    def _facility_pattern(facility):
        """
        Case- and punctuation-insensitive matcher for a dictionary entry.
        'Comm. Health annex' also matches 'comm health annex',
        'Comm Health Annex' and 'COMM.  HEALTH-ANNEX'.
        """
        tokens = re.findall(r"[A-Za-z0-9]+", facility)
        if not tokens:
            return re.compile(re.escape(facility), re.IGNORECASE)
        body = r"[\W_]+".join(re.escape(t) for t in tokens)
        return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)

    # ------------------------------------------------------
    def _collect(self, text):
        cands = []
        skipped = 0

        # Spans already turned into [PLACEHOLDER] tokens by the regex stage
        ph_spans = [(m.start(), m.end()) for m in self.PLACEHOLDER.finditer(text)]

        doc = self.nlp(text)
        for ent in doc.ents:
            placeholder = self.LABEL_MAP.get(ent.label_)
            if not placeholder:
                continue
            if "[" in ent.text or "]" in ent.text:
                continue  # already-redacted token
            if any(ent.start_char < pe and ent.end_char > ps for ps, pe in ph_spans):
                continue  # overlaps an existing placeholder (avoids "[[ORG]]")
            if ent.text.strip().lower() in self.CLINICAL_ALLOWLIST:
                skipped += 1
                continue
            if ent.label_ == "DATE" and self.NON_PHI_DATE.match(ent.text.strip()):
                skipped += 1
                continue
            cands.append((ent.start_char, ent.end_char, placeholder, ent.text, "spacy"))

        for m in self.ISO_DATE.finditer(text):
            cands.append((m.start(), m.end(), "[DATE]", m.group(0), "regex"))

        for facility in self.facilities:
            for m in self._facility_pattern(facility).finditer(text):
                cands.append((m.start(), m.end(), "[ORG]", m.group(0), "dictionary"))

        return cands, skipped

    @staticmethod
    def _resolve(cands, priority):
        """Greedy non-overlapping selection: priority, then span length."""
        ordered = sorted(
            cands,
            key=lambda c: (-priority[c[4]], -(c[1] - c[0]), c[0]),
        )
        kept = []
        for c in ordered:
            if all(c[1] <= k[0] or c[0] >= k[1] for k in kept):
                kept.append(c)
        return kept

    # ------------------------------------------------------
    def redact(self, text):

        cands, skipped = self._collect(text)
        kept = self._resolve(cands, self.PRIORITY)

        # Replace from the end so earlier character offsets stay valid
        kept.sort(key=lambda c: c[0], reverse=True)

        redacted_text = text
        for start, end, label, _, _ in kept:
            redacted_text = redacted_text[:start] + label + redacted_text[end:]

        entities = [
            {
                "text": t,
                "label": lbl.strip("[]"),
                "start": s,
                "end": e,
                "source": src,
            }
            for s, e, lbl, t, src in sorted(kept, key=lambda c: c[0])
        ]

        breakdown = {}
        for ent in entities:
            breakdown[ent["label"]] = breakdown.get(ent["label"], 0) + 1

        return {
            "redacted_text": redacted_text,
            "entities_found": len(entities),
            "breakdown": breakdown,
            "entities": entities,
            "non_phi_dates_skipped": skipped,
        }
