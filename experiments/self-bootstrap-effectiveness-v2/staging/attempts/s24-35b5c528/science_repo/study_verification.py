"""Fail-closed verification of controlled self-study observations."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, os, re
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

class StudyVerificationError(ValueError): pass

def _bytes(v: Any) -> bytes:
    return (json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)+"\n").encode()
def _hash(v: Any) -> str: return hashlib.sha256(_bytes(v)).hexdigest()
def _time(v: Any) -> datetime:
    try: d=datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as e: raise StudyVerificationError("invalid timestamp") from e
    if d.tzinfo is None: raise StudyVerificationError("timestamp must be timezone-aware")
    return d.astimezone(timezone.utc)
def _path(value: Any, root: Path) -> Path:
    if not isinstance(value,str) or not value or "\\" in value: raise StudyVerificationError("unsafe artifact path")
    p=PurePosixPath(value)
    if p.is_absolute() or any(x in (".","..","") for x in p.parts): raise StudyVerificationError("unsafe artifact path")
    base=root.resolve(strict=True); candidate=root.joinpath(*p.parts)
    # lstat every component: resolving only the leaf would permit a symlink chain.
    cursor=root
    for part in p.parts:
        cursor=cursor/part
        try: attributes=getattr(os.lstat(cursor), "st_file_attributes", 0)
        except OSError as e: raise StudyVerificationError("artifact path component is missing") from e
        if cursor.is_symlink() or attributes & 0x400: raise StudyVerificationError("artifact path contains symlink or reparse point")
    try: resolved=candidate.resolve(strict=True); resolved.relative_to(base)
    except (OSError,ValueError) as e: raise StudyVerificationError("artifact missing or outside root") from e
    if not resolved.is_file(): raise StudyVerificationError("artifact is not a regular file")
    return resolved
def _json(value: Any, root: Path) -> Mapping[str,Any]:
    try: result=json.loads(_path(value,root).read_text(encoding="utf-8"))
    except (UnicodeError,json.JSONDecodeError) as e: raise StudyVerificationError("artifact is not UTF-8 JSON") from e
    if not isinstance(result,dict): raise StudyVerificationError("artifact must be a JSON object")
    return result

def verify_attempt_manifest(manifest: Mapping[str,Any], *, root: Path,
    ledger: Mapping[str,Mapping[str,Any]], authorizations: Mapping[str,Mapping[str,Any]],
    authorization_verifier: Callable[[Mapping[str,Any],Mapping[str,Any]],bool] | None,
    expected_cohort_id: str,
    now: datetime | None=None) -> dict[str,Any]:
    if authorization_verifier is None: raise StudyVerificationError("trusted authorization verifier required")
    attempts=manifest.get("attempts")
    if set(manifest)!={"schema_version","cohort_id","attempts"} or manifest.get("cohort_id") != expected_cohort_id or manifest.get("schema_version")!=1 or len(ledger)!=24 or not isinstance(attempts,list) or len(attempts)!=24:
        raise StudyVerificationError("exactly 24 ledger cells and attempts required")
    if not all(isinstance(a, Mapping) for a in attempts):
        raise StudyVerificationError("attempt entries must be objects")
    if not all(isinstance(k, str) and isinstance(v, Mapping) for k,v in ledger.items()):
        raise StudyVerificationError("ledger cells must be keyed objects")
    if not all(isinstance(k, str) and isinstance(v, Mapping) for k,v in authorizations.items()):
        raise StudyVerificationError("authorization receipts must be keyed objects")
    for entry in attempts:
        if set(entry)!={"path","cell_id","attempt_ordinal"}:
            raise StudyVerificationError("invalid attempt entry")
        if (not isinstance(entry["path"], str) or not isinstance(entry["cell_id"], str)
                or not isinstance(entry["attempt_ordinal"], int) or isinstance(entry["attempt_ordinal"], bool)):
            raise StudyVerificationError("attempt entry fields have invalid types")
    ids=[a.get("cell_id") for a in attempts]
    if len(set(ids))!=24 or set(ids)!=set(ledger): raise StudyVerificationError("attempts must cover ledger exactly")
    current=now or datetime.now(timezone.utc)
    if current.tzinfo is None: raise StudyVerificationError("now must be timezone-aware")
    seen_attempt:set[Any]=set(); seen_session:set[Any]=set(); verified=[]
    for entry in attempts:
        bundle=_json(entry["path"],root); unsigned=dict(bundle); final=unsigned.pop("finalized_sha256",None)
        required={"schema_version","attempt_id","opaque_cell_token","attempt_ordinal","subject_packet_sha256","baseline","identities","authorization_receipt","timing","evidence","stop_reason","censor","critical_violations","finalized_sha256"}
        if set(bundle) != required or bundle.get("schema_version") != 1 or not isinstance(bundle.get("evidence"),dict) or not bundle["evidence"]:
            raise StudyVerificationError("attempt bundle does not satisfy required schema fields")
        if (not isinstance(bundle.get("attempt_id"), str) or not bundle["attempt_id"]
                or not isinstance(bundle.get("opaque_cell_token"), str)
                or not isinstance(bundle.get("subject_packet_sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", bundle["subject_packet_sha256"])
                or not isinstance(bundle.get("attempt_ordinal"), int) or isinstance(bundle.get("attempt_ordinal"), bool)
                or not isinstance(bundle.get("baseline"), dict)
                or not isinstance(bundle.get("identities"), dict)
                or not isinstance(bundle.get("authorization_receipt"), dict)
                or not isinstance(final, str) or not re.fullmatch(r"[a-f0-9]{64}", final)):
            raise StudyVerificationError("attempt bundle fields have invalid types")
        baseline=bundle["baseline"]
        if set(baseline)!={"git_commit","git_tree"} or any(not isinstance(baseline[k],str) or not re.fullmatch(r"[a-f0-9]{40}",baseline[k]) for k in baseline):
            raise StudyVerificationError("baseline binding is invalid")
        identities=bundle["identities"]
        if not identities or any(not isinstance(k,str) or not isinstance(v,str) or not v for k,v in identities.items()):
            raise StudyVerificationError("identity bindings are invalid")
        auth_ref=bundle["authorization_receipt"]
        if set(auth_ref)!={"receipt_id","receipt_sha256"} or any(not isinstance(auth_ref[k],str) or not auth_ref[k] for k in auth_ref):
            raise StudyVerificationError("authorization reference is invalid")
        if not isinstance(bundle.get("critical_violations"), list) or not all(isinstance(x, str) for x in bundle["critical_violations"]):
            raise StudyVerificationError("critical violations must be a string array")
        if bundle.get("stop_reason") not in {"completed","timeout","context-exhaustion","explicit-block","critical-violation","infrastructure-failure","refusal","test-failure"}:
            raise StudyVerificationError("invalid attempt outcome")
        censor=bundle.get("censor")
        if (not isinstance(censor,dict) or set(censor)!={"status","reason"}
                or censor["status"] not in {"not-censored","setup-censored"}
                or (censor["status"] == "not-censored" and censor["reason"] is not None)
                or (censor["status"] == "setup-censored" and (not isinstance(censor["reason"],str) or not censor["reason"]))):
            raise StudyVerificationError("invalid censor outcome")
        timing=bundle.get("timing")
        if not isinstance(timing,dict) or set(timing)!={"task_received_utc","ended_utc","elapsed_seconds"} or not isinstance(timing["elapsed_seconds"],(int,float)) or isinstance(timing["elapsed_seconds"],bool):
            raise StudyVerificationError("invalid completion timing")
        started, ended = _time(timing["task_received_utc"]), _time(timing["ended_utc"])
        if ended < started or timing["elapsed_seconds"] < 0 or abs((ended-started).total_seconds()-timing["elapsed_seconds"]) > 1:
            raise StudyVerificationError("invalid completion timing")
        if final!=_hash(unsigned): raise StudyVerificationError("finalized hash mismatch")
        cell=ledger[entry["cell_id"]]
        for key in ("opaque_cell_token","subject_packet_sha256","baseline"):
            if bundle.get(key)!=cell.get(key): raise StudyVerificationError("ledger binding mismatch")
        if bundle.get("attempt_ordinal")!=entry["attempt_ordinal"]: raise StudyVerificationError("ordinal mismatch")
        if entry["attempt_ordinal"] != cell.get("attempt_ordinal", 1): raise StudyVerificationError("replacement ordinal violates ledger policy")
        if bundle.get("identities") != cell.get("identities"):
            raise StudyVerificationError("identity/worktree/context binding mismatch")
        aid=bundle.get("attempt_id"); sid=bundle.get("identities",{}).get("session_id")
        if not aid or not sid or aid in seen_attempt or sid in seen_session: raise StudyVerificationError("attempt/session identity not unique")
        seen_attempt.add(aid); seen_session.add(sid)
        ref=bundle["authorization_receipt"]; receipt=authorizations.get(ref["receipt_id"])
        if not receipt or ref.get("receipt_sha256")!=_hash(receipt) or not authorization_verifier(receipt,ref):
            raise StudyVerificationError("authorization not trusted and content-bound")
        expected={"cohort_id":manifest.get("cohort_id"),"cell_id":entry["cell_id"],"attempt_ordinal":entry["attempt_ordinal"],"scope":cell.get("write_scope")}
        if any(receipt.get(k)!=v for k,v in expected.items()) or _time(receipt.get("expires_at"))<=current.astimezone(timezone.utc):
            raise StudyVerificationError("authorization binding invalid or expired")
        for name,digest in bundle.get("evidence",{}).items():
            if not isinstance(name, str) or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise StudyVerificationError("evidence entries require safe paths and SHA-256 digests")
            if hashlib.sha256(_path(name,root).read_bytes()).hexdigest()!=digest: raise StudyVerificationError("evidence hash mismatch")
        verified.append({"cell_id":entry["cell_id"],"attempt_id":aid,"finalized_sha256":final})
    return {"schema_version":1,"cohort_id":manifest.get("cohort_id"),"verified":verified,"manifest_sha256":_hash(manifest)}

_PROHIBITED_FIELDS={"arm","arm_label","condition","control","treatment","allocation","cohort_id","cell_id","session_id","model_id","identity","identities"}
_PROHIBITED_CONTENT=re.compile(r"(?i)(?<![\w-])(control|treatment|allocation|cohort|cell[_ -]?id|session[_ -]?id|model[_ -]?id|arm(?:[_ -]?label)?)(?![\w-])")
def _blind_audit(v: Any, location="packet") -> None:
    if isinstance(v,Mapping):
        for k,x in v.items():
            normalized=str(k).casefold().replace("-","_").replace(" ","_")
            if normalized in _PROHIBITED_FIELDS: raise StudyVerificationError(f"prohibited blinded field at {location}.{k}")
            _blind_audit(x,f"{location}.{k}")
    elif isinstance(v,list):
        for i,x in enumerate(v): _blind_audit(x,f"{location}[{i}]")
    elif isinstance(v,str) and _PROHIBITED_CONTENT.search(v): raise StudyVerificationError(f"prohibited blinded content at {location}")

def verify_blinded_scoring(packets: Sequence[Mapping[str,Any]], commitments: Sequence[Mapping[str,Any]],
    reveals: Sequence[Mapping[str,Any]], *, attempt_hashes:set[str], reveal_not_before:datetime,
    scorer_verifier:Callable[[Mapping[str,Any],Mapping[str,Any]],bool] | None,
    scoring_context: Mapping[str,Any]) -> dict[str,Any]:
    if scorer_verifier is None: raise StudyVerificationError("trusted scorer verifier required")
    if reveal_not_before.tzinfo is None: raise StudyVerificationError("reveal time must be timezone-aware")
    if len(packets)!=24 or len(attempt_hashes)!=24: raise StudyVerificationError("exactly 24 packets and attempt hashes required")
    ids=set(); hashes=[]
    for p in packets:
        _blind_audit(p); pid=p.get("opaque_packet_id")
        if not pid or pid in ids or p.get("source_attempt_sha256") not in attempt_hashes: raise StudyVerificationError("packet source/id invalid")
        ids.add(pid)
        for section in ("acceptance_evidence","diff_evidence","test_evidence","provenance_evidence"):
            for e in p.get(section,[]):
                if e.get("sha256")!=hashlib.sha256(e.get("content","").encode()).hexdigest(): raise StudyVerificationError("packet evidence hash mismatch")
        hashes.append(_hash(p))
    if {p.get("source_attempt_sha256") for p in packets} != attempt_hashes:
        raise StudyVerificationError("packets must map one-to-one onto verified attempts")
    packet_set=_hash(sorted(hashes)); cs={x.get("scorer_id"):x for x in commitments}; rs={x.get("scorer_id"):x for x in reveals}
    if len(commitments)!=2 or len(reveals)!=2 or len(cs)!=2 or len(rs)!=2 or set(cs)!=set(rs): raise StudyVerificationError("exactly two scorers required")
    boundary=reveal_not_before.astimezone(timezone.utc)
    context_sha256=_hash(scoring_context)
    for scorer,c in cs.items():
        r=rs[scorer]
        if not scorer_verifier(c,r): raise StudyVerificationError("scorer identity/timestamps not trusted")
        if c.get("packet_set_sha256")!=packet_set or c.get("scoring_context_sha256")!=context_sha256: raise StudyVerificationError("packet coverage or scoring context differs")
        committed,revealed=_time(c.get("committed_at")),_time(r.get("revealed_at"))
        if not committed<boundary<=revealed or not committed<revealed: raise StudyVerificationError("commit-before-reveal violated")
        payload={"scorer_id":scorer,"packet_set_sha256":packet_set,"scoring_context_sha256":context_sha256,"scores":r.get("scores"),"nonce":r.get("nonce")}
        if c.get("commitment_sha256")!=_hash(payload) or set(r.get("scores",{}))!=ids: raise StudyVerificationError("reveal or packet coverage invalid")
    return {"schema_version":1,"packet_set_sha256":packet_set,"scoring_context_sha256":context_sha256,"packet_count":len(packets),"scorers":sorted(cs)}
