from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.core import event_identity

class IdentityContractTests(unittest.TestCase):
    def test_configured_mutation_emits_v2_identity_without_actor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            config={"schema_version":1,"instance":{"id":"x","name":"X"},"pkc":{"version":"0.1.0","projection_path":".local/pkc"},"authority":{"registry":"store/registry.json","actors":"store/actors.json","store":"store","knowledge":"domain"},"identities":{"principal":{"id":"owner"},"executor":{"id":"agent"},"workspace":{"id":"workspace"},"writer":{"id":"channel"}},"memory":{}}
            (root/'project-intelligence.json').write_text(json.dumps(config),encoding='utf-8')
            args=type('Args',(),{"actor":"channel","performed_by":"legacy"})()
            identity=event_identity(root,args)
            self.assertEqual(identity,{"schema_version":2,"principal":"owner","executor":"agent","workspace":"workspace","writer":"channel"})
            self.assertNotIn('actor',identity)

if __name__=='__main__': unittest.main()
