"""Exploratory data analysis: python eda.py  ->  reports/"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import DATASET_PATH, REPORTS_FOLDER, CHARTS_FOLDER
from services.pipeline_service import load_dataset

os.makedirs(CHARTS_FOLDER, exist_ok=True)

df = load_dataset(DATASET_PATH)
df["text_length"] = df["note_text"].str.len()
df["word_count"] = df["note_text"].str.split().str.len()

lines = [
    "EDA SUMMARY", "=" * 40,
    f"Total records     : {len(df)}",
    f"Total columns     : {df.shape[1]}",
    f"Missing values    : {int((df == '').sum().sum() + df.isna().sum().sum())}",
    f"Duplicate records : {int(df.duplicated().sum())}",
    f"Scanned notes     : {int(df['is_scanned'].sum())}",
    f"Non-scanned notes : {int((~df['is_scanned']).sum())}",
    f"Facilities        : {df['facility'].nunique()}",
    f"Avg text length   : {df['text_length'].mean():.0f} chars",
    f"Avg word count    : {df['word_count'].mean():.0f} words",
]
open(os.path.join(REPORTS_FOLDER, "eda_summary.txt"), "w").write("\n".join(lines))
print("\n".join(lines))

# grouping / sorting / filtering
fac = df.groupby("facility").agg(notes=("note_id", "count"),
                                 scanned=("is_scanned", "sum"),
                                 avg_words=("word_count", "mean")).reset_index()
fac.sort_values("notes", ascending=False).to_csv(os.path.join(REPORTS_FOLDER, "facility_summary.csv"), index=False)
df.to_csv(os.path.join(REPORTS_FOLDER, "eda_processed_dataset.csv"), index=False)

# charts
counts = df["is_scanned"].map({True: "Scanned", False: "Non-scanned"}).value_counts()
plt.figure(figsize=(5, 4)); counts.plot.bar(color=["#00b4d8", "#ef476f"]); plt.title("Scanned vs non-scanned")
plt.tight_layout(); plt.savefig(os.path.join(CHARTS_FOLDER, "scanned_vs_non_scanned.png")); plt.close()

plt.figure(figsize=(6, 4)); plt.bar(df["note_id"].astype(str), df["word_count"], color="#6c5ce7")
plt.title("Word count per note"); plt.tight_layout()
plt.savefig(os.path.join(CHARTS_FOLDER, "word_count_per_note.png")); plt.close()
print("\nReports written to reports/")
