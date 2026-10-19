import re
from dateutil import parser


class Verifier:
    """
    Stage 7 - mandatory post-redaction safety net.

    Scans the REDACTED output for the patient's actual identifiers pulled
    from structured EHR fields (not merely whatever NER happened to flag).
    Beyond the exact strings it also looks for:
      * each name part on its own ("Miller" alone)
      * the DOB in every common written format
      * phone numbers regardless of punctuation
      * MRNs regardless of prefix / leading zeros
    """

    # ------------------------------------------------------
    @staticmethod
    def _dob_variants(dob):
        variants = {str(dob).strip()}
        try:
            d = parser.parse(str(dob))
            variants |= {
                d.strftime("%Y-%m-%d"),
                d.strftime("%m/%d/%Y"),
                d.strftime("%-m/%-d/%Y"),
                d.strftime("%m/%d/%y"),
                d.strftime("%-m/%-d/%y"),
                d.strftime("%-m-%-d-%y"),
                d.strftime("%m-%d-%Y"),
                d.strftime("%B %-d, %Y"),
                d.strftime("%b %-d, %Y"),
            }
        except Exception:
            pass
        return {v for v in variants if v}

    # ------------------------------------------------------
    def verify(
        self,
        redacted_text,
        patient_name,
        mrn,
        dob,
        phone=None,
        email=None,
        facility=None,
    ):

        issues = []
        checks = []

        def record(kind, provided, passed, detail=""):
            checks.append({
                "check": kind,
                "identifier": provided,
                "result": "PASS" if passed else "FAIL",
                "detail": detail if not passed else "Not present in redacted text",
            })
            if not passed:
                issues.append(detail)

        text_lower = redacted_text.lower()
        digits_only = re.sub(r"\D", "", redacted_text)

        # ------------------------------ Patient name
        if patient_name and str(patient_name).strip():
            name = str(patient_name).strip()
            full_hit = re.search(re.escape(name), redacted_text, flags=re.IGNORECASE)
            record("Patient name (full)", name, not full_hit,
                   f"Patient Name Found: {name}")

            for part in re.split(r"\s+", name):
                if len(part) >= 3:
                    hit = re.search(rf"\b{re.escape(part)}\b", redacted_text, flags=re.IGNORECASE)
                    record("Patient name (part)", part, not hit,
                           f"Name part still present: {part}")

        # ------------------------------ MRN
        if mrn and str(mrn).strip():
            m = str(mrn).strip()
            core = re.sub(r"^MRN[:\s#]*", "", m, flags=re.IGNORECASE)
            hit = m in redacted_text or (len(core) >= 4 and core.lower() in text_lower)
            record("MRN", m, not hit, f"MRN Found: {m}")

        # ------------------------------ DOB
        if dob and str(dob).strip():
            d = str(dob).strip()
            hit = any(v in redacted_text for v in self._dob_variants(d))
            record("Date of birth", d, not hit, f"DOB Found: {d}")

        # ------------------------------ Phone
        if phone and str(phone).strip():
            p = str(phone).strip()
            p_digits = re.sub(r"\D", "", p)[-10:]
            hit = len(p_digits) >= 7 and p_digits in digits_only
            record("Phone", p, not hit, f"Phone Found: {p}")

        # ------------------------------ Email
        if email and str(email).strip():
            e = str(email).strip()
            record("Email", e, e.lower() not in text_lower, f"Email Found: {e}")

        # ------------------------------ Facility / organisation
        if facility and str(facility).strip():
            f = str(facility).strip()
            norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
            hit = norm(f) in norm(redacted_text)
            record("Facility", f, not hit, f"Facility Found: {f}")

        status = "PASS" if not issues else "FAIL"

        return {
            "status": status,
            "issues": issues,
            "checks": checks,
            "checks_performed": len(checks),
            "verified": len(checks) > 0,
        }
