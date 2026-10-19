from utils.audit_logger import AuditLogger

AuditLogger().log_event(note_id=1, file_name="sample_notes.csv", entities_found=5, verification_status="PASS")
print("Audit entry written.")
