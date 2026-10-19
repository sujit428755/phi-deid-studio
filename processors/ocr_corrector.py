import pickle
import re

from config import OCR_RULES_PATH


class OCRCorrector:
    """
    Stage 5 - targeted correction of the misrecognition patterns that the
    scanned historical batch is known to have. Applied ONLY to notes flagged
    as scanned: applying it to native notes would introduce new errors.
    """

    _TOKEN_WITH_DIGIT = re.compile(r"\b(?=\w*\d)\w+\b")

    def __init__(self):

        with open(OCR_RULES_PATH, "rb") as file:
            self.ocr_rules = pickle.load(file)

    @staticmethod
    def _is_char_confusion(wrong):
        """Rules like 'OO' -> '00' only make sense inside numeric tokens."""
        return bool(re.fullmatch(r"[OolI]+", wrong))

    def correct_with_report(self, text, is_scanned=False):
        applied = {}
        if not is_scanned:
            return text, applied

        for wrong, correct in self.ocr_rules.items():

            if self._is_char_confusion(wrong):
                # Only touch tokens that already contain a digit (OO4521),
                # so real words such as "Good" or "Blood" are left intact.
                def _fix(m, w=wrong, c=correct):
                    return m.group(0).replace(w, c)
                new_text = self._TOKEN_WITH_DIGIT.sub(_fix, text)
            else:
                new_text = text.replace(wrong, correct)

            if new_text != text:
                applied[wrong] = applied.get(wrong, 0) + 1
            text = new_text

        return text, applied

    def correct_text(self, text, is_scanned=False):
        """Apply OCR corrections only for scanned notes."""
        return self.correct_with_report(text, is_scanned)[0]
