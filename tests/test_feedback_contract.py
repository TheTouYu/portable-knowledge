from __future__ import annotations
import contextlib, hashlib, io, json, subprocess, sys, tempfile, unittest
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.authority import observe_authority_refs, validate_authority_conflicts, validate_authority_coverage
from portable_knowledge.core import _claim_summary, main, output

class FeedbackContractTests(unittest.TestCase):
 def test_authority_reports_committed_baseline_and_working_tree_separately(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary); subprocess.run(['git','init','-q'],cwd=root,check=True)
   (root/'contract.py').write_text('v1\n',encoding='utf-8')
   subprocess.run(['git','add','contract.py'],cwd=root,check=True)
   subprocess.run(['git','-c','user.name=T','-c','user.email=t@x','commit','-qm','base'],cwd=root,check=True)
   digest=hashlib.sha256((root/'contract.py').read_bytes()).hexdigest()
   ref={'path':'contract.py','locator':'whole','role':'current_implementation','baseline_state':'committed_baseline','approved_hash':digest,'change_policy':'review_on_change','claim_ids':['clm_a'],'supports_fact_classes':['public_type_surface']}
   (root/'contract.py').write_text('v2\n',encoding='utf-8')
   observed=observe_authority_refs(root,[ref])[0]
   self.assertEqual(observed['baseline_status'],'current')
   self.assertEqual(observed['working_tree_status'],'modified')
   self.assertEqual(observed['effective_status'],'pending_review')

 def test_fact_class_coverage_detects_unregistered_dependency(self):
  claims=[{'id':'clm_a','fact_classes':['runtime_behavior','public_type_surface']}]
  refs=[{'id':'auth_a','claim_ids':['clm_a'],'supports_fact_classes':['runtime_behavior']}]
  findings=validate_authority_coverage(claims,refs)
  self.assertEqual(findings,[{'code':'AUTHORITY_FACT_COVERAGE','claim_id':'clm_a','missing_fact_classes':['public_type_surface']}])

 def test_markdown_summary_closes_tokens_and_prefers_semantic_boundaries(self):
  statement=('Stage 3 uses `__composite_call` for the root implementation; this sentence explains the contract. '
             '[Reference](docs/contract.md) remains available.\n\n#### 适用边界\n\nDo not infer external behavior from source alone; verify the real environment.')
  result=_claim_summary(statement,120)
  self.assertTrue(result['summary_truncated'])
  self.assertEqual(result['summary'].count('`') % 2,0)
  self.assertNotIn('](',result['summary'][-3:])
  self.assertIn('适用边界',result['summary'])

 def test_controlled_authority_conflicts_compare_only_explicit_facts(self):
  base={'claim_ids':['clm_a'],'baseline_state':'committed_baseline'}
  refs=[
   {**base,'id':'impl','role':'current_implementation','facts':[{'key':'stage3.default_backend','value':'shared-vendor-impl-graph'}]},
   {**base,'id':'docs','role':'documented_contract','facts':[{'key':'stage3.default_backend','value':'legacy-graph'}]},
   {**base,'id':'body-only','role':'documented_contract','summary':'stage3.default_backend is guessed from prose'},
  ]
  findings=validate_authority_conflicts(refs)
  self.assertEqual(len(findings),1)
  self.assertEqual(findings[0]['code'],'AUTHORITY_CONFLICT')
  self.assertEqual(findings[0]['fact_key'],'stage3.default_backend')

 def test_text_output_exposes_tree_query_and_claim_details(self):
  tree={'ok':True,'command':'tree','nodes':[{'id':'n','name':'Node','topics':[{'id':'t','title':'Topic','claim_count':2}]}]}
  query={'ok':True,'command':'progressive-query','context':{'id':'c'},'intent':'safe','retrieval_strategy':'explicit_route','topics':[{'id':'t','title':'Topic'}],'claims':[{'id':'clm_a','title':'Claim','summary':'Safe boundary'}],'authority_refs':[],'minimum_files':['knowledge/t.md'],'escalate_to_l3':False,'operation_authorized':False,'budget':6000,'used_characters':900,'warnings':['review']}
  claim={'ok':True,'command':'show-claim','claim':{'id':'clm_a','title':'Claim','statement':'Assertion\n\n#### 适用边界\n\nBoundary','confirmation':'unconfirmed','conflict':'none'},'authority_support':{'status':'current','ref_count':2,'pending_review_count':0},'event_evidence':{'status':'not_registered','supporting_kinds':[]},'support_summary':'authority_backed_no_separate_events','evidence_status':'supported','evidence':[]}
  for payload, expected in ((tree,'t — Topic (2 claims)'),(query,'Operation authorized: false'),(claim,'Authority support: current (2 refs)')):
   stream=io.StringIO()
   with contextlib.redirect_stdout(stream): output(payload,'text')
   self.assertIn(expected,stream.getvalue())

 def test_mutation_defaults_come_from_instance_identity(self):
  parser_output=io.StringIO()
  # Parsing reaches source validation, proving the configured writer passed actor validation.
  with contextlib.redirect_stdout(parser_output):
   result=main(['--root',str(PACKAGE/'tests/fixtures/minimal'),'register-source','--source-path','missing.md','--title','x'])
  payload=json.loads(parser_output.getvalue())
  self.assertNotIn('unknown actor',json.dumps(payload))
  self.assertIn('invalid source path',json.dumps(payload))
  self.assertEqual(result,1)

if __name__=='__main__': unittest.main()
