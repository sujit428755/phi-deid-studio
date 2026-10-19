"""Command-line runner: python main.py [dataset.csv]"""
import sys

from config import DATASET_PATH
from services.pipeline_service import PHIDeidentificationPipeline
import services.evaluation_service as ev

path = sys.argv[1] if len(sys.argv) > 1 else DATASET_PATH

pipeline = PHIDeidentificationPipeline()
out, traces = pipeline.process_dataset(path)

print("\n===== REDACTED NOTES =====\n")
for _, r in out.iterrows():
    print(f"[{r['note_id']}] {r['verification_status']} | entities={r['entities_found']}")
    print(f"    {r['redacted_text']}\n")

rec = ev.recall_by_type(ev.identifier_matrix(traces))
print("===== IDENTIFIER RECALL =====")
print(rec.to_string(index=False))
print(f"\nOverall recall: {100 * ev.overall_recall(rec):.1f}%")
print("\nSaved: data/output/redacted_notes.csv  |  Audit: logs/audit_log.csv")
