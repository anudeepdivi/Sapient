"""TC-R-011 dependency-aware impact analysis.

The sponsor environment already declares its dependency structure in
metadata: each standard lists the modules it sources (`modules:`) and may
declare standard-level edges (`depends_on_standards:`). This module turns
those declarations into an impact map for a set of changed modules and
scores whether the validation/preservation work actually done covered
exactly that map. Deterministic metadata arithmetic — no code parsing, no LLM.
"""


def _norm_module(name):
    name = str(name).replace("\\", "/")
    return name if "/" in name else "modules/" + name


def impact(env, changed_modules):
    """Partition approved standards by their relation to changed modules.

    Blast radius is bidirectional over the declared graph: a standard whose
    declared module changed is affected, and so is everything that declares
    dependence on it (transitively); the declared dependencies of the affected
    set become the preserve set. Dataset names are compared case-insensitively
    (uniformly upper-cased). Changed modules that no standard declares are
    surfaced in unmatched_changed_modules instead of silently scoring a
    vacuous map.
    """
    changed = {_norm_module(m) for m in changed_modules}
    module_map, edges = {}, {}
    for std in env.list_standards():
        dataset = str(std["dataset"]).upper()
        module_map[dataset] = {_norm_module(m) for m in std.get("modules") or []}
        edges[dataset] = {str(d).upper() for d in std.get("depends_on_standards") or []}

    affected = {d for d, mods in module_map.items() if mods & changed}

    # downstream dependents of affected standards are affected too
    dependents = {}
    for d, ds in edges.items():
        for dep in ds:
            dependents.setdefault(dep, set()).add(d)
    frontier = list(affected)
    while frontier:
        nxt = []
        for dataset in frontier:
            for child in dependents.get(dataset, ()):
                if child in module_map and child not in affected:
                    affected.add(child)
                    nxt.append(child)
        frontier = nxt

    # transitive declared dependencies of affected standards, minus affected
    preserve, frontier = set(), list(affected)
    while frontier:
        nxt = []
        for dataset in frontier:
            for dep in edges.get(dataset, ()):
                if dep in module_map and dep not in preserve and dep not in affected:
                    preserve.add(dep)
                    nxt.append(dep)
        frontier = nxt
    affected = sorted(affected)
    preserve = sorted(preserve - set(affected))
    unaffected = sorted(set(module_map) - set(affected) - set(preserve))

    unknown_deps = sorted({d for ds in edges.values() for d in ds} - set(module_map))
    declared = set().union(*module_map.values()) if module_map else set()
    return {
        "changed_modules": sorted(changed),
        "unmatched_changed_modules": sorted(changed - declared),
        "affected": affected,
        "preserve": preserve,
        "unaffected": unaffected,
        "module_map": {d: sorted(m) for d, m in module_map.items()},
        "edges": {d: sorted(e) for d, e in edges.items() if e},
        "unknown_dependencies": unknown_deps,
    }


def path_metrics(impacted, revalidated=(), preserved_verified=(),
                 preserved_identical=()):
    """Score the validation work actually done against the required map.

    revalidated: standards re-validated after the change (any oracle)
    preserved_verified: declared dependencies whose base-vs-view output was
        compared at all
    preserved_identical: declared dependencies proven byte/output identical
    A vacuous denominator scores 1.0 (nothing was required).
    """
    affected = set(impacted["affected"])
    preserve = set(impacted["preserve"])
    reval, pver, pid = (set(revalidated), set(preserved_verified),
                        set(preserved_identical))

    def ratio(num, den):
        return len(num) / len(den) if den else 1.0

    return {
        "validation_precision": ratio(reval & affected, reval),
        "validation_recall": ratio(reval & affected, affected),
        "preservation_recall": ratio(pver & preserve, preserve),
        "preservation_accuracy": ratio(pid & preserve, preserve),
    }
