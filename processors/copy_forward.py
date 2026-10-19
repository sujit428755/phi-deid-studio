import re


class CopyForwardRemover:
    """
    Stage 3 - strip nested EHR "copy-forward" blocks (a new note that
    begins by quoting a prior visit verbatim) so the same patient's PHI
    is not left behind at a second or third nesting level.
    """

    def __init__(self):
        # Block markers run until the new content starts (or a blank line).
        self.block_patterns = [
            r"Copy-forward note:.*?(?=New visit:|\n\s*\n|$)",
            r"Copied note:.*?(?=New visit:|\n\s*\n|$)",
            r"Forwarded note:.*?(?=New visit:|\n\s*\n|$)",
        ]
        # Long single-quoted spans. The look-arounds stop apostrophes in
        # ordinary prose ("patient's ... doctor's") being treated as quotes.
        self.quote_pattern = r"(?<![\w])'[^'\n]{20,}'(?![\w])"

    def remove_with_report(self, text):
        removed = 0
        for pattern in self.block_patterns + [self.quote_pattern]:
            text, n = re.subn(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
            removed += n
        return text.strip(), removed

    def remove_copy_forward(self, text):
        """
        Remove copied historical notes.

        Copy-forward note:
        'John Miller was seen...'
        """
        return self.remove_with_report(text)[0]
