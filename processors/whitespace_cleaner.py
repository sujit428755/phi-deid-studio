import re


class WhitespaceCleaner:
    """
    Stage 4 - undo PDF-to-text artefacts so a name or date broken across
    a line break ("John\\nMiller") is one continuous span for NER.
    """

    def clean(self, text):

        # Re-join words hyphenated across a line wrap ("Mil-\\nler")
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        # Line breaks / runs of blank lines -> single space
        text = re.sub(r"\n+", " ", text)

        # Tabs -> space
        text = re.sub(r"\t+", " ", text)

        # Repeated / unicode spaces
        text = re.sub(r"\s+", " ", text)

        return text.strip()
