from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.core import main
from portable_knowledge.instance import load_instance, validate_project_memory

class CoreContractTests(unittest.TestCase):
    def test_capabilities_does_not_require_a_project_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(main(["--root", directory, "capabilities"]), 0)

    def test_experience_config_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {
                "schema_version": 1, "instance": {"id": "x", "name": "X"},
                "pkc": {"version": "0.2.0rc4", "projection_path": ".local/pkc"},
                "authority": {"registry": "data/registry.json", "actors": "data/actors.json", "store": "data", "knowledge": "knowledge"},
                "identities": {key: {"id": key} for key in ("principal", "executor", "workspace", "writer")},
                "compatibility": {"v1_actor_map": {}},
                "memory": {"roles": [], "contexts": [], "startup_budget": {"max_files": 1, "max_characters": 1}, "applies_to": {"workspace": "."}},
                "evaluation": {"cases_path": "../outside.json"},
                "experience": {"current_surfaces": ["/absolute"], "stale_markers": [""]},
            }
            for path in (root / "data/registry.json", root / "data/actors.json"):
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text("{}")
            (root / "knowledge").mkdir()
            (root / "project-intelligence.json").write_text(json.dumps(config))
            codes = {item["code"] for item in validate_project_memory(load_instance(root))["errors"]}
            self.assertTrue({"EVALUATION_PATH", "EXPERIENCE_PATH", "EXPERIENCE_MARKER"} <= codes)

    def test_fixture_is_business_neutral_and_loads(self):
        root=PACKAGE/'tests/fixtures/minimal'
        raw='\n'.join(p.read_text(encoding='utf-8') for p in root.rglob('*') if p.is_file() and '.local' not in p.parts)
        for forbidden in ('W-','P-','M-','E-','X-','dongzhi','朋友圈'):
            self.assertNotIn(forbidden,raw)
        instance=load_instance(root)
        self.assertEqual(instance.identity['id'],'minimal-existing')
        self.assertTrue(validate_project_memory(instance)['ok'])

if __name__=='__main__': unittest.main()
