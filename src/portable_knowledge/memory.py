"""Bounded Project Memory router and targeted Decision interface."""
from __future__ import annotations
import fnmatch
from typing import Any
STARTUP_STATES={'active','paused'}

def _scope(context:dict[str,Any],task_path:str|None,workspace:str|None,branch:str|None)->bool:
 scope=context.get('applies_to',{})
 if task_path and scope.get('paths') and not any(fnmatch.fnmatch(task_path,p) for p in scope['paths']): return False
 if workspace and scope.get('workspaces') and workspace not in scope['workspaces']: return False
 if branch and scope.get('branches') and not any(fnmatch.fnmatch(branch,p) for p in scope['branches']): return False
 return True

def select_primary_context(contexts:list[dict[str,Any]],*,user_context:str|None=None,task_path:str|None=None,workspace:str|None=None,branch:str|None=None)->dict[str,Any]:
 eligible=[c for c in contexts if c.get('lifecycle') in STARTUP_STATES]
 if user_context:
  found=[c for c in contexts if c.get('id')==user_context]
  if not found:return {'status':'missing','context':None,'reason':'user-specified context not found'}
  if not _scope(found[0],task_path,workspace,branch):return {'status':'scope_mismatch','context':found[0],'reason':'explicit context does not apply'}
  return {'status':'selected','context':found[0],'reason':'user_specified'}
 def unique(items,reason):
  return {'status':'selected','context':items[0],'reason':reason} if len(items)==1 else ({'status':'ambiguous','context':None,'candidates':[x['id'] for x in items],'reason':reason} if len(items)>1 else None)
 if task_path:
  result=unique([c for c in eligible if _scope(c,task_path,None,None)],'path_scope')
  if result:return result
 if workspace or branch:
  result=unique([c for c in eligible if _scope(c,None,workspace,branch)],'workspace_branch')
  if result:return result
 priorities=[c for c in eligible if c.get('priority')==1]
 result=unique(priorities,'global_unique_priority')
 return result or {'status':'ambiguous','context':None,'candidates':[x['id'] for x in eligible],'reason':'no unique primary; do not guess'}

def startup_memory(contexts:list[dict[str,Any]],primary:dict[str,Any],max_contexts:int=8)->dict[str,Any]:
 active=[c for c in contexts if c.get('lifecycle') in STARTUP_STATES]
 invalid=[c['id'] for c in active if c.get('lifecycle')=='active' and not c.get('current_recovery')]
 if invalid:return {'status':'invalid','errors':[{'code':'ACTIVE_RECOVERY_MISSING','context_id':x} for x in invalid]}
 if primary not in active:return {'status':'scope_mismatch','router':{'contexts':[]},'primary':None}
 summaries=[{k:c.get(k) for k in ('id','lifecycle','goal','priority')} for c in sorted(active,key=lambda x:(x.get('priority',999),x['id']))[:max_contexts]]
 return {'status':'ok','router':{'contexts':summaries,'truncated':len(active)>max_contexts},'primary':primary}

def lookup_decisions(decisions:list[dict[str,Any]],*,decision_id:str|None=None,keyword:str|None=None)->list[dict[str,Any]]:
 if decision_id:return [d for d in decisions if d.get('id')==decision_id]
 if not keyword:return []
 term=keyword.casefold()
 return [d for d in decisions if term in d.get('title','').casefold() or any(term in str(x).casefold() for x in d.get('keywords',[]))]
