from __future__ import annotations
import tempfile, unittest
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "src"))

from portable_knowledge.profile import DiscoveryError, prepare_remote_input, validate_discovery_manifest, validate_profile
from portable_knowledge.blueprint import BlueprintError, approve_blueprint, apply_blueprint, validate_candidate


PROFILE = {
    "schema_version": 1,
    "project": {"id": "sample", "name": "Sample", "goal": "Ship reliable work", "users": ["owner"]},
    "primary_production_task": "Resolve one high-value customer problem",
    "machine_truth_sources": [{"path": "src", "state": "committed_baseline", "role": "implementation"}],
    "memory_role_candidates": [{"role": "current_recovery", "path": "STATUS.md", "status": "mapped"}],
    "input_types": ["request"], "evidence_types": ["user_validation"],
    "state_sources": {"committed": ["src"], "working": ["git status"], "released": ["CHANGELOG.md"], "external": ["user environment"]},
    "policy": {"permissions": "owner-controlled", "remote_models": "authorized_bounded_content_only", "local_only_paths": ["private"]},
    "completion_gates": ["tests pass"], "exclusions": ["git history", "generated directories"]
}
MANIFEST = {
    "schema_version": 1, "read_paths": ["STATUS.md"], "excluded_paths": [".env", ".git", "vendor"],
    "expansions": [], "working_tree": {"branch": "main", "status": "clean"},
    "model": {"provider": "none", "name": "none", "transfer": "local_summary"}
}
CANDIDATE = {
    "schema_version": 1, "candidate_id": "focused", "authority": False,
    "production_task": PROFILE["primary_production_task"],
    "nodes": [{"id": "delivery", "topics": [{"id": "delivery-diagnosis", "title": "Diagnosis"}]}],
    "include": ["stable diagnostic constraints"], "exclude": ["project log"],
    "memory_roles": PROFILE["memory_role_candidates"],
    "files": [{"path": "ppi/generated/router.json", "content": "{\"schema_version\":1}\n"}]
}
PROVENANCE = {"profile_hash": "a" * 64, "pack": {"id": "software-existing", "version": "1.0.0"},
              "model": {"provider": "local", "name": "test"}, "read_paths": ["STATUS.md"],
              "excluded_paths": [".env"], "working_tree": {"branch": "main", "status": "clean"},
              "candidate_ids": ["focused"], "user_decisions": ["approve focused"]}


class ProfileBlueprintContractTests(unittest.TestCase):
    def test_profile_and_bounded_manifest_validate(self):
        self.assertTrue(validate_profile(PROFILE)["ok"])
        self.assertTrue(validate_discovery_manifest(MANIFEST)["ok"])
        invalid = dict(MANIFEST); invalid["read_paths"] = [".git/logs/HEAD"]
        self.assertFalse(validate_discovery_manifest(invalid)["ok"])

    def test_secret_scan_precedes_remote_payload(self):
        with self.assertRaises(DiscoveryError):
            prepare_remote_input({".env": "API_KEY=secret-value-123456789"}, MANIFEST)
        payload = prepare_remote_input({"STATUS.md": "bounded summary"}, MANIFEST)
        self.assertEqual(payload["content_mode"], "local_summary")
        self.assertNotIn(".env", str(payload))

    def test_candidate_is_non_authority_and_requires_explicit_approval(self):
        self.assertTrue(validate_candidate(CANDIDATE, PROFILE)["ok"])
        bad = dict(CANDIDATE); bad["authority"] = True
        self.assertFalse(validate_candidate(bad, PROFILE)["ok"])
        with self.assertRaises(BlueprintError): approve_blueprint(CANDIDATE, PROVENANCE, principal="owner", explicit=False)

    def test_approved_apply_is_dry_run_idempotent_and_never_overwrites(self):
        approved = approve_blueprint(CANDIDATE, PROVENANCE, principal="owner", explicit=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dry = apply_blueprint(root, approved)
            self.assertTrue(dry["dry_run"]); self.assertFalse((root / "ppi/generated/router.json").exists())
            first = apply_blueprint(root, approved, apply=True)
            self.assertEqual(first["created_files"], ["ppi/generated/router.json"])
            second = apply_blueprint(root, approved, apply=True)
            self.assertEqual(second["created_files"], []); self.assertEqual(second["unchanged_files"], ["ppi/generated/router.json"])
            (root / "ppi/generated/router.json").write_text("different\n", encoding="utf-8")
            with self.assertRaises(BlueprintError): apply_blueprint(root, approved, apply=True)

if __name__ == "__main__": unittest.main()
