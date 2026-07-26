from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path

PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.bundle import BundleError, apply_bundle, approval, build_bundle, verify_bundle
from portable_knowledge.core import transactional_replace

IDENTITIES={"principal":{"id":"owner"},"executor":{"id":"agent"},"workspace":{"id":"test"},"writer":{"id":"channel"}}

class BundleContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        (self.root/'data/knowledge').mkdir(parents=True)
        (self.root/'data/knowledge/a.txt').write_text('before\n',encoding='utf-8')
        self.manifest={"bundle_type":"claim_revise","intent":"Clarify one claim","semantic_diff":{"before":"before","after":"after"},"evidence_refs":[],"authority_refs":[],"permission_effect":"none","risk":"medium","actions":[{"operation":"replace","path":"data/knowledge/a.txt","content":"after\n"}]}
    def tearDown(self): self.temp.cleanup()
    def test_hash_lock_and_principal_approval(self):
        bundle=build_bundle(self.root,self.manifest,IDENTITIES); verify_bundle(bundle)
        approved=approval(bundle,'owner')
        tampered=dict(bundle); tampered['intent']='changed'
        with self.assertRaises(BundleError): apply_bundle(self.root,tampered,approved,transactional_replace)
    def test_apply_failure_writes_zero_authority(self):
        self.manifest['actions'].append({"operation":"replace","path":"data/knowledge/b.txt","content":"new\n"})
        bundle=build_bundle(self.root,self.manifest,IDENTITIES); approved=approval(bundle,'owner')
        (self.root/'data/knowledge/a.txt').write_text('concurrent\n',encoding='utf-8')
        before={p:p.read_bytes() for p in (self.root/'data/knowledge').glob('*.txt')}
        with self.assertRaises(BundleError): apply_bundle(self.root,bundle,approved,transactional_replace)
        self.assertEqual(before,{p:p.read_bytes() for p in (self.root/'data/knowledge').glob('*.txt')})
        self.assertFalse((self.root/'data/knowledge/b.txt').exists())
    def test_controlled_bundle_classes_are_independent(self):
        for kind in ('claim_create','claim_revise','permission_expansion','lifecycle_change','node_boundary_change'):
            manifest=dict(self.manifest); manifest['bundle_type']=kind
            self.assertEqual(build_bundle(self.root,manifest,IDENTITIES)['bundle_type'],kind)

if __name__=='__main__': unittest.main()
