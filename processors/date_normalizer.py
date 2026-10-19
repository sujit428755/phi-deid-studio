import re
from dateutil import parser

_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)


class DateNormalizer:
    """
    Stage 2 - collapse every date style used by the different
    note-authoring systems / eras into one canonical YYYY-MM-DD form:

        03/03/2026 | March 3, 2026 | 3-3-26 | 2026-03-03  ->  2026-03-03
    """

    def __init__(self):

        self.date_patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
            r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
            r"\b" + _MONTHS + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
            r"\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTHS + r"\.?,?\s+\d{2,4}\b",
        ]

        self._combined = re.compile(
            "|".join(f"(?:{p})" for p in self.date_patterns),
            flags=re.IGNORECASE,
        )

    def normalize_with_report(self, text):
        """Return (normalized_text, [{'original':..., 'normalized':...}])."""
        changes = []

        def _sub(match):
            original = match.group(0)
            try:
                normalized = parser.parse(original).strftime("%Y-%m-%d")
            except Exception:
                return original
            changes.append({"original": original, "normalized": normalized})
            return normalized

        return self._combined.sub(_sub, text), changes

    def normalize_text(self, text):
        return self.normalize_with_report(text)[0]
