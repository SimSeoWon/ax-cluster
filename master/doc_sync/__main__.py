"""운영 문서 최신화: plan(읽기), draft(LLM 수정안), apply(명시 승인)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import DocSyncError, read_text
from .registry import collect


def _summary(plan):
    return {"schema_version": plan["schema_version"], "root": plan["root"],
            "registry": plan["registry"], "head": plan["head"],
            "documents": [{key: doc[key] for key in
                           ("id", "path", "target", "role", "protected")}
                          for doc in plan["documents"]]}


def _save(path, artifact, plan):
    destination = Path(path).expanduser().absolute()
    root = Path(plan["root"])
    reserved = {Path(plan["registry"])}
    for doc in plan["documents"]:
        reserved.add(root / doc["target"])
        reserved.update(root / item["path"] for item in doc["evidence"])
    if destination.resolve() in reserved or destination.is_symlink():
        raise DocSyncError("수정안 출력은 등록목록·문서·근거 파일을 덮을 수 없다")
    try:
        with destination.open("x", encoding="utf-8") as stream:
            json.dump(artifact, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except OSError as exc:
        raise DocSyncError(f"수정안을 저장할 수 없다(기존 파일 덮기 금지): {destination}: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "draft", "apply"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, default=Path.cwd())
        command.add_argument("--registry", type=Path, default=Path("docs/document-registry.json"))
        if name != "apply":
            command.add_argument("--id", action="append", dest="ids")
        if name == "draft":
            command.add_argument("--project", required=True, help="사용량을 기록할 마운트된 프로젝트")
            command.add_argument("--out", type=Path, required=True)
            command.add_argument("--lane", choices=("codex",), default="codex")
            command.add_argument("--timeout", type=int, default=180)
        if name == "apply":
            command.add_argument("--artifact", type=Path, required=True)
            command.add_argument("--confirm", action="store_true")
            command.add_argument("--approve", action="append", dest="approved_ids")
            command.add_argument("--allow-protected", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve(strict=True)
        registry = args.registry.expanduser()
        if not registry.is_absolute():
            registry = root / registry
        if args.command == "apply":
            from .apply import apply_draft
            artifact = json.loads(read_text(args.artifact))
            result = apply_draft(root, registry, artifact, confirm=args.confirm,
                                 approved_ids=args.approved_ids,
                                 allow_protected=args.allow_protected)
        else:
            plan = collect(root, registry, ids=args.ids)
            if args.command == "plan":
                result = _summary(plan)
            else:
                from ..context_search.paths import resolve_mounted_only
                from .draft import generate
                paths = resolve_mounted_only(args.project)
                # 출력을 덮지 않을 수 있는지 비용이 드는 호출 전에 확인한다.
                if args.out.exists() or args.out.is_symlink() or not args.out.parent.is_dir():
                    raise DocSyncError("수정안 출력은 존재하지 않는 파일·존재하는 부모 디렉토리여야 한다")
                artifact = generate(plan, lane=args.lane, timeout=args.timeout,
                                    usage_log=paths.usage_log)
                _save(args.out, artifact, plan)
                result = {"ok": True, "artifact": str(args.out.absolute()),
                          "documents": [{"id": doc["id"], "decision": doc["decision"],
                                         "reason": doc["reason"], "diff": doc["diff"]}
                                        for doc in artifact["documents"]]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (DocSyncError, OSError, ValueError, TypeError) as exc:
        print(f"[doc-sync] 실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
