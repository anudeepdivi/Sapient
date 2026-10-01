import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


class RunManifest:
    def __init__(self, runs_dir, git_commit=None, configuration=None):
        self.run_id = uuid4().hex
        self.root = Path(runs_dir).resolve() / self.run_id
        self.root.mkdir(parents=True, exist_ok=False)
        for name in ("adam", "tlf_programs", "frames"):
            (self.root / name).mkdir()
        self.path = self.root / "manifest.json"
        # Accept only non-secret, reproducibility-related configuration.
        allowed = {"reasoning_model", "codegen_model", "fallback_model",
                   "temperature", "max_tokens"}
        config = {k: v for k, v in (configuration or {}).items() if k in allowed}
        self.data = {
            "schema_version": 1,
            "run_id": self.run_id,
            "started_at": _timestamp(),
            "finished_at": None,
            "status": "running",
            "git_commit": git_commit,
            "configuration": config,
            "configuration_sha256": hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()).hexdigest(),
            "inputs": {},
            "artifacts": {},
        }
        self.save()

    def save(self):
        fd, temporary = tempfile.mkstemp(dir=self.root, prefix=".manifest-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(self.data, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def record_input(self, name, path):
        path = Path(path).resolve(strict=True)
        if path.is_dir():
            files = {}
            for item in sorted(path.rglob("*")):
                if item.is_file():
                    files[item.relative_to(path).as_posix()] = file_sha256(item)
            record = {"path": str(path), "files": files,
                      "sha256": hashlib.sha256(
                          json.dumps(files, sort_keys=True).encode()).hexdigest()}
        else:
            record = {"path": str(path), "sha256": file_sha256(path)}
        previous = self.data["inputs"].get(name)
        if previous is not None and previous != record:
            raise ValueError(f"input changed during run: {name}")
        self.data["inputs"][name] = record
        self.save()
        return record

    def record_artifact(self, name, path, producer, source_path):
        path = Path(path).resolve(strict=True)
        if not path.is_relative_to(self.root) or path == self.path:
            raise ValueError("artifact must be a file inside this run directory")
        record = {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": file_sha256(path),
            "producer": producer,
            "source_path": str(Path(source_path).resolve(strict=True)),
            "source_sha256": file_sha256(source_path),
        }
        previous = self.data["artifacts"].get(name)
        if previous is not None and previous != record:
            raise ValueError(f"artifact already recorded with different content: {name}")
        self.data["artifacts"][name] = record
        self.save()
        return record

    def artifact_path(self, name):
        record = self.data["artifacts"][name]
        path = (self.root / record["path"]).resolve(strict=True)
        if not path.is_relative_to(self.root):
            raise ValueError(f"artifact escapes run directory: {name}")
        if file_sha256(path) != record["sha256"]:
            raise ValueError(f"artifact changed after registration: {name}")
        return path

    def finish(self, status):
        if status not in {"completed", "failed", "incomplete"}:
            raise ValueError(f"invalid terminal run status: {status}")
        if self.data["status"] != "running":
            raise ValueError("run already finished")
        self.data["status"] = status
        self.data["finished_at"] = _timestamp()
        self.save()
