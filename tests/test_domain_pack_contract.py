from __future__ import annotations
import json, sys, unittest
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.domain_pack import load_pack, propose_candidates, validate_pack
from test_profile_blueprint_contract import PROFILE

class DomainPackContractTests(unittest.TestCase):
    def test_only_two_existing_project_packs_are_valid_and_fact_free(self):
        personal=load_pack(PACKAGE,'personal-brand-existing'); software=load_pack(PACKAGE,'software-existing')
        self.assertTrue(validate_pack(personal)['ok']); self.assertTrue(validate_pack(software)['ok'])
        self.assertNotEqual(personal['candidate_facets'],software['candidate_facets'])
        raw=json.dumps([personal,software],ensure_ascii=False)
        for forbidden in ('dongzhi','朋友圈','Composite','GIA','GraphNode','Genshin-TS','~/'):
            self.assertNotIn(forbidden,raw)
        self.assertTrue(all('claims' not in pack for pack in (personal, software)))
    def test_packs_define_evidence_non_substitution_and_confirmation_rules(self):
        for pack_id in ('personal-brand-existing','software-existing'):
            pack=load_pack(PACKAGE,pack_id)
            self.assertGreaterEqual(len(pack['evidence_kinds']),2)
            self.assertTrue(pack['claim_confirmation_rules'])
            self.assertTrue(pack['non_substitutable_evidence'])
            self.assertTrue(pack['representative_query_seeds'])
            self.assertEqual(pack['upgrade_policy'],'never_rewrite_instance')
    def test_each_pack_proposes_two_or_three_non_authority_distinct_candidates(self):
        personal=propose_candidates(PROFILE,load_pack(PACKAGE,'personal-brand-existing'))
        software=propose_candidates(PROFILE,load_pack(PACKAGE,'software-existing'))
        self.assertIn(len(personal), (2,3)); self.assertIn(len(software),(2,3))
        self.assertTrue(all(c['authority'] is False and 'claims' not in c for c in personal+software))
        self.assertNotEqual(personal[0]['nodes'][0]['id'],software[0]['nodes'][0]['id'])

if __name__=='__main__': unittest.main()
