import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent


class HarnessTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env_root = self.tmp / "sponsor_r_env"
        shutil.copytree(BASE_DIR / "sponsor_r_env", self.env_root)
        self.state_dir = self.tmp / "state"
        self.state_dir.mkdir()

    def load_case(self, name):
        with open(BASE_DIR / "tests" / "cases" / f"{name}.yaml") as f:
            return yaml.safe_load(f)
