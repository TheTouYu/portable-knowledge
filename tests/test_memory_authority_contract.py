from __future__ import annotations
import hashlib, tempfile, unittest, sys
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.authority import observe_authority_refs, queryable_claim_ids, validate_authority_ref
from portable_knowledge.memory import select_primary_context, startup_memory, lookup_decisions
from portable_knowledge.relations import validate_relations, partition_adapter_output, deduplicate_evidence_pointers
from portable_knowledge.retrieval import RetrievalError, build_progressive_scope, select_intent_route

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
   self.assertEqual(observations[0]['baseline_status'],'stale')
   self.assertEqual(observations[0]['effective_status'],'stale')
   self.assertEqual(queryable_claim_ids({'clm_a','clm_b','clm_c'},observations),{'clm_c'})
   working=dict(review,baseline_state='working_tree_observation',change_policy='existence_only',claim_ids=['clm_c'])
   self.assertEqual(queryable_claim_ids({'clm_c'},observe_authority_refs(root,[working])),set())
 def test_configured_intent_route_returns_only_its_topics(self):
  config={"memory":{"contexts":[{"id":"static","lifecycle":"active"}]},"relations":{"context_nodes":[{"context_id":"static","node_id":"assets"},{"context_id":"static","node_id":"writeback"}]},"retrieval":{"max_topics":3,"intent_routes":[
   {"id":"screenshot-validation","contexts":["static"],"keywords":["截图","位置关系"],"topic_ids":["assembly"],"escalate_to_l3":False},
   {"id":"map-writeback","contexts":["static"],"keywords":["写回地图"],"topic_ids":["closure","writeback"],"escalate_to_l3":True},
  ]}}
  registry={"nodes":[{"id":"assets"},{"id":"writeback"}],"topics":[{"id":"assembly","node_id":"assets"},{"id":"closure","node_id":"assets"},{"id":"writeback","node_id":"writeback"}]}
  screenshot=build_progressive_scope(config,registry,context_id="static",intent="核对截图中的位置关系",limit=3)
  self.assertEqual([x["id"] for x in screenshot["topics"]],["assembly"])
  self.assertFalse(screenshot["route"]["escalate_to_l3"])
  writeback=build_progressive_scope(config,registry,context_id="static",intent="准备写回地图",limit=3)
  self.assertEqual([x["id"] for x in writeback["topics"]],["closure","writeback"])

 def test_unknown_and_ambiguous_intents_fail_closed(self):
  config={"retrieval":{"semantic_groups":{"read_only":["不写回","别动地图","do not write"],"visual_only":["只看图","仅分析图片"]},"intent_routes":[
   {"id":"screenshot","contexts":["c"],"keywords":["截图","只看图","仅分析图片"],"blocked_by":["不看图"]},
   {"id":"writeback","contexts":["c"],"keywords":["写回","ID"],"blocked_by_groups":["read_only","visual_only"]},
  ]}}
  with self.assertRaisesRegex(RetrievalError,"no configured"): select_intent_route(config,context_id="c",intent="未知")
  with self.assertRaisesRegex(RetrievalError,"ambiguous"): select_intent_route(config,context_id="c",intent="看截图并准备写回")
  self.assertEqual(select_intent_route(config,context_id="c",intent="只看图，不写回")["id"],"screenshot")
  self.assertEqual(select_intent_route(config,context_id="c",intent="仅分析图片，别动地图")["id"],"screenshot")
  with self.assertRaisesRegex(RetrievalError,"no configured"): select_intent_route(config,context_id="c",intent="不看图")
  with self.assertRaisesRegex(RetrievalError,"no configured"): select_intent_route(config,context_id="c",intent="VALID identifier")

 def test_dynamic_fallback_is_context_scoped_and_reports_telemetry(self):
  config={"memory":{"contexts":[{"id":"static","lifecycle":"active"},{"id":"compiler","lifecycle":"active"}]},"relations":{"context_nodes":[{"context_id":"static","node_id":"assets"},{"context_id":"compiler","node_id":"compiler"}]},"retrieval":{"max_topics":3,"dynamic":{"candidate_limit":5,"confidence_threshold":0.2,"margin_threshold":0.05},"intent_routes":[]}}
  registry={"nodes":[{"id":"assets","name":"Static assets","boundary":"assembly transforms"},{"id":"compiler","name":"Compiler","boundary":"compiler diagnostics"}],"topics":[{"id":"assembly","node_id":"assets","title":"Component transforms","summary":"local position rotation and scale","keywords":["transform","缩放","局部位置"]},{"id":"diagnosis","node_id":"compiler","title":"Compiler diagnosis","summary":"pipeline failure localization","keywords":["compiler","diagnosis"]}]}
  result=build_progressive_scope(config,registry,context_id="static",intent="How does local component scale affect position?",limit=3)
  self.assertEqual(result["retrieval_strategy"],"dynamic_metadata")
  self.assertEqual([x["id"] for x in result["topics"]],["assembly"])
  self.assertGreaterEqual(result["confidence"],0.2)
  self.assertIn("margin",result)
  self.assertEqual([x["id"] for x in result["candidate_topics"]],["assembly"])

 def test_dynamic_fallback_distinguishes_ambiguous_gap_and_out_of_context(self):
  base={"memory":{"contexts":[{"id":"static","lifecycle":"active"},{"id":"compiler","lifecycle":"active"}]},"relations":{"context_nodes":[{"context_id":"static","node_id":"assets"},{"context_id":"compiler","node_id":"compiler"}]},"retrieval":{"dynamic":{"candidate_limit":5,"confidence_threshold":0.2,"margin_threshold":0.08},"intent_routes":[]}}
  registry={"nodes":[{"id":"assets","name":"Assets","boundary":"asset work"},{"id":"compiler","name":"Compiler","boundary":"compiler work"}],"topics":[{"id":"position","node_id":"assets","title":"Position transform","summary":"component position transform","keywords":["position"]},{"id":"rotation","node_id":"assets","title":"Rotation transform","summary":"component rotation transform","keywords":["rotation"]},{"id":"pipeline","node_id":"compiler","title":"Compiler pipeline","summary":"compiler pipeline diagnostics","keywords":["compiler"]}]}
  with self.assertRaises(RetrievalError) as ambiguous: build_progressive_scope(base,registry,context_id="static",intent="position rotation transform",limit=3)
  self.assertEqual(ambiguous.exception.code,"RETRIEVAL_CANDIDATE_AMBIGUOUS")
  self.assertEqual(ambiguous.exception.details["failure_type"],"ambiguous")
  with self.assertRaises(RetrievalError) as outside: build_progressive_scope(base,registry,context_id="static",intent="compiler pipeline diagnostics",limit=3)
  self.assertEqual(outside.exception.details["failure_type"],"out_of_context")
  with self.assertRaises(RetrievalError) as gap: build_progressive_scope(base,registry,context_id="static",intent="employee payroll vacation policy",limit=3)
  self.assertEqual(gap.exception.details["failure_type"],"coverage_gap")

 def test_explicit_route_precedes_dynamic_fallback(self):
  config={"memory":{"contexts":[{"id":"c","lifecycle":"active"}]},"relations":{"context_nodes":[{"context_id":"c","node_id":"n"}]},"retrieval":{"intent_routes":[{"id":"safe","contexts":["c"],"keywords":["exact"],"topic_ids":["t1"]}],"dynamic":{"confidence_threshold":0.01}}}
  registry={"nodes":[{"id":"n"}],"topics":[{"id":"t1","node_id":"n","title":"First"},{"id":"t2","node_id":"n","title":"exact exact exact"}]}
  result=build_progressive_scope(config,registry,context_id="c",intent="exact",limit=3)
  self.assertEqual(result["retrieval_strategy"],"explicit_route")
  self.assertEqual([x["id"] for x in result["topics"]],["t1"])

 def test_cross_plane_types_partition_and_pointer_deduplication(self):
  relations={"context_nodes":[{"context_id":"alpha","node_id":"diagnostics"},{"context_id":"beta","node_id":"diagnostics"}],"decision_claims":[{"decision_id":"ADR-1","claim_id":"clm_a","relation":"governed_by"}],"evidence_pointers":[{"id":"p1","kind":"trace_only","reality_key":"run-1"},{"id":"p2","kind":"resolvable","reality_key":"run-1"}]}
  self.assertTrue(validate_relations(relations)['ok'])
  self.assertEqual(len(deduplicate_evidence_pointers(relations['evidence_pointers'])),1)
  output=partition_adapter_output(project_state=[{"id":"alpha"}],decisions=[{"id":"ADR-1"}],claims=[{"id":"clm_a"}],authority_refs=[],evidence_pointers=[])
  self.assertEqual(list(output),['current_project_state','governing_decisions','domain_claims','authority_refs','evidence_pointers'])

if __name__=='__main__': unittest.main()
