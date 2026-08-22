import hashlib
import json
from datetime import datetime
from pathlib import Path

import yaml

from config import HARNESS_STATE_DIR


def request_decision(kind, context, state_dir):
    ddir = Path(state_dir) / "decisions"
    ddir.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(
        json.dumps([kind, context], sort_keys=True, default=str).encode()
    ).hexdigest()
    for path in sorted(ddir.glob("D-*.yaml")):
        with open(path) as f:
            existing = yaml.safe_load(f)
        if existing.get("fingerprint") == fingerprint and existing.get("status") == "resolved":
            return {**existing, "file": path.name, "asked_again": True}
    decision_id = f"D-{len(list(ddir.glob('D-*.yaml'))) + 1:04d}"
    decision = {
        "decision_id": decision_id,
        "status": "pending",
        "created": datetime.now().isoformat(),
        "kind": kind,
        "fingerprint": fingerprint,
        **context,
        "resolution": None,
    }
    path = ddir / f"{decision_id}.yaml"
    with open(path, "w") as f:
        yaml.dump(decision, f, sort_keys=False)
    return {**decision, "file": path.name, "asked_again": False}


def resolve_decision(decision_id, choice, actor, state_dir):
    path = Path(state_dir) / "decisions" / f"{decision_id}.yaml"
    with open(path) as f:
        decision = yaml.safe_load(f)
    decision["status"] = "resolved"
    decision["resolution"] = {
        "choice": choice,
        "actor": actor,
        "timestamp": datetime.now().isoformat(),
    }
    with open(path, "w") as f:
        yaml.dump(decision, f, sort_keys=False)
    return decision


def pending_decisions(state_dir):
    ddir = Path(state_dir) / "decisions"
    if not ddir.exists():
        return []
    pending = []
    for path in sorted(ddir.glob("D-*.yaml")):
        with open(path) as f:
            decision = yaml.safe_load(f)
        if decision.get("status") == "pending":
            pending.append(decision)
    return pending
