from pathlib import Path

import yaml

from config import SPONSOR_ENV_DIR


class SponsorEnv:
    def __init__(self, root=None):
        self.root = Path(root) if root else SPONSOR_ENV_DIR

    def _yaml(self, rel_path):
        with open(self.root / rel_path) as f:
            return yaml.safe_load(f)

    def list_standards(self):
        standards = []
        for meta_file in sorted((self.root / "standards").glob("*/metadata.yaml")):
            standards.append(self._yaml(meta_file.relative_to(self.root).as_posix()))
        return standards

    def get_standard(self, dataset):
        for std in self.list_standards():
            if std["dataset"] == dataset:
                return std
        return None

    def get_version(self, dataset, version):
        std = self.get_standard(dataset)
        if not std:
            return None
        for v in std["versions"]:
            if str(v["version"]) == str(version):
                return v
        return None

    def program_path(self, rel_path):
        return self.root / rel_path

    def read_program(self, rel_path):
        return self.program_path(rel_path).read_text()

    def list_capabilities(self):
        meta = self._yaml("modules/metadata.yaml")
        return [fn for fn in meta["functions"] if fn["status"] == "approved"]

    def get_validation_rules(self):
        return self._yaml("validation/rules.yaml")

    def register_capability(self, name, code, meta):
        module_file = self.root / "modules" / f"{name}.R"
        module_file.write_text(code)
        registry = self._yaml("modules/metadata.yaml")
        registry["functions"].append(meta)
        with open(self.root / "modules/metadata.yaml", "w") as f:
            yaml.dump(registry, f, sort_keys=False)
        return module_file
