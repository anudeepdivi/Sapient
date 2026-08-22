from datetime import datetime
from pathlib import Path

import yaml

from config import HARNESS_GENERATOR, HARNESS_STATE_DIR
from harness.gates import run_checks
from harness.generators import generate
from harness.r_executor import run_r_script


class CapabilityNotApproved(Exception):
    pass


def _proposals_dir(state_dir):
    return Path(state_dir) / "proposals"


def proposal_path(state_dir, name):
    return _proposals_dir(state_dir) / f"{name}.yaml"


def load_proposal(state_dir, name):
    with open(proposal_path(state_dir, name)) as f:
        return yaml.safe_load(f)


def _save(state_dir, proposal):
    path = proposal_path(state_dir, proposal["capability"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(proposal, f, sort_keys=False)
    return path


def _history(proposal, step, result):
    proposal["history"].append(
        {"step": step, "timestamp": datetime.now().isoformat(), "result": result})


def propose(name, requirement, env, state_dir, generator=None):
    proposal = {
        "capability": name,
        "requirement_id": requirement.get("requirement_id"),
        "purpose": requirement.get("purpose"),
        "version": "1.0.0",
        "generator": generator or HARNESS_GENERATOR,
        "model": None,
        "status": "proposed",
        "implementation_file": None,
        "tests_file": None,
        "dependencies": ["dplyr"],
        "datasets": [],
        "owner": "sapient",
        "approval": None,
        "registration": None,
        "history": [],
    }
    _history(proposal, "proposed", "ok")
    _save(state_dir, proposal)
    return proposal


def implement(proposal, env, state_dir, generator=None):
    generator = generator or proposal["generator"]
    pdir = _proposals_dir(state_dir)
    pdir.mkdir(parents=True, exist_ok=True)
    impl_code = generate("implementation", proposal, generator)
    tests_code = generate("tests", proposal, generator)
    impl_path = pdir / f"{proposal['capability']}.R"
    tests_path = pdir / f"test-{proposal['capability']}.R"
    impl_path.write_text(impl_code)
    tests_path.write_text(tests_code.replace("__IMPL_PATH__", str(impl_path.resolve())))
    proposal["implementation_file"] = impl_path.name
    proposal["tests_file"] = tests_path.name
    proposal["generator"] = generator
    proposal["status"] = "implemented"
    _history(proposal, "implemented", "ok")
    _save(state_dir, proposal)
    return proposal


def validate(proposal, env, state_dir):
    pdir = _proposals_dir(state_dir)
    impl_code = (pdir / proposal["implementation_file"]).read_text()
    rules = env.get_validation_rules()
    gate = run_checks(impl_code, rules)
    if gate["passed"]:
        timeout = rules.get("execution_timeout_seconds", 120)
        test_result = run_r_script(
            f'testthat::test_file("{(pdir / proposal["tests_file"]).resolve()}", '
            'stop_on_failure=TRUE)',
            name="capability_tests", cwd=pdir, timeout=timeout,
        )
        passed = test_result["success"]
        detail = "" if passed else (test_result["stdout"] + test_result["stderr"])[-800:]
    else:
        passed = False
        detail = "; ".join(gate["issues"])
    proposal["validation"] = {"gate_passed": gate["passed"], "detail": detail}
    proposal["status"] = "awaiting_approval" if passed else "failed_validation"
    _history(proposal, "validated", "passed" if passed else "failed")
    _save(state_dir, proposal)
    return proposal


def approve(proposal, actor, state_dir):
    if proposal["status"] != "awaiting_approval":
        raise CapabilityNotApproved(
            f"cannot approve capability in status {proposal['status']}")
    proposal["approval"] = {"actor": actor, "timestamp": datetime.now().isoformat()}
    proposal["status"] = "approved"
    _history(proposal, "approved", f"by {actor}")
    _save(state_dir, proposal)
    return proposal


def register(proposal, env, state_dir):
    if proposal.get("status") == "failed_validation" or not proposal.get("approval"):
        raise CapabilityNotApproved(
            f"capability {proposal['capability']} is not approved for registration")
    impl_code = (_proposals_dir(state_dir) / proposal["implementation_file"]).read_text()
    meta = {
        "name": proposal["capability"],
        "file": f"{proposal['capability']}.R",
        "signature": f"{proposal['capability']}(data, ...)",
        "status": "approved",
        "validated": True,
        "version": proposal["version"],
        "purpose": proposal.get("purpose"),
        "datasets": proposal.get("datasets", []),
        "source": "sapient-generated",
    }
    module_file = env.register_capability(proposal["capability"], impl_code, meta)
    proposal["status"] = "registered"
    proposal["registration"] = {"module_file": str(module_file)}
    _history(proposal, "registered", str(module_file))
    _save(state_dir, proposal)
    return proposal
