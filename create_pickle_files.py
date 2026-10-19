import os
import pickle

# ==========================================
# Create Models Folder
# ==========================================

os.makedirs("models", exist_ok=True)

# ==========================================
# Facility Dictionary
# (hospital-specific names spaCy was never trained on)
# ==========================================

facility_dictionary = [
    "Riverside East Wing",
    "Comm. Health annex",
    "Riverside Regional",
    "ED Triage Unit",
    "RE Wing",
]

with open("models/facility_dictionary.pkl", "wb") as file:
    pickle.dump(facility_dictionary, file)

# ==========================================
# OCR Rules
# (only ever applied to notes flagged as scanned)
# ==========================================

ocr_rules = {
    "OO": "00",
    " l ": " 1 ",
    " I ": " 1 ",
    "Jo hn": "John",
    "Em ma": "Emma",
    "Mi ller": "Miller",
    "Sm ith": "Smith",
    "Pri ya": "Priya",
}

with open("models/ocr_rules.pkl", "wb") as file:
    pickle.dump(ocr_rules, file)

print("PKL files created successfully.")
