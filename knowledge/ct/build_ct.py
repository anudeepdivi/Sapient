"""Build a compact CDISC controlled-terminology index from the free NCI-EVS
machine-readable CT files (SDTM + ADaM), which are public and license-free.

Downloads the CT text files, parses codelists (definition row = empty Codelist
Code; member rows carry the parent Codelist Code), and writes the codelists we
use for ADaM spec grounding / conformance to knowledge/ct/cdisc_ct.json —
keyed by CDISC submission value. Raw CT downloads are gitignored; this JSON is
the committed artifact. Re-run to refresh against a newer CT release.

Usage: python knowledge/ct/build_ct.py
"""
import csv
import json
import subprocess
from pathlib import Path

CT_DIR = Path(__file__).resolve().parent
SOURCES = {
    "SDTM": "https://evs.nci.nih.gov/ftp1/CDISC/SDTM/SDTM%20Terminology.txt",
    "ADaM": "https://evs.nci.nih.gov/ftp1/CDISC/ADaM/ADaM%20Terminology.txt",
}

# Codelists (by CDISC submission value) used by the ADaM datasets we generate.
# Analysis-level codelists that map cleanly to ADaM variables. (RACEC/ETHNICC in the
# current release are the granular "as collected" verbatim lists — hundreds of values,
# not analysis CT — so they are intentionally excluded.)
WANTED = {
    "SEX", "NCOMPLT", "NY", "AGEU", "DTYPE", "ND", "SBJTSTAT",
}

# Codelists (by NCI code) exported in sdtm.oak ct_spec format for the SDTM layer:
# VSTESTCD, VS Test Name, VS Result Unit, Position, Location, Laterality.
OAK_WANTED = {"C66741", "C67153", "C66770", "C71148", "C74456", "C99073"}


def parse_file(path: Path) -> dict:
    """Return {codelist_code: {'submission': str, 'name': str, 'values': [str], 'terms': [...]}}."""
    lists = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for row in reader:
            if len(row) < 5:
                continue
            code, clist_code, _ext, name, submission = row[0], row[1], row[2], row[3], row[4]
            synonyms = row[5] if len(row) > 5 else ""
            preferred = row[7] if len(row) > 7 else ""
            if not clist_code:  # definition row
                lists.setdefault(code, {"submission": submission, "name": name, "values": [], "terms": []})
            else:               # member term
                lists.setdefault(clist_code, {"submission": None, "name": name, "values": [], "terms": []})
                lists[clist_code]["values"].append(submission)
                lists[clist_code]["terms"].append(
                    {"code": code, "value": submission, "synonyms": synonyms, "preferred": preferred})
    return lists


def main():
    index = {}
    oak_rows = []
    for std, url in SOURCES.items():
        path = CT_DIR / f"{std}_Terminology.txt"
        if not path.exists():
            subprocess.run(["curl", "-sSL", "-o", str(path), url], check=True)
        for clist_code, meta in parse_file(path).items():
            sub = meta["submission"]
            if sub in WANTED and meta["values"]:
                index[sub] = {"name": meta["name"], "values": sorted(set(meta["values"]))}
            if clist_code in OAK_WANTED:
                for t in meta["terms"]:
                    oak_rows.append({
                        "codelist_code": clist_code,
                        "term_code": t["code"],
                        "term_value": t["value"],
                        "collected_value": t["value"],
                        "term_preferred_term": t["preferred"],
                        "term_synonyms": t["synonyms"],
                    })
    out = CT_DIR / "cdisc_ct.json"
    out.write_text(json.dumps(index, indent=1))
    print(f"{out}: {len(index)} codelists — {', '.join(sorted(index))}")
    oak_out = CT_DIR / "oak_ct_spec.csv"
    with oak_out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(oak_rows[0].keys()))
        writer.writeheader()
        writer.writerows(oak_rows)
    print(f"{oak_out}: {len(oak_rows)} terms across {len({r['codelist_code'] for r in oak_rows})} codelists")


if __name__ == "__main__":
    main()
