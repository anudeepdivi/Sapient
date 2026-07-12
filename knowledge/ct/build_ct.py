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


def parse_file(path: Path) -> dict:
    """Return {codelist_code: {'submission': str, 'name': str, 'values': [str]}}."""
    lists = {}
    with path.open(encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        for row in reader:
            if len(row) < 5:
                continue
            code, clist_code, _ext, name, submission = row[0], row[1], row[2], row[3], row[4]
            if not clist_code:  # definition row
                lists.setdefault(code, {"submission": submission, "name": name, "values": []})
            else:               # member term
                lists.setdefault(clist_code, {"submission": None, "name": name, "values": []})
                lists[clist_code]["values"].append(submission)
    return lists


def main():
    index = {}
    for std, url in SOURCES.items():
        path = CT_DIR / f"{std}_Terminology.txt"
        if not path.exists():
            subprocess.run(["curl", "-sSL", "-o", str(path), url], check=True)
        for meta in parse_file(path).values():
            sub = meta["submission"]
            if sub in WANTED and meta["values"]:
                index[sub] = {"name": meta["name"], "values": sorted(set(meta["values"]))}
    out = CT_DIR / "cdisc_ct.json"
    out.write_text(json.dumps(index, indent=1))
    print(f"{out}: {len(index)} codelists — {', '.join(sorted(index))}")


if __name__ == "__main__":
    main()
