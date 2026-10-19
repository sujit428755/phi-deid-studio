import re


class RegexProcessor:
    """
    Stage 1 - structured PHI that spaCy was never trained to recognise
    (MRN, phone, e-mail, DOB, SSN). Exact-format patterns, run BEFORE NER.
    """

    def __init__(self):

        self.email_pattern = re.compile(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        )

        # (555) 019-2231 | 555-019-2231 | 555.019.2231 | +1 555 019 2231 | 5550192231
        self.phone_pattern = re.compile(
            r"(?<![\w-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\w-])"
            r"|(?<!\d)\d{10}(?!\d)"
        )

        # MRN: 004521 | MRN 004521 | MRN#004521  (OCR variants like OO4521 included)
        self.mrn_pattern = re.compile(
            r"MRN\s*[:#]?\s*[A-Za-z0-9]+",
            re.IGNORECASE
        )

        # DOB: 03/03/1985 | DOB: 1985-03-03 | DOB: March 3, 1985
        self.dob_pattern = re.compile(
            r"DOB\s*:\s*(?:[A-Za-z]+\.?\s+\d{1,2},?\s*\d{4}|[\w/\-]+)",
            re.IGNORECASE
        )

        self.ssn_pattern = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")

        # (count key, pattern, placeholder, entity label) - order matters:
        # MRN/DOB first so a 10-digit MRN is never mistaken for a phone.
        self._rules = [
            ("mrns", self.mrn_pattern, "[MRN]", "MRN"),
            ("dobs", self.dob_pattern, "[DOB]", "DOB"),
            ("emails", self.email_pattern, "[EMAIL]", "EMAIL"),
            ("ssns", self.ssn_pattern, "[SSN]", "SSN"),
            ("phones", self.phone_pattern, "[PHONE]", "PHONE"),
        ]

    def process(self, text):

        redaction_counts = {
            "emails": 0,
            "phones": 0,
            "mrns": 0,
            "dobs": 0,
            "ssns": 0,
        }
        matches = []

        for key, pattern, placeholder, label in self._rules:

            found = [m.group(0) for m in pattern.finditer(text)]
            redaction_counts[key] = len(found)
            matches.extend({"label": label, "text": t, "source": "regex"} for t in found)
            text = pattern.sub(placeholder, text)

        return {
            "clean_text": text,
            "redaction_counts": redaction_counts,
            "matches": matches,
        }
