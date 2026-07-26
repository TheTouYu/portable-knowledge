"""Typed cross-plane relationships and partitioned Adapter output."""
from __future__ import annotations
from typing import Any
DECISION_RELATIONS={'motivated_by','governed_by','implemented_by','validated_by','superseded_by'}
POINTER_KINDS={'trace_only','resolvable','unavailable'}

def validate_relations(value:dict[str,Any])->dict[str,Any]:
 errors=[]
 for item in value.get('context_nodes',[]):
  if not item.get('context_id') or not item.get('node_id'):errors.append({'code':'CONTEXT_NODE','path':'relations','message':'context/node IDs required'})
 for item in value.get('decision_claims',[]):
  if item.get('relation') not in DECISION_RELATIONS:errors.append({'code':'DECISION_CLAIM','path':'relations','message':'invalid typed relation'})
 for item in value.get('evidence_pointers',[]):
  if item.get('kind') not in POINTER_KINDS:errors.append({'code':'EVIDENCE_POINTER','path':'relations','message':'invalid pointer kind'})
 return {'ok':not errors,'command':'validate-relations','errors':errors}

def deduplicate_evidence_pointers(items:list[dict[str,Any]])->list[dict[str,Any]]:
 """One reality_key counts once; representation count never raises evidence strength."""
 rank={'resolvable':0,'trace_only':1,'unavailable':2}; selected={}
 for item in items:
  key=item.get('reality_key') or item.get('id')
  if key not in selected or rank.get(item.get('kind'),9)<rank.get(selected[key].get('kind'),9):selected[key]=item
 return [selected[k] for k in sorted(selected)]

def partition_adapter_output(*,project_state,decisions,claims,authority_refs,evidence_pointers)->dict[str,Any]:
 return {'current_project_state':project_state,'governing_decisions':decisions,'domain_claims':claims,'authority_refs':authority_refs,'evidence_pointers':deduplicate_evidence_pointers(evidence_pointers)}
