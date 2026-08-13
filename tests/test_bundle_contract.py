from __future__ import annotations
import contextlib, io, json, shutil, sys, tempfile, unittest
from pathlib import Path

PACKAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PACKAGE/'src'))
from portable_knowledge.bundle import BundleError, apply_bundle, approval, build_bundle, build_migration_plan, capture_bundle_draft, lifecycle_projection, seal_preflight, verify_bundle, verify_migration_plan
from portable_knowledge.core import main, transactional_replace

IDENTITIES={"principal":{"id":"owner"},"executor":{"id":"agent"},"workspace":{"id":"test"},"writer":{"id":"channel"}}

class BundleContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        (self.root/'data/knowledge').mkdir(parents=True)
        (self.root/'data/knowledge/a.txt').write_text('before\n',encoding='utf-8')
        self.manifest={"bundle_type":"claim_revise","intent":"Clarify one claim","semantic_diff":{"before":"before","after":"after"},"evidence_refs":[],"authority_refs":[],"permission_effect":"none","risk":"medium","actions":[{"operation":"replace","path":"data/knowledge/a.txt","content":"after\n"}]}
    def tearDown(self): self.temp.cleanup()
    def test_hash_lock_and_principal_approval(self):
        bundle=build_bundle(self.root,self.manifest,IDENTITIES)
        from portable_knowledge.bundle import seal_preflight
        bundle=seal_preflight(bundle,[]); verify_bundle(bundle)
        approved=approval(bundle,'owner')
        tampered=dict(bundle); tampered['intent']='changed'
        with self.assertRaises(BundleError): apply_bundle(self.root,tampered,approved,transactional_replace)
    def test_apply_failure_writes_zero_authority(self):
        self.manifest['actions'].append({"operation":"replace","path":"data/knowledge/b.txt","content":"new\n"})
        from portable_knowledge.bundle import seal_preflight
        bundle=seal_preflight(build_bundle(self.root,self.manifest,IDENTITIES),[]); approved=approval(bundle,'owner')
        (self.root/'data/knowledge/a.txt').write_text('concurrent\n',encoding='utf-8')
        before={p:p.read_bytes() for p in (self.root/'data/knowledge').glob('*.txt')}
        with self.assertRaises(BundleError): apply_bundle(self.root,bundle,approved,transactional_replace)
        self.assertEqual(before,{p:p.read_bytes() for p in (self.root/'data/knowledge').glob('*.txt')})
        self.assertFalse((self.root/'data/knowledge/b.txt').exists())
    def test_capture_only_returns_an_existing_bundle_draft(self):
        request={**self.manifest,"capture_checks":{"duplicate":"checked","conflict":"checked","authority":"checked","scope":"checked","repository_state":"working_tree_observation","deletion_test":"passed"}}
        result=capture_bundle_draft(self.root,request,IDENTITIES)
        self.assertEqual(result["command"],"capture")
        self.assertTrue(result["draft_only"])
        self.assertFalse(result["approved"])
        self.assertFalse(result["applied"])
        verify_bundle(result["bundle"])
        self.assertFalse((self.root/'data/knowledge/bundles').exists())

    def test_capture_fails_closed_when_required_checks_are_missing(self):
        with self.assertRaisesRegex(BundleError,"capture_checks"):
            capture_bundle_draft(self.root,self.manifest,IDENTITIES)

    def test_capture_and_create_fail_preflight_with_all_findings_and_zero_writes(self):
        fixture=PACKAGE/'tests/fixtures/minimal'
        shutil.copytree(fixture,self.root,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.local'))
        config=json.loads((self.root/'project-intelligence.json').read_text(encoding='utf-8'))
        config['authority']['authority_refs']='data/store/authority-refs.json'
        (self.root/'project-intelligence.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
        (self.root/'data/store/authority-refs.json').write_text('{"schema_version": 1, "refs": []}\n',encoding='utf-8')
        registry=json.loads((self.root/'data/store/registry.json').read_text(encoding='utf-8'))
        claim_id='clm_00000000000000000000000000'
        registry['claim_metadata']={claim_id:{'fact_classes':['documented_contract','runtime_behavior']}}
        manifest={
            'bundle_type':'claim_revise','intent':'Declare controlled facts','semantic_diff':{'before':'none','after':'facts'},
            'evidence_refs':[],'authority_refs':[],'permission_effect':'none','risk':'medium',
            'actions':[{'operation':'replace','path':'data/store/registry.json','content':json.dumps(registry,indent=2)+'\n'}],
            'capture_checks':{'duplicate':'checked','conflict':'checked','authority':'checked','scope':'checked','repository_state':'committed_baseline','deletion_test':'passed'},
        }
        manifest_path=self.root/'manifest.json'; manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
        before=(self.root/'data/store/registry.json').read_bytes()
        for command in (['capture','--manifest',str(manifest_path)],['bundle-create','--manifest','manifest.json'],['bundle-create','--manifest','manifest.json','--apply']):
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream): result=main(['--root',str(self.root),*command])
            payload=json.loads(stream.getvalue())
            self.assertEqual(result,1)
            self.assertEqual({item['code'] for item in payload['errors']},{'AUTHORITY_FACT_COVERAGE'})
            finding=payload['errors'][0]
            self.assertEqual(finding['phase'],'preflight')
            self.assertEqual(finding['claim_id'],claim_id)
            self.assertEqual(finding['missing_fact_classes'],['documented_contract','runtime_behavior'])
            self.assertEqual((self.root/'data/store/registry.json').read_bytes(),before)
            self.assertFalse((self.root/'data/knowledge/bundles').exists())
            self.assertFalse((self.root/'data/store/bundles').exists())

    def test_bundle_inspect_human_review_contains_semantics_and_exact_hash(self):
        shutil.copytree(PACKAGE/'tests/fixtures/minimal',self.root,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.local'))
        bundle=seal_preflight(build_bundle(self.root,self.manifest,IDENTITIES),[])
        directory=self.root/'data/knowledge/bundles'; directory.mkdir(parents=True)
        (directory/f"{bundle['bundle_id']}.json").write_text(json.dumps(bundle),encoding='utf-8')
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream): result=main(['--root',str(self.root),'bundle-inspect',bundle['bundle_id'],'--format','text'])
        output=stream.getvalue()
        self.assertEqual(result,0)
        self.assertIn(bundle['content_hash'],output)
        self.assertIn('only approval credential',output)
        self.assertIn('Semantic diff:',output)
        self.assertIn('Permission effect: none',output)
        self.assertIn('Operations: {"replace": 1}',output)
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream): result=main(['--root',str(self.root),'bundle-status',bundle['bundle_id']])
        status=json.loads(stream.getvalue())
        self.assertEqual(result,0)
        self.assertEqual(status['count'],1)
        self.assertEqual(status['bundles'][0]['bundle_id'],bundle['bundle_id'])

    def test_bundle_lifecycle_projection_is_append_only_and_preserves_supersede(self):
        old=seal_preflight(build_bundle(self.root,self.manifest,IDENTITIES),[])
        revised={**self.manifest,'intent':'Correct the invalid draft'}
        new=seal_preflight(build_bundle(self.root,revised,IDENTITIES),[])
        events=[
            {'event_type':'bundle_failed','bundle_id':old['bundle_id'],'failure_phase':'preflight','reason':'coverage'},
            {'event_type':'bundle_superseded','bundle_id':old['bundle_id'],'superseded_by':new['bundle_id'],'reason':'correct authority coverage'},
        ]
        projected=lifecycle_projection(old,approved=True,applied=False,events=events)
        self.assertEqual(projected['state'],'superseded')
        self.assertEqual(projected['failure_phase'],'preflight')
        self.assertEqual(projected['superseded_by'],new['bundle_id'])
        self.assertEqual(projected['reason'],'correct authority coverage')
        self.assertEqual(len(events),2)

    def test_bundle_lifecycle_matrix(self):
        bundle=seal_preflight(build_bundle(self.root,self.manifest,IDENTITIES),[])
        cases=[
            (False,False,[],'draft'),(True,False,[],'approved'),(True,True,[],'applied'),
            (True,False,[{'event_type':'bundle_failed','failure_phase':'apply','reason':'drift'}],'failed'),
            (True,False,[{'event_type':'bundle_abandoned','reason':'cancelled'}],'abandoned'),
            (True,True,[{'event_type':'bundle_rolled_back','reason':'regression'}],'rolled_back'),
        ]
        for approved,applied,events,state in cases:
            projected=lifecycle_projection(bundle,approved=approved,applied=applied,events=events)
            self.assertEqual(projected['state'],state)

    def test_migration_plan_parent_hash_covers_ordered_children_dependencies_and_risk(self):
        first=seal_preflight(build_bundle(self.root,self.manifest,IDENTITIES),[])
        second_manifest={**self.manifest,'intent':'Second phase','risk':'high'}
        second=seal_preflight(build_bundle(self.root,second_manifest,IDENTITIES),[])
        plan=build_migration_plan([first,second],dependencies={second['bundle_id']:[first['bundle_id']]})
        verify_migration_plan(plan,{first['bundle_id']:first,second['bundle_id']:second})
        changed=seal_preflight(build_bundle(self.root,{**second_manifest,'intent':'Changed second phase'},IDENTITIES),[])
        with self.assertRaises(BundleError):
            verify_migration_plan(plan,{first['bundle_id']:first,second['bundle_id']:changed})
        self.assertFalse(plan['cross_phase_atomic'])

    def test_controlled_bundle_classes_are_independent(self):
        for kind in ('source_evidence','claim_create','claim_revise','authority_maintenance','permission_expansion','lifecycle_change','node_boundary_change'):
            manifest=dict(self.manifest); manifest['bundle_type']=kind
            self.assertEqual(build_bundle(self.root,manifest,IDENTITIES)['bundle_type'],kind)

    def test_bundle_approve_and_apply_help_require_exact_content_hash(self):
        for command in ('bundle-approve','bundle-apply'):
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):
                with self.assertRaises(SystemExit) as raised:
                    main([command,'--help'])
            self.assertEqual(raised.exception.code,0)
            help_output=stream.getvalue()
            flat=' '.join(help_output.split())
            compact=''.join(help_output.split())
            self.assertIn('REQUIRED',flat)
            self.assertIn('bundle-status',compact)
            self.assertIn('bundle-inspect',compact)
            self.assertIn('same hash',flat)

    def test_bundle_status_and_inspect_help_surface_the_exact_hash(self):
        for command in ('bundle-status','bundle-inspect'):
            stream=io.StringIO()
            with contextlib.redirect_stdout(stream):
                with self.assertRaises(SystemExit) as raised:
                    main([command,'--help'])
            self.assertEqual(raised.exception.code,0)
            self.assertIn('content hash',stream.getvalue())

if __name__=='__main__': unittest.main()
