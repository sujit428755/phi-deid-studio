from processors.copy_forward import CopyForwardRemover

sample_text = """
Copy-forward note:
'Michael Brown was seen 03/03/2026 and discharged.'

New visit:
Patient reports improvement.
"""
print("\n===== CLEANED TEXT =====\n")
print(CopyForwardRemover().remove_copy_forward(sample_text))
