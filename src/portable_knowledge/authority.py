"""Registered-only Authority Reference observation and claim filtering."""
from __future__ import annotations
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any
POLICIES={"existence_only","review_on_change","invalidate_on_change","manual_review"}
STATES={"committed_baseline","working_tree_observation","released_baseline","external_environment"}
ROLES={"design_intent","current_implementation","documented_contract","external_environment_behavior"}

def _safe(value:str)->bool:
 path=PurePosixPath(value); return bool(value) and '\\' not in value and not path.is_absolute() and '..' not in path.parts

def validate_authority_ref(ref:dict[str,Any])->dict[str,Any]:
 errors=[]
 def fail(code,message): errors.append({'code':code,'path':str(ref.get('path','authority_ref')),'message':message})
 for key in ('path','locator','role','baseline_state','change_policy'):
  if not ref.get(key): fail('AUTHORITY_REF_SCHEMA',f'missing {key}')
 if not _safe(ref.get('path','')): fail('AUTHORITY_REF_PATH','path must be portable and relative')
 if ref.get('role') not in ROLES: fail('AUTHORITY_REF_ROLE','invalid role')
 if ref.get('baseline_state') not in STATES: fail('AUTHORITY_REF_STATE','invalid baseline state')
 if ref.get('change_policy') not in POLICIES: fail('AUTHORITY_REF_POLICY','invalid change policy')
 if ref.get('change_policy') in {'review_on_change','invalidate_on_change'} and not (ref.get('approved_hash') or ref.get('fragment_hash')): fail('AUTHORITY_REF_HASH','change-sensitive reference needs approved or fragment hash')
 return {'ok':not errors,'command':'validate-authority-ref','errors':errors}

def observe_authority_refs(root:Path,refs:list[dict[str,Any]])->list[dict[str,Any]]:
 """Observe only explicitly registered refs; never walks the repository."""
 results=[]
 for ref in refs:
  validation=validate_authority_ref(ref)
  if not validation['ok']:
   results.append({**ref,'status':'invalid_ref','errors':validation['errors']}); continue
  path=root/ref['path']
  if not path.exists(): status='invalidated' if ref['change_policy']=='invalidate_on_change' else 'missing'
  elif ref['baseline_state']=='working_tree_observation': status='working_observation'
  elif ref['change_policy'] in {'existence_only','manual_review'}: status='current' if ref['change_policy']=='existence_only' else 'manual_review'
  else:
   actual=hashlib.sha256(path.read_bytes()).hexdigest(); expected=ref.get('approved_hash') or ref.get('fragment_hash')
   status='current' if actual==expected else ('invalidated' if ref['change_policy']=='invalidate_on_change' else 'stale')
  results.append({**ref,'status':status})
 return results

def queryable_claim_ids(claim_ids:set[str],observations:list[dict[str,Any]])->set[str]:
 blocked=set()
 for item in observations:
  if item.get('status') in {'stale','invalidated','missing','invalid_ref','working_observation','manual_review'}: blocked.update(item.get('claim_ids',[]))
 return set(claim_ids)-blocked
