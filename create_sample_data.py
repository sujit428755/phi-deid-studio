"""
Builds the synthetic datasets (no real PHI is ever used).

  data/sample_notes.csv      - the 5-note research corpus described in the use case
  data/edge_case_notes.csv   - harder notes (nicknames, misspellings) that the
                               automated pass is KNOWN to struggle with; used to
                               demonstrate the verification + human-review loop.
"""
import os
import pandas as pd

os.makedirs("data", exist_ok=True)

COLS = ["note_id", "patient_name", "mrn", "dob", "phone", "email",
        "facility", "is_scanned", "note_text"]

sample = [
    [1, "John Miller", "004521", "1985-03-03", "(555) 019-2231", "jmiller82@email.com",
     "Riverside East Wing", True,
     "Jo hn Miller (MRN: OO4521) seen 3-3-26 at Riverside East Wing. Patient reports "
     "chest tightness since yesterday, no radiation. ECG normal. Contact: (555) 019-2231, "
     "jmiller82@email.com. DOB: 1985-03-03. Discharged with follow-up in 2 weeks."],
    [2, "Emma Davis", "007832", "1990-07-14", "555-014-8890", "emma.davis@mail.org",
     "Comm. Health annex", True,
     "Em ma Davis presented to the Comm. Health annex on March 5, 2026 with persistent cough "
     "and mild fever. Good oxygen saturation. MRN: 007832. DOB: 07/14/1990. Call back on "
     "555-014-8890 or emma.davis@mail.org. Prescribed amoxicillin for 7 days."],
    [3, "Michael Brown", "009115", "1972-11-30", "(555) 301-4467", "mbrown72@webmail.com",
     "Riverside East Wing", False,
     "Copy-forward note:\n'Michael Brown was seen 03/03/2026 and discharged from Riverside "
     "East Wing.'\n\nNew visit: Michael Brown reports improvement on 2026-03-10. Blood pressure "
     "stable. Contact: (555) 301-4467, mbrown72@webmail.com. MRN: 009115."],
    [4, "Sarah Johnson", "012390", "1978-11-02", "555.882.1200", "sjohnson@care.net",
     "Comm. Health annex", False,
     "Patient Sarah\nJohnson (MRN: 012390, DOB: 11/02/1978) arrived at the Comm. Health annex "
     "on 3-12-26. Complains of migraine for three days. Phone 555.882.1200, email sjohnson@care.net. "
     "Started sumatriptan; review in clinic next month."],
    [5, "Robert Wilson", "015004", "1966-05-21", "(555) 210-7788", "rwilson66@inbox.com",
     "Riverside East Wing", False,
     "Robert Wilson, a resident of Mumbai, was brought to Riverside East Wing on March 12, 2026 "
     "after a fall. X-ray shows no fracture. MRN: 015004. Family reachable at (555) 210-7788. "
     "Advised rest and physiotherapy."],
]

edge = [
    [101, "Jonathan Hale", "020113", "1969-02-09", "(555) 700-1122", "jhale@post.com",
     "Riverside East Wing", False,
     "Johnny came in on the morning of the ninth of February with knee pain. MRN: 020113. "
     "Seen at the Riverside East Wing. Call (555) 700-1122."],
    [102, "Priya Natarajan", "020774", "1994-08-17", "5557003344", "priya.n@mail.in",
     "Comm. Health annex", True,
     "Pri ya Natarajan attended the comm health annex on 17 Aug 26. MRN: O2O774. Reachable at "
     "5557003344. Reports fatigue, hemoglobin low."],
    [103, "Elizabeth Turner", "021559", "1958-12-25", "(555) 610-9090", "eturner@care.org",
     "Riverside East Wing", False,
     "Liz Turner (pt. of Dr. Anand) seen on Christmas Day 2025 at the RE Wing. MRN: 021559. "
     "Follow-up on (555) 610-9090."],
]

pd.DataFrame(sample, columns=COLS).to_csv("data/sample_notes.csv", index=False)
pd.DataFrame(edge, columns=COLS).to_csv("data/edge_case_notes.csv", index=False)
print("Sample datasets created.")
