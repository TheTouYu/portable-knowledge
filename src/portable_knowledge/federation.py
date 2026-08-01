"""Explicit, read-only search across registered PKC projects."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .instance import InstanceError, load_instance, validate_project_memory

PERMISSIONS = {"restricted", "internal", "public_redacted", "public"}


class FederationError(Exception):
    def __init__(self, message: str, *, code: str = "FEDERATION_REGISTRY", path: str = ".") -> None:
        self.code = code
        self.path = path
        super().__init__(message)


def load_registry(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FederationError(f"invalid federation registry {path}: {exc}", path=str(path)) from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("projects"), list):
        raise FederationError("federation registry needs schema_version 1 and a projects array", path=str(path))
    projects: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value["projects"]):
        item_path = f"projects[{index}]"
        if not isinstance(item, dict):
            raise FederationError("project entry must be an object", path=item_path)
        project_id, root = item.get("id"), item.get("root")
        permission = item.get("read_permission")
        if not isinstance(project_id, str) or not project_id or not isinstance(root, str) or not root:
            raise FederationError("project id and root are required", path=item_path)
        if project_id in projects:
            raise FederationError(f"duplicate project id: {project_id}", path=item_path)
        if permission not in PERMISSIONS:
            raise FederationError(f"invalid read_permission for {project_id}", path=item_path)
        projects[project_id] = item
    return {**value, "projects_by_id": projects}


def search(registry_path: Path, selected: list[str], query: str, limit: int,
           search_project: Callable[[Path, Any, str, str, int], dict[str, Any]]) -> dict[str, Any]:
    registry_path = registry_path.resolve()
    registry = load_registry(registry_path)
    selected = list(dict.fromkeys(selected))
    if not selected:
        raise FederationError("select at least one project with --project", code="FEDERATION_SCOPE")
    unknown = [project_id for project_id in selected if project_id not in registry["projects_by_id"]]
    if unknown:
        raise FederationError("projects are not registered: " + ", ".join(unknown), code="FEDERATION_PROJECT_UNKNOWN")
    projects = []
    for project_id in selected:
        configured = registry["projects_by_id"][project_id]
        root_value = Path(configured["root"])
        root = (root_value if root_value.is_absolute() else registry_path.parent / root_value).resolve()
        config_value = Path(configured.get("config", "project-intelligence.json"))
        config = (config_value if config_value.is_absolute() else root / config_value).resolve()
        project = {"project_id": project_id, "root": str(root), "read_permission": configured["read_permission"],
                   "evidence_boundary": configured.get("evidence_boundary", "Only this project's configured PKC knowledge is searched."),
                   "status": "available", "results": [], "warnings": [], "errors": []}
        try:
            if not config.is_relative_to(root):
                raise FederationError("target config must stay inside its project root", code="FEDERATION_PROJECT_CONFIG", path=str(config))
            instance = load_instance(root, config)
            if instance.identity.get("id") != project_id:
                raise FederationError(f"registered id {project_id} does not match target instance id {instance.identity.get('id')}",
                                      code="FEDERATION_PROJECT_ID", path=str(config))
            memory = validate_project_memory(instance)
            if not memory["ok"]:
                raise FederationError("target project configuration is invalid", code="FEDERATION_PROJECT_INVALID", path=str(config))
            result = search_project(root, instance, query, configured["read_permission"], limit)
            project.update(results=result.get("results", []), warnings=result.get("warnings", []), mode=result.get("mode", "lexical"))
        except (FederationError, InstanceError, OSError) as exc:
            project["status"] = "unavailable"
            project["errors"] = [{"code": getattr(exc, "code", "FEDERATION_PROJECT_UNAVAILABLE"),
                                  "path": getattr(exc, "path", str(root)), "message": str(exc)}]
        projects.append(project)
    available = sum(item["status"] == "available" for item in projects)
    status = "complete" if available == len(projects) else ("partial" if available else "unavailable")
    return {"ok": available > 0, "command": "federation-search", "read_only": True, "cross_project_writes": False,
            "registry": str(registry_path), "query": query, "status": status, "projects": projects,
            "errors": [] if available else [error for project in projects for error in project["errors"]],
            "exit_code": 0 if available else 2}
