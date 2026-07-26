from __future__ import annotations
import hashlib, tempfile, unittest, sys
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.authority import observe_authority_refs, queryable_claim_ids, validate_authority_ref
from portable_knowledge.memory import select_primary_context, startup_memory, lookup_decisions
from portable_knowledge.relations import validate_relations, partition_adapter_output, deduplicate_evidence_pointers

CONTEXTS=[
 {"id":"alpha","lifecycle":"active","goal":"Alpha","current_recovery":"memory/alpha.md","priority":1,"applies_to":{"paths":["src/alpha/**"],"workspaces":["main"],"branches":["main"]}},
 {"id":"beta","lifecycle":"paused","goal":"Beta","current_recovery":"memory/beta.md","priority":2,"applies_to":{"paths":["src/beta/**"],"workspaces":["main"],"branches":["feature/*"]}},
 {"id":"old","lifecycle":"completed","goal":"Old","current_recovery":"memory/old.md","priority":3,"applies_to":{"paths":["**"]}}
]

class MemoryAuthorityContractTests(unittest.TestCase):
 def test_primary_selection_order_and_ambiguity(self):
  self.assertEqual(select_primary_context(CONTEXTS,user_context='beta',task_path='src/alpha/x.py',workspace='main',branch='main')['context']['id'],'beta')
  self.assertEqual(select_primary_context(CONTEXTS,task_path='src/alpha/x.py',workspace='main',branch='main')['context']['id'],'alpha')
  ambiguous=[dict(CONTEXTS[0]),dict(CONTEXTS[0],id='alpha-two')]
  self.assertEqual(select_primary_context(ambiguous,task_path='src/alpha/x.py',workspace='main',branch='main')['status'],'ambiguous')
 def test_scope_mismatch_and_startup_excludes_completed(self):
  result=select_primary_context(CONTEXTS,user_context='beta',workspace='main',branch='main')
  self.assertEqual(result['status'],'scope_mismatch')
  startup=startup_memory(CONTEXTS,CONTEXTS[0],max_contexts=2)
  self.assertEqual([x['id'] for x in startup['router']['contexts']],['alpha','beta'])
  self.assertEqual(startup['primary']['id'],'alpha')
 def test_active_needs_recovery_and_decisions_are_targeted(self):
  invalid=[dict(CONTEXTS[0],current_recovery='')]
  self.assertEqual(startup_memory(invalid,invalid[0])['status'],'invalid')
  decisions=[{"id":"ADR-1","title":"Storage boundary","keywords":["storage"],"body":"intent"},{"id":"ADR-2","title":"UI","keywords":["interface"],"body":"intent"}]
  self.assertEqual([x['id'] for x in lookup_decisions(decisions,decision_id='ADR-1')],['ADR-1'])
  self.assertEqual([x['id'] for x in lookup_decisions(decisions,keyword='interface')],['ADR-2'])
  self.assertEqual(lookup_decisions(decisions,keyword='project log'),[])
 def test_authority_change_policy_affects_default_queries_without_scanning(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); (root/'src').mkdir(); target=root/'src/contract.py'; target.write_text('v1\n')
   digest=hashlib.sha256(target.read_bytes()).hexdigest()
   review={"path":"src/contract.py","locator":"symbol:Contract","role":"current_implementation","baseline_state":"committed_baseline","approved_hash":digest,"change_policy":"review_on_change","claim_ids":["clm_a"]}
   invalid=dict(review,change_policy='invalidate_on_change',claim_ids=['clm_b'])
   self.assertTrue(validate_authority_ref(review)['ok'])
   target.write_text('v2\n')
   observations=observe_authority_refs(root,[review,invalid])
   self.assertEqual([x['status'] for x in observations],['stale','invalidated'])
   self.assertEqual(queryable_claim_ids({'clm_a','clm_b','clm_c'},observations),{'clm_c'})
   working=dict(review,baseline_state='working_tree_observation',change_policy='existence_only',claim_ids=['clm_c'])
   self.assertEqual(queryable_claim_ids({'clm_c'},observe_authority_refs(root,[working])),set())
 def test_cross_plane_types_partition_and_pointer_deduplication(self):
  relations={"context_nodes":[{"context_id":"alpha","node_id":"diagnostics"},{"context_id":"beta","node_id":"diagnostics"}],"decision_claims":[{"decision_id":"ADR-1","claim_id":"clm_a","relation":"governed_by"}],"evidence_pointers":[{"id":"p1","kind":"trace_only","reality_key":"run-1"},{"id":"p2","kind":"resolvable","reality_key":"run-1"}]}
  self.assertTrue(validate_relations(relations)['ok'])
  self.assertEqual(len(deduplicate_evidence_pointers(relations['evidence_pointers'])),1)
  output=partition_adapter_output(project_state=[{"id":"alpha"}],decisions=[{"id":"ADR-1"}],claims=[{"id":"clm_a"}],authority_refs=[],evidence_pointers=[])
  self.assertEqual(list(output),['current_project_state','governing_decisions','domain_claims','authority_refs','evidence_pointers'])

if __name__=='__main__': unittest.main()
