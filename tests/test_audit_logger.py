from utils.audit_logger import AuditLogger


def test_audit_and_edge_case_logging(tmp_path):
    lg = AuditLogger(str(tmp_path / "a.csv"), str(tmp_path / "e.csv"))
    lg.log_event(1, "f.csv", 5, "PASS")
    lg.log_event(2, "f.csv", 3, "FAIL", issues=["Facility Found: X"])
    assert len(lg.read_log()) == 2
    assert len(lg.read_edge_cases()) == 1
