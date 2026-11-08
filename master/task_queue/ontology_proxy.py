"""#898 요청자 대행의 입력·결과 투영. 온톨로지 처리는 기존 코어 한 벌을 쓴다."""
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class ProjectReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str = ""


class CreateDomainReq(ProjectReq):
    name: str
    tags: list[str] = []
    parent: str = ""
    summary: str = ""


class ResolveTermsReq(ProjectReq):
    terms: list[str]


class ItemReq(ProjectReq):
    domain: str
    kind: Literal["objects", "actions", "invariants"]
    name: str


class EditItemReq(ItemReq):
    patch: dict


class RemoveItemReq(ItemReq):
    force: StrictBool = False


class LockItemReq(ItemReq):
    locked: StrictBool = True


class DomainReq(ProjectReq):
    domain: str = ""


class UnassignedReq(ProjectReq):
    sample: int = Field(default=20, ge=0)


class SyncReq(DomainReq):
    apply: StrictBool = False


class RequiredDomainReq(ProjectReq):
    domain: str


class EditDomainFieldReq(RequiredDomainReq):
    parent_domain: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    collaborates_with: list[str] | None = None
    summary: str | None = None


class RemoveLogTagReq(RequiredDomainReq):
    tag: str


class SetLogTagReq(RemoveLogTagReq):
    cvar: str
    related_invariants: list[str] | None = None


class RenameDomainReq(ProjectReq):
    old: str
    new: str
    apply: StrictBool = False


class RenameClassReq(RenameDomainReq):
    domain: str


def _component(value: str) -> None:
    """코어의 한글 이름 계약은 유지하고 경로 성분만 거부한다."""
    if not value or value in (".", "..") or any(c in value for c in ("/", "\\", "\0")):
        raise ValueError(f"단일 이름이어야 한다: {value!r}")


def _contained(base: Path, target: Path) -> None:
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError("프로젝트의 온톨로지 경계를 벗어난 경로다")


def _safe_tree(base: Path, target: Path) -> None:
    """도메인·하위 YAML의 심볼릭 링크로 다른 트윈에 쓰지 않는다."""
    _contained(base, target)
    if target.is_dir():
        for entry in target.rglob("*"):
            if entry.is_symlink():
                _contained(base, entry)


def process(paths, operation: str, req) -> dict:
    """인증·마운트 관문을 통과한 프로젝트 경로만 받는다. 쓰기는 캐시하지 않는다."""
    from ..ontology import create, edit, staging, sync, unassigned

    _contained(paths.root, paths.ontology)
    domains = paths.ontology / "domains"
    if operation == "resolve-terms":
        from ..context_search import thesaurus
        from ..context_search.search import ContextSearch
        try:
            searcher = ContextSearch(paths)
        except Exception:
            searcher = None                   # 색인이 없어도 기존 별칭은 조회한다
        r = thesaurus.resolve(paths, req.terms, searcher=searcher)
        return {"ok": True, "project": paths.name, "known": r.known,
                "expansion": r.expansion, "needs_user": r.needs_user,
                "unresolved": [{"term": u.term, "question": u.question,
                                "candidates": [{"class": c.class_name, "why": c.why,
                                                "file": c.file} for c in u.candidates]}
                               for u in r.unresolved], "summary": r.summary}
    if operation == "create-domain":
        # 코어가 정규화해 실제로 쓰는 이름으로 경계 검사와 호출을 함께 한다.
        # 공백을 포함한 원문만 검사하면 trim된 경로의 dangling symlink를 놓친다.
        name = create.validate_name(req.name)
        parent = create.validate_name(req.parent) if req.parent else ""
        _component(name)
        if parent:
            _component(parent)
        seed = paths.root / "context" / "_domains"
        _contained(paths.root, seed)
        _contained(seed, seed / f"{name}.md")
        if parent:
            _contained(seed, seed / f"{parent}.md")
            _safe_tree(paths.ontology, domains / parent)
            if staging.in_session(paths, parent):
                raise ValueError("상위 도메인 편집 세션이 있다 — commit/discard 후 생성할 것")
        r = create.create(paths, name, tags=req.tags, parent=parent, summary=req.summary)
        return {"ok": True, "domain": r.domain, "path": r.path, "parent": r.parent,
                "linked": r.linked, "notes": r.notes,
                "next": "그 MD 의 절(특히 `## 도메인 경계`)을 채운 뒤 "
                        "`python -m master.ontology refresh` 로 합성한다"}

    if operation in ("rename-domain", "rename-class"):
        from ..ontology import rename
        _component(req.old)
        # 실제 코어가 사용하는 새 이름을 검사한다. 계획의 경로는 클라이언트가 주입하지 못한다.
        _component(rename.safe_name(req.new))
        _safe_tree(paths.ontology, domains)
        _safe_tree(paths.root, paths.context / "_domains")
        if staging.status(paths).get("sessions"):
            raise ValueError("편집 세션이 있다 — commit/discard 후 개명할 것")
        if operation == "rename-class":
            _component(req.domain)
            plan = rename.plan_class(paths, req.domain, req.old, req.new)
        else:
            plan = rename.plan_domain(paths, req.old, req.new)
        for source, destination in plan.moves:
            _safe_tree(paths.root, Path(source))
            _safe_tree(paths.root, Path(destination))
            if Path(destination).exists():
                raise ValueError("개명 대상이 이미 있다 — 덮어쓰지 않는다")
        for target, _ in plan.edits:
            _contained(paths.root, Path(target))
        if req.apply and plan.ok:
            plan = (rename.apply_class(paths, plan) if operation == "rename-class"
                    else rename.apply_domain(paths, plan))
        return {"ok": plan.ok, **asdict(plan), "summary": plan.summary()}

    domain = getattr(req, "domain", "").strip()
    if domain:
        _component(domain)
    elif operation not in ("list-locked", "unassigned-classes", "sync", "staging-status"):
        raise ValueError("도메인명이 비었다")
    if hasattr(req, "name"):
        _component(req.name)
    _safe_tree(paths.ontology, domains / domain if domain else domains)
    if operation == "edit-domain-field":
        from ..ontology.edit_field import edit_domain_field
        if staging.in_session(paths, domain):
            raise ValueError("편집 세션 중 도메인 필드는 바꾸지 않는다 — commit/discard 후 실행할 것")
        seed = paths.context / "_domains"
        _contained(paths.root, seed)
        _contained(seed, seed / f"{domain}.md")
        if req.parent_domain and req.parent_domain.strip():
            _component(create.validate_name(req.parent_domain))
        return edit_domain_field(paths, domain, parent_domain=req.parent_domain,
                                 status=req.status, tags=req.tags,
                                 collaborates_with=req.collaborates_with, summary=req.summary)
    if operation in ("list-log-tags", "set-log-tag", "remove-log-tag"):
        from ..ontology import log_tags
        if operation == "list-log-tags":
            return log_tags.list_impl(paths, domain)
        if staging.in_session(paths, domain):
            raise ValueError("편집 세션 중 로그 태그는 바꾸지 않는다 — commit/discard 후 실행할 것")
        if operation == "set-log-tag":
            return log_tags.set_impl(paths, domain, req.tag, req.cvar,
                                     related_invariants=req.related_invariants)
        return log_tags.remove_impl(paths, domain, req.tag)
    if operation.startswith("staging-"):
        _safe_tree(paths.ontology, domains)
        if operation == "staging-begin":
            return staging.begin(paths, domain)
        if operation == "staging-commit":
            return staging.commit(paths, domain, sync=staging.default_sync)
        if operation == "staging-discard":
            return staging.discard(paths, domain)
        if operation == "staging-status":
            return staging.status(paths, domain)
    if operation in ("edit-item", "remove-item", "lock-item"):
        # 기존 코어의 domain 인자로 실제 working package를 전달한다.
        # 경로 선택만 대행하고 편집·잠금·manifest 갱신은 같은 코어 한 벌이 처리한다.
        _safe_tree(paths.ontology, domains)
        working = staging.working_pkg(paths, domain)
        target_domain = str(working.relative_to(domains.resolve()))
        in_staging = working != staging.pkg_path(paths, domain)
    if operation == "edit-item":
        r = edit.edit(paths, target_domain, req.kind, req.name, req.patch)
        return {"ok": True, "summary": r.summary, "changed": r.changed,
                "ignored": r.ignored, "locked": r.locked,
                "domain": domain, "staging": in_staging,
                "note": " 이 항목은 이제 재합성이 덮지 않는다"}
    if operation == "remove-item":
        r = edit.remove(paths, target_domain, req.kind, req.name, force=req.force)
        return {"ok": r.removed, "summary": r.summary, "was_locked": r.was_locked,
                "reason": r.reason, "domain": domain, "staging": in_staging}
    if operation == "lock-item":
        r = edit.set_lock(paths, target_domain, req.kind, req.name, req.locked)
        return {"ok": True, "summary": r.summary, "locked": r.locked, "note": r.note,
                "domain": domain, "staging": in_staging}
    if operation == "list-locked":
        _safe_tree(paths.ontology, domains)
        rows = []
        names = ([domain] if domain else sorted(
            d.name for d in domains.iterdir() if d.is_dir()
            and not d.name.endswith((staging.STAGING_SUFFIX, staging.BACKUP_SUFFIX)))) if domains.is_dir() else []
        for name in names:
            working = staging.working_pkg(paths, name)
            target = str(working.relative_to(domains.resolve()))
            for row in edit.locked_items(paths, target):
                rows.append({**row, "domain": name,
                             "staging": working != staging.pkg_path(paths, name)})
        return {"ok": True, "count": len(rows), "items": rows}
    if operation == "unassigned-classes":
        rep = unassigned.scan(paths, sample=req.sample)
        return {"ok": True, "summary": rep.summary, "total_classes": rep.total_classes,
                "assigned": rep.assigned,
                "adjacent": [{"name": a.name, "domain": a.domain, "why": a.why, "via": a.via}
                             for a in rep.adjacent[:req.sample]],
                "adjacent_total": len(rep.adjacent),
                "isolated_sample": [{"name": n, "methods": m} for n, m in rep.isolated],
                "isolated_total": rep.isolated_total, "notes": rep.notes}
    if operation == "sync":
        if req.apply and staging.status(paths, domain).get("sessions"):
            raise ValueError("편집 세션 중 sync 반영은 하지 않는다 — commit/discard 후 실행할 것")
        stats = ([sync.sync_domain(paths, domain, apply=req.apply)] if domain
                 else sync.sync_all(paths, apply=req.apply))
        return {"ok": True, "applied": req.apply,
                "domains": [{"domain": s.domain, "summary": s.summary,
                             "path_fixed": s.path_fixed[:10], "missing": s.missing[:10],
                             "declared": len(s.declared_set)} for s in stats],
                "note": "" if req.apply else "[중요] 아무것도 쓰지 않았다. 반영하려면 apply=true"}
    raise ValueError(f"알 수 없는 온톨로지 동작: {operation}")
