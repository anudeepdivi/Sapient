"""Replay check: rebuild every AI step from the prompt cache, with AI calls switched off.

Each step builds its prompts exactly as a real run does. A prompt already in the cache
replays the saved answer; a prompt that is not counts as a miss and is never sent.
Nothing is published: proposed specs and shells go to a temporary folder, code
generation stops before assembling the final program, and the guardrail log is left
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

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import gen_derivations
import gen_shells
import gen_spec
from templates.adam_templates import ADAM_INPUTS

counts = {"hit": 0, "miss": 0}


class Miss(Exception):
    pass


class Stop(Exception):
    pass


def offline(module):
    real_get = module.get_cached

    def get_cached(key):
        answer = real_get(key)
        counts["hit" if answer is not None else "miss"] += 1
        return answer

    def no_call(*args, **kwargs):
        raise Miss

    module.get_cached, module.create_with_retry = get_cached, no_call
    module.set_cached = lambda *args, **kwargs: None


def stop(*args, **kwargs):
    raise Stop


for module in (gen_derivations, gen_spec, gen_shells):
    offline(module)

real_gen_step = gen_derivations.gen_step


def gen_step(*args, **kwargs):
    # a miss continues with code that fails the gate, so the run stays deterministic
    try:
        return real_gen_step(*args, **kwargs)
    except Miss:
        return "MISS"


gen_derivations.gen_step = gen_step
gen_derivations.log_event = gen_spec.log_spec_event = lambda *args, **kwargs: None
gen_derivations.render_footer = stop  # first call after the generation rounds


def codegen(dataset):
    gen_derivations.feedback_code.clear()
    gen_derivations.main(dataset)


def main(datasets):
    gen_spec.PROPOSED_DIR = gen_shells.OUT_DIR = Path(tempfile.mkdtemp(prefix="replay_check_"))
    jobs = ([("spec", ds, gen_spec.propose) for ds in datasets]
            + [("codegen", ds, codegen) for ds in datasets]
            + [("shells", arm, gen_shells.generate) for arm in ("title", "sap")])
    print(f"{'step':<8} {'target':<7} {'prompts':>7} {'misses':>6}")
    total = {"hit": 0, "miss": 0}
    for step, target, run in jobs:
        if step != "shells" and target not in ADAM_INPUTS:
            print(f"{step:<8} {target:<7} {'-':>7} {'-':>6}  not set up in the pipeline")
            continue
        counts.update(hit=0, miss=0)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                run(target)
        except (Miss, Stop):
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
