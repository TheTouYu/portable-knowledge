"""Registered-only Authority Reference observation and claim coverage validation."""
from __future__ import annotations
import hashlib
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any
POLICIES={"existence_only","review_on_change","invalidate_on_change","manual_review"}
STATES={"committed_baseline","working_tree_observation","released_baseline","external_environment"}
ROLES={"design_intent","current_implementation","documented_contract","external_environment_behavior"}
FACT_CLASSES={"runtime_behavior","public_type_surface","cli_behavior","documented_contract","external_game_evidence","transform_defaults","writeback_behavior","evidence_scope"}

def _safe(value:str)->bool:
 path=PurePosixPath(value); return bool(value) and '\\' not in value and not path.is_absolute() and '..' not in path.parts

def _git(root:Path,*args:str)->subprocess.CompletedProcess[str]:
 return subprocess.run(["git",*args],cwd=root,text=True,encoding="utf-8",stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)

def _committed_bytes(root:Path,path:str)->bytes|None:
 result=_git(root,"show",f"HEAD:{path}")
 return result.stdout.encode("utf-8") if result.returncode==0 else None

def _working_tree_status(root:Path,path:str)->str:
 result=_git(root,"status","--porcelain=v1","--",path)
 if result.returncode!=0: return "unknown"
 return "modified" if result.stdout.strip() else "clean"

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
 fact_classes=ref.get('supports_fact_classes',[])
 if not isinstance(fact_classes,list) or any(value not in FACT_CLASSES for value in fact_classes): fail('AUTHORITY_REF_FACT_CLASS','invalid supports_fact_classes')
 return {'ok':not errors,'command':'validate-authority-ref','errors':errors}

def validate_authority_coverage(claims:list[dict[str,Any]],refs:list[dict[str,Any]])->list[dict[str,Any]]:
 """Require each declared Claim fact class to be supported by a linked reference."""
 findings=[]
 for claim in claims:
  # Evidence-backed classes are covered by the Source/Evidence plane, not machine Authority References.
  required=set(claim.get('fact_classes',[]))-{'external_game_evidence','evidence_scope'}
  supported={fact for ref in refs if claim.get('id') in ref.get('claim_ids',[]) for fact in ref.get('supports_fact_classes',[])}
  missing=sorted(required-supported)
  if missing: findings.append({'code':'AUTHORITY_FACT_COVERAGE','claim_id':claim.get('id'),'missing_fact_classes':missing})
 return findings

def observe_authority_refs(root:Path,refs:list[dict[str,Any]])->list[dict[str,Any]]:
 """Observe registered refs at committed baseline and working tree without repository walking."""
 results=[]
 for ref in refs:
  validation=validate_authority_ref(ref)
  if not validation['ok']:
   results.append({**ref,'status':'invalid_ref','baseline_status':'invalid_ref','working_tree_status':'unknown','effective_status':'invalid_ref','errors':validation['errors']}); continue
  path=root/ref['path']; baseline=ref['baseline_state']; policy=ref['change_policy']; expected=ref.get('approved_hash') or ref.get('fragment_hash')
  working_status=_working_tree_status(root,ref['path'])
  if baseline=='committed_baseline':
   observed=_committed_bytes(root,ref['path'])
   if observed is None and not (root/'.git').exists(): observed=path.read_bytes() if path.exists() else None
  else: observed=path.read_bytes() if path.exists() else None
  if observed is None: baseline_status='invalidated' if policy=='invalidate_on_change' else 'missing'
  elif baseline=='working_tree_observation': baseline_status='working_observation'
  elif policy=='existence_only': baseline_status='current'
  elif policy=='manual_review': baseline_status='manual_review'
  else:
   actual=hashlib.sha256(observed).hexdigest()
   baseline_status='current' if actual==expected else ('invalidated' if policy=='invalidate_on_change' else 'stale')
  effective='pending_review' if baseline_status=='current' and working_status=='modified' else baseline_status
  results.append({**ref,'status':effective,'baseline_status':baseline_status,'working_tree_status':working_status,'effective_status':effective})
 return results

def queryable_claim_ids(claim_ids:set[str],observations:list[dict[str,Any]])->set[str]:
 blocked=set()
 for item in observations:
  if item.get('effective_status',item.get('status')) in {'stale','invalidated','missing','invalid_ref','working_observation','manual_review','pending_review'}: blocked.update(item.get('claim_ids',[]))
 return set(claim_ids)-blocked
