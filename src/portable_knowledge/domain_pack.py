"""Fact-free Existing Project Domain Pack loader and candidate orchestration."""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any

PACK_IDS={"personal-brand-existing","software-existing"}
REQUIRED={"schema_version","id","version","project_kind","discovery_questions","candidate_facets","machine_truth_sources","memory_discovery_rules","evidence_kinds","claim_confirmation_rules","non_substitutable_evidence","risks","exclusions","representative_query_seeds","upgrade_policy"}
CONTAMINATION=(re.compile(r"(?i)genshin|dongzhi|ai brand lab"),re.compile(r"\b(?:W|P|M|E|X)-\d+\b"),re.compile(r"(?:^|[ /])~?/[^ ]+"))

class DomainPackError(Exception): pass

def load_pack(package_root: Path, pack_id: str) -> dict[str,Any]:
    if pack_id not in PACK_IDS: raise DomainPackError(f"unsupported pack: {pack_id}")
    return json.loads((package_root/'domain-packs'/f'{pack_id}.json').read_text(encoding='utf-8'))

def validate_pack(pack: dict[str,Any]) -> dict[str,Any]:
    errors=[]
    def fail(code,message): errors.append({"code":code,"path":f"domain-packs/{pack.get('id','unknown')}","message":message})
    if REQUIRED-set(pack): fail('PACK_SCHEMA',f'missing: {sorted(REQUIRED-set(pack))}')
    if pack.get('id') not in PACK_IDS: fail('PACK_ID','unsupported pack ID')
    if pack.get('upgrade_policy')!='never_rewrite_instance': fail('PACK_UPGRADE','pack upgrades must not rewrite instances')
    for key in ('discovery_questions','candidate_facets','machine_truth_sources','memory_discovery_rules','evidence_kinds','claim_confirmation_rules','non_substitutable_evidence','risks','exclusions','representative_query_seeds'):
        if not pack.get(key): fail('PACK_CONTENT',f'{key} must not be empty')
    serialized=json.dumps(pack,ensure_ascii=False)
    if '"claims"' in serialized: fail('PACK_CLAIM','pack must not preload claims')
    if any(pattern.search(serialized) for pattern in CONTAMINATION): fail('PACK_FACT_CONTAMINATION','project-specific fact or path detected')
    return {'ok':not errors,'command':'validate-domain-pack','errors':errors}

def propose_candidates(profile: dict[str,Any],pack: dict[str,Any])->list[dict[str,Any]]:
    validation=validate_pack(pack)
    if not validation['ok']: raise DomainPackError(str(validation['errors']))
    facets=pack['candidate_facets']
    modes=(("focused",facets[:3]),("balanced",facets[:5]),("traceable",facets[-3:]))
    candidates=[]
    for mode,selected in modes:
        nodes=[]
        for facet in selected:
            slug=facet['id']
            nodes.append({'id':slug,'topics':[{'id':f'{slug}-core','title':facet['title']}]})
        candidates.append({'schema_version':1,'candidate_id':f"{pack['id']}-{mode}",'authority':False,'production_task':profile['primary_production_task'],'nodes':nodes,'include':[x['title'] for x in selected],'exclude':pack['exclusions'],'memory_roles':profile['memory_role_candidates'],'files':[],'pack':{'id':pack['id'],'version':pack['version']}})
    return candidates
