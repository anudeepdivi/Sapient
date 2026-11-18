"""Generate mock shells for the pilot SAP's 24 display templates.

Usage: python scripts/gen_shells.py title|sap   -> data/mockshells/<arm>.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from specs.shells import generate

if __name__ == "__main__":
    print(generate(sys.argv[1]))
