"""Replay check: rebuild every AI step from the prompt cache, with AI calls switched off.

Each step builds its prompts exactly as a real run does. A prompt already in the cache
replays the saved answer; a prompt that is not counts as a miss and is never sent.
Nothing is published: proposed specs and shells go to a temporary folder, code
generation ends before a program is assembled, and the guardrail log is left
alone. Zero misses means a rebuild of these steps makes zero AI calls. Spec drafting
and shells stop at their first miss, so their miss counts are a lower bound.

Usage: python scripts/replay_check.py [DATASET ...]   (default: ADSL ADAE ADLBC)
       SAPIENT_SPEC_RDS selects the spec, as for gen_derivations.py.
Exit code 1 if any prompt misses the cache.
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llm
from adam import derivations
from specs import drafting, shells
from study import DATASETS

counts = {"hit": 0, "miss": 0}


class Miss(Exception):
    pass


def offline():
    real_get = llm.get_cached

    def get_cached(key):
        answer = real_get(key)
        counts["hit" if answer is not None else "miss"] += 1
        return answer

    def no_call(*args, **kwargs):
        raise Miss

    llm.get_cached, llm.create_with_retry = get_cached, no_call
    llm.set_cached = lambda *args, **kwargs: None


offline()

real_gen_step = derivations.gen_step


def gen_step(*args, **kwargs):
    # a miss continues with code that fails the gate, so the run stays deterministic
    try:
        return real_gen_step(*args, **kwargs)
    except Miss:
        return "MISS"


derivations.gen_step = gen_step
derivations.log_event = drafting.log_spec_event = lambda *args, **kwargs: None


def main(datasets):
    drafting.PROPOSED_DIR = shells.OUT_DIR = Path(tempfile.mkdtemp(prefix="replay_check_"))
    jobs = ([("spec", ds, drafting.propose) for ds in datasets]
            + [("codegen", ds, derivations.derive) for ds in datasets]
            + [("shells", arm, shells.generate) for arm in ("title", "sap")])
    print(f"{'step':<8} {'target':<7} {'prompts':>7} {'misses':>6}")
    total = {"hit": 0, "miss": 0}
    for step, target, run in jobs:
        if step != "shells" and target not in DATASETS:
            print(f"{step:<8} {target:<7} {'-':>7} {'-':>6}  not set up in the pipeline")
            continue
        counts.update(hit=0, miss=0)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                run(target)
        except Miss:
            pass
        print(f"{step:<8} {target:<7} {counts['hit'] + counts['miss']:>7} {counts['miss']:>6}")
        for k in total:
            total[k] += counts[k]
    print(f"{'total':<16} {total['hit'] + total['miss']:>7} {total['miss']:>6}")
    if total["miss"]:
        print("Some prompts are not in the cache: a rebuild would call the AI for them.")
        return 1
    print("Zero AI calls: every prompt replayed from the cache.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["ADSL", "ADAE", "ADLBC"]))
