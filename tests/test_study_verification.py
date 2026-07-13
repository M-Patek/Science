from datetime import datetime, timezone
import hashlib, json
import pytest
from science_repo.study_verification import StudyVerificationError, verify_attempt_manifest, verify_blinded_scoring

def h(x): return hashlib.sha256((json.dumps(x,sort_keys=True,separators=(",",":"))+"\n").encode()).hexdigest()

def test_attempts_require_exact_coverage_and_trusted_authorization(tmp_path):
    (tmp_path/"e").write_bytes(b"x"); ledger={}; attempts=[]; auth={}
    baseline={"git_commit":"b"*40,"git_tree":"c"*40}
    for i in range(24):
        cid=f"c{i}"; receipt={"cohort_id":"co","cell_id":cid,"attempt_ordinal":1,"scope":["w"],"expires_at":"2030-01-01T00:00:00Z"}; rid=f"r{i}"
        identities={"session_id":f"s{i}","worktree_id":f"w{i}","context_id":f"x{i}"}
        b={"schema_version":1,"attempt_id":f"a{i}","opaque_cell_token":f"t{i}","attempt_ordinal":1,"subject_packet_sha256":hashlib.sha256(str(i).encode()).hexdigest(),"baseline":baseline,"identities":identities,"authorization_receipt":{"receipt_id":rid,"receipt_sha256":h(receipt)},"timing":{"task_received_utc":"2029-01-01T00:00:00Z","ended_utc":"2029-01-01T00:01:00Z","elapsed_seconds":60},"evidence":{"e":hashlib.sha256(b"x").hexdigest()},"stop_reason":"completed","censor":{"status":"not-censored","reason":None},"critical_violations":[]}
        b["finalized_sha256"]=h(b); path=f"b{i}.json"; (tmp_path/path).write_text(json.dumps(b))
        ledger[cid]={"opaque_cell_token":f"t{i}","subject_packet_sha256":b["subject_packet_sha256"],"baseline":baseline,"write_scope":["w"],"attempt_ordinal":1,"identities":identities}; auth[rid]=receipt
        attempts.append({"path":path,"cell_id":cid,"attempt_ordinal":1})
    manifest={"schema_version":1,"cohort_id":"co","attempts":attempts}
    result=verify_attempt_manifest(manifest,root=tmp_path,ledger=ledger,authorizations=auth,authorization_verifier=lambda r,ref: ref["receipt_sha256"]==h(r),expected_cohort_id="co",now=datetime(2029,1,1,tzinfo=timezone.utc))
    assert len(result["verified"])==24
    with pytest.raises(StudyVerificationError,match="trusted authorization"):
        verify_attempt_manifest(manifest,root=tmp_path,ledger=ledger,authorizations=auth,authorization_verifier=None,expected_cohort_id="co")
    malformed={**manifest,"attempts":[None,*attempts[1:]]}
    with pytest.raises(StudyVerificationError,match="entries must be objects"):
        verify_attempt_manifest(malformed,root=tmp_path,ledger=ledger,authorizations=auth,authorization_verifier=lambda *_: True,expected_cohort_id="co")
    unhashable={**manifest,"attempts":[{**attempts[0],"cell_id":[]},*attempts[1:]]}
    with pytest.raises(StudyVerificationError,match="invalid types"):
        verify_attempt_manifest(unhashable,root=tmp_path,ledger=ledger,authorizations=auth,authorization_verifier=lambda *_: True,expected_cohort_id="co")
    broken=json.loads((tmp_path/"b0.json").read_text()); broken["authorization_receipt"]=True
    broken["finalized_sha256"]=h({k:v for k,v in broken.items() if k!="finalized_sha256"})
    (tmp_path/"b0.json").write_text(json.dumps(broken))
    with pytest.raises(StudyVerificationError,match="invalid types"):
        verify_attempt_manifest(manifest,root=tmp_path,ledger=ledger,authorizations=auth,authorization_verifier=lambda *_: True,expected_cohort_id="co",now=datetime(2029,1,1,tzinfo=timezone.utc))

def test_blinding_audit_and_commit_before_reveal():
    content="evidence"; digest=hashlib.sha256(content.encode()).hexdigest()
    attempt_hashes={hashlib.sha256(str(i).encode()).hexdigest() for i in range(24)}
    packets=[{"opaque_packet_id":f"opaque-{i}","source_attempt_sha256":source,"acceptance_evidence":[{"content":content,"sha256":digest}],"diff_evidence":[],"test_evidence":[],"provenance_evidence":[]} for i,source in enumerate(sorted(attempt_hashes))]
    ps=h(sorted(h(packet) for packet in packets)); scores={p["opaque_packet_id"]:{"score":2} for p in packets}; commits=[]; reveals=[]; context={"rubric_sha256":"a"*64,"study_id":"study-1"}; context_hash=h(context)
    for scorer in ("s1","s2"):
        payload={"scorer_id":scorer,"packet_set_sha256":ps,"scoring_context_sha256":context_hash,"scores":scores,"nonce":scorer}
        commits.append({"scorer_id":scorer,"packet_set_sha256":ps,"scoring_context_sha256":context_hash,"committed_at":"2029-01-01T00:00:00Z","commitment_sha256":h(payload)})
        reveals.append({"scorer_id":scorer,"revealed_at":"2029-01-03T00:00:00Z","scores":scores,"nonce":scorer})
    assert verify_blinded_scoring(packets,commits,reveals,attempt_hashes=attempt_hashes,reveal_not_before=datetime(2029,1,2,tzinfo=timezone.utc),scorer_verifier=lambda c,r: c["scorer_id"]==r["scorer_id"],scoring_context=context)["packet_count"]==24
    packets[0]["notes"]="treatment arm"
    with pytest.raises(StudyVerificationError,match="prohibited blinded content"):
        verify_blinded_scoring(packets,commits,reveals,attempt_hashes=attempt_hashes,reveal_not_before=datetime(2029,1,2,tzinfo=timezone.utc),scorer_verifier=lambda c,r: True,scoring_context=context)

def test_blind_audit_does_not_reject_unrelated_substrings():
    from science_repo.study_verification import _blind_audit
    _blind_audit({"description":"an armchair benchmark"})
