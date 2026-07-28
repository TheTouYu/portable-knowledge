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

    def test_fixture_is_business_neutral_and_loads(self):
        root=PACKAGE/'tests/fixtures/minimal'
        raw='\n'.join(p.read_text(encoding='utf-8') for p in root.rglob('*') if p.is_file() and '.local' not in p.parts)
        for forbidden in ('W-','P-','M-','E-','X-','dongzhi','朋友圈'):
            self.assertNotIn(forbidden,raw)
        instance=load_instance(root)
        self.assertEqual(instance.identity['id'],'minimal-existing')
        self.assertTrue(validate_project_memory(instance)['ok'])

if __name__=='__main__': unittest.main()
