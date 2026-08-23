"""Deterministic sponsor-environment views for module-targeted deltas.

A view is a throwaway copy of the sponsor environment in which exactly the
declared module files are replaced by their delta'd variants; everything
else — including every standard program — stays byte-identical, so running
a standard from the view root exercises the modified modules without ever
touching the original environment.
"""
import shutil
from pathlib import Path

from harness.deltas import apply_deltas


def materialize_view(env, state_dir, study_id):
    view_dir = Path(state_dir) / "views" / study_id
    if view_dir.exists():
        shutil.rmtree(view_dir)
    shutil.copytree(env.root, view_dir)
    return view_dir


def apply_module_deltas(view_dir, deltas):
    by_file = {}
    for delta in deltas:
        if delta.get("type") != "module_behavior":
            raise ValueError(
                f"unsupported delta type for view application: {delta.get('type')!r}")
        by_file.setdefault(delta["target_file"], []).append(delta)
    touched = []
    for rel, file_deltas in by_file.items():
        path = Path(view_dir) / rel
        if not path.resolve().is_relative_to(Path(view_dir).resolve()):
            raise ValueError(f"target_file escapes the view: {rel!r}")
        # substitute before writing so an anchor error leaves the view intact
        path.write_text(apply_deltas(path.read_text(), file_deltas))
        touched.append(rel)
    return sorted(touched)
