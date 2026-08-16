"""상태 익스포트/임포트 (소 2.4.3).

원본: `AgentTest/mcp/context_search/state_transfer.py` — 형식과 규칙을 그대로 받는다.

## 무엇을 옮기나 — **재생성 비용이 큰 것만**

    context/            컨텍스트 MD    LLM 합성물. 재실행하면 문구가 달라진다(비결정적)
    ontology_domains/   온톨로지 YAML  같은 이유. 우리 실측으로는 재합성이 **더 얕았다**(§20)

벡터·BM25·class_graph 는 **로컬 연산만으로 재생성 가능한 파생 자산**이라 넣지 않는다 —
원본이 같은 판단을 했고(`docs/data-schema.md` §0), 우리도 `rebuild` 한 번이면 된다.

## [중요] 우리 트리는 받은 스냅샷과 갈라져 있다

    zip 에만 있는 필드   없음
    [중요] 우리에만          protected · protected_at · protected_reason      (우리가 만든 것)
    형식 밖 자산         `_thesaurus.tsv`                                 (별칭 폴백 저장소)

[주의] `aliases` 는 **원본의 필드다** — 시소러스의 원천이 *"objects yaml 의 `aliases`"* 라고 원본이
적어 뒀다. 받은 zip 에 없던 것은 그때 등록분이 0이었기 때문이지 형식에 없어서가 아니다.
**그래서 호환본에서도 `aliases` 는 뺀다고 착각하면 안 된다.**

## 두 벌을 낸다 (사용자 결정 2026-08-10)

    compat   받은 zip 과 **같은 모양** + 우리 필드 제거 → 원본 시스템이 읽을 수 있다
    full     우리 필드·`_thesaurus.tsv` 까지 → **우리를 복원**할 수 있다

둘 다 `README.md` 를 동봉한다 — 어느 것이 무엇이고 임포트가 무엇을 지켜야 하는지.

## [중요] 임포트는 덮어쓰기가 아니라 **병합**이어야 한다

원본의 `force` 는 *백업 후 통째 교체* 다. 그대로 하면 **보호 표식 240건과 별칭이 사라진다.**
재합성 경계에서 이미 같은 문제를 풀었으므로(`package.carry_human_fields`) 같은 방식을 쓴다 —
들어온 파일을 쓰되 **우리 필드를 이월**한다. 그리고 계획을 먼저 보여준다.
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .context_search.paths import ProjectPaths
from .ontology import yaml_io

MANIFEST_NAME = "_export_manifest.json"
CONTEXT_DIR = "context"
DOMAINS_DIR = "ontology_domains"
SIDE_FILE = "_thesaurus.tsv"
README_NAME = "README.md"

# [중요] 우리가 만든 필드. 호환본에서 뺀다 — 원본이 모르는 키다.
AX_FIELDS = ("protected", "protected_at", "protected_reason")
# [중요] 임포트가 **이월해야** 하는 필드. `aliases` 는 원본 것이지만 우리 등록분을 잃으면 안 된다.
CARRY_FIELDS = AX_FIELDS + ("aliases",)

# 윈도우 절대경로 — 다른 기계에서 깨진다. 원본이 같은 검사를 한다(비차단 경고).
_ABS_PATH = re.compile(r"[A-Za-z]:\\")


@dataclass
class ExportResult:
    path: Path
    variant: str
    context_files: int = 0
    domains: int = 0
    yaml_files: int = 0
    stripped: int = 0                                  # 호환본에서 지운 필드 수
    abs_path_warnings: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = (f"{self.variant}: {self.path.name} · context {self.context_files} · "
             f"도메인 {self.domains} · yaml {self.yaml_files}")
        if self.stripped:
            s += f" · 우리 필드 제거 {self.stripped}"
        if self.abs_path_warnings:
            s += f" · [주의] 절대경로 {len(self.abs_path_warnings)}건"
        return s


def _scan_abs_paths(base: Path) -> list:
    """윈도우 절대경로가 섞였는지. **차단하지 않고 경고만** — 원본과 같은 판단."""
    out = []
    if not base.is_dir():
        return out
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _ABS_PATH.search(line):
                out.append(f"{f.name}:{i}")
                break
    return out


def _readme(variant: str, res: ExportResult, project: str) -> str:
    other = "full" if variant == "compat" else "compat"
    head = ("**원본 시스템 호환본**" if variant == "compat"
            else "**우리 복원본** (AX 클러스터)")
    body = [
        f"# {project} 상태 전송 — {variant}",
        "",
        f"{head} · 생성 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 무엇이 들어 있나",
        "",
        "```",
        f"{MANIFEST_NAME}          형식 기술서 (항목 수·버전)",
        f"{CONTEXT_DIR}/                 컨텍스트 MD  {res.context_files}개",
        f"{DOMAINS_DIR}/        온톨로지 YAML  도메인 {res.domains} · 파일 {res.yaml_files}",
    ]
    if variant == "full":
        body.append(f"{SIDE_FILE}          별칭 폴백 저장소 (온톨로지 yaml 이 없는 클래스용)")
    body += ["```", "",
             "[중요] **벡터·BM25·class_graph 는 들어 있지 않다.** 로컬 연산만으로 다시 만들 수 있는",
             "파생 자산이라 넣지 않는다 — 임포트 뒤 재색인 한 번이면 된다.", ""]

    if variant == "compat":
        body += [
            "## [중요] 이 사본에서 뺀 것",
            "",
            f"`{'` · `'.join(AX_FIELDS)}` — **AX 클러스터가 만든 필드**라 원본 시스템이 모른다.",
            f"이 {res.stripped}개를 지웠다. 그래서 **이 zip 으로는 AX 쪽을 온전히 복원할 수 없다** —",
            f"그 용도로는 `{other}` 사본을 쓸 것.", "",
            "[주의] `aliases` 는 **빼지 않았다.** 그건 원본의 필드다(시소러스의 원천).", "",
        ]
    else:
        body += [
            "## [중요] 임포트할 때 지켜야 할 것",
            "",
            "이 사본에는 AX 가 얹은 것이 들어 있다:",
            "",
            f"- `protected` / `protected_at` / `protected_reason` — *재생성으로 대체하지 않는다* 는 표식.",
            "  **검수 잠금(`verified_by_user`)과 다른 것**이다. 전자는 출처가 근거고 일괄로 걸며,",
            "  후자는 사람이 항목을 검수했다는 뜻이다. 섞으면 둘 다 못 쓴다.",
            "- `aliases` — 한글 검색을 살리는 별칭. 색인의 tags 채널(가중치 3.0)로 올라간다.",
            "",
            "[중요] **새 스냅샷을 받을 때 통째로 덮으면 이것들이 사라진다.** 임포트는 파일을 쓰되",
            "위 필드를 **이월**해야 한다 — 재합성 경계에서 같은 문제를 이미 겪었다.",
            "",
        ]
    body += [
        "## 되돌리기",
        "",
        "[중요] `ModularStage/` 는 **git 밖**이다(gitignore). 임포트 전에 반드시 백업할 것 —",
        "임포트 도구는 자동으로 백업하지만, 그 경로를 확인하고 나서 진행하라.",
        "",
        "## 명령",
        "",
        "```bash",
        "python -m master.transfer export            # 두 벌 + README",
        "python -m master.transfer import <zip>      # [중요] 계획만 (아무것도 안 쓴다)",
        "python -m master.transfer import <zip> --apply",
        "python -m master.context_search.rebuild     # 임포트 뒤 재색인",
        "```",
    ]
    if res.abs_path_warnings:
        body += ["", "## [주의] 절대경로가 섞였다",
                 "", "다른 기계에서 깨진다. 차단하지는 않았다:", "",
                 "```", *res.abs_path_warnings[:10], "```"]
    return "\n".join(body) + "\n"


def export(paths: ProjectPaths, out_dir=None, *, variant: str = "full") -> ExportResult:
    """상태를 zip 한 벌로 낸다. `variant` 는 `full` 또는 `compat`."""
    if variant not in ("full", "compat"):
        raise ValueError(f"variant 는 full|compat: {variant!r}")
    ctx = paths.root / "context"
    dom = paths.ontology / "domains"
    if not dom.is_dir():
        raise RuntimeError(f"온톨로지가 없다: {dom}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(out_dir) if out_dir else (paths.root.parent / "ax-exports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{paths.name}_state_{stamp}_{variant}.zip"

    res = ExportResult(path=out, variant=variant)
    res.abs_path_warnings = _scan_abs_paths(ctx) + _scan_abs_paths(dom)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(ctx.rglob("*")) if ctx.is_dir() else []:
            if f.is_file():
                zf.write(f, f"{CONTEXT_DIR}/{f.relative_to(ctx).as_posix()}")
                res.context_files += 1
        for f in sorted(dom.rglob("*")):
            if not f.is_file():
                continue
            rel = f"{DOMAINS_DIR}/{f.relative_to(dom).as_posix()}"
            if f.suffix == ".yaml":
                res.yaml_files += 1
                data = yaml_io.read(f)
                if variant == "compat" and isinstance(data, dict):
                    hit = [k for k in AX_FIELDS if k in data]
                    if hit:
                        res.stripped += len(hit)
                        data = {k: v for k, v in data.items() if k not in AX_FIELDS}
                        zf.writestr(rel, yaml_io.dump(data))
                        continue
                zf.write(f, rel)
            else:
                zf.write(f, rel)
        res.domains = sum(1 for d in dom.iterdir() if d.is_dir())

        side = paths.ontology / SIDE_FILE
        if variant == "full" and side.is_file():
            zf.write(side, SIDE_FILE)

        manifest = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_version": "ax-cluster",
            "items": [CONTEXT_DIR, DOMAINS_DIR],
            "context_file_count": res.context_files,
            "domain_count": res.domains,
        }
        if variant == "full":
            # [중요] 호환본의 manifest 는 **원본과 같은 모양**으로 둔다 — 여분 키가 그쪽 파서를
            #    건드릴 이유가 없다. 우리 것에만 표시한다.
            manifest["variant"] = "full"
            manifest["ax_fields"] = list(AX_FIELDS)
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr(README_NAME, _readme(variant, res, paths.name))
    return res


def export_both(paths: ProjectPaths, out_dir=None) -> list:
    """두 벌 다. [중요] **compat 만 받아 가면 AX 상태를 못 되살린다** — README 에 적어 둔다."""
    return [export(paths, out_dir, variant=v) for v in ("full", "compat")]


# ── 임포트 ───────────────────────────────────────────────────────────────────

@dataclass
class ImportPlan:
    zip_path: Path
    variant: str = ""
    context_in: int = 0
    yaml_in: int = 0
    domains_in: int = 0
    carried: list = field(default_factory=list)     # [(항목경로, [이월한 필드])]
    new_files: int = 0
    replaced: int = 0
    removed_here: list = field(default_factory=list)  # 우리엔 있고 zip 엔 없다
    applied: bool = False
    backup: str = ""
    notes: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        head = "적용" if self.applied else "계획"
        s = (f"{head}: zip({self.variant or '?'}) context {self.context_in} · "
             f"yaml {self.yaml_in} · 도메인 {self.domains_in} · "
             f"새 파일 {self.new_files} · 교체 {self.replaced}")
        if self.carried:
            s += f" ·  필드 이월 {len(self.carried)}"
        if self.removed_here:
            s += f" · [주의] zip 에 없는 우리 항목 {len(self.removed_here)}(남겨 둔다)"
        if self.backup:
            s += f" · 백업 {self.backup}"
        return s


def _our_fields(item) -> dict:
    return {k: item[k] for k in CARRY_FIELDS if isinstance(item, dict) and item.get(k)}


def import_(paths: ProjectPaths, zip_path, *, apply: bool = False,
            backup_dir=None) -> ImportPlan:
    """zip 을 우리 트리에 들인다. [중요] **기본은 계획만.**

    [중요] **통째로 덮지 않는다.** 들어온 파일을 쓰되 우리 필드(`protected*`·`aliases`)를
    **이월**한다 — 원본의 `force` 는 백업 후 통째 교체라 그대로 하면 보호 표식 240건과
    별칭이 사라진다. 재합성 경계에서 이미 같은 문제를 풀었다(`package.carry_human_fields`).

    [중요] **zip 에 없는 우리 항목은 지우지 않는다.** 상대가 안 보낸 것인지 지운 것인지 여기선
    모른다 — `sync` 가 사라진 클래스를 대하는 것과 같은 규칙이다. 세어서 보고만 한다.
    """
    zp = Path(zip_path)
    plan = ImportPlan(zip_path=zp)
    if not zp.is_file():
        raise RuntimeError(f"zip 이 없다: {zp}")

    dom_root = paths.ontology / "domains"
    ctx_root = paths.root / "context"

    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
        try:
            man = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            plan.variant = str(man.get("variant") or "compat")
            plan.domains_in = int(man.get("domain_count") or 0)
        except (KeyError, ValueError):
            plan.notes.append(f"[중요] {MANIFEST_NAME} 을 읽지 못했다 — 형식이 다를 수 있다")

        incoming_yaml = {}
        for n in names:
            if n.startswith(f"{CONTEXT_DIR}/") and not n.endswith("/"):
                plan.context_in += 1
            elif n.startswith(f"{DOMAINS_DIR}/") and n.endswith(".yaml"):
                plan.yaml_in += 1
                incoming_yaml[n[len(DOMAINS_DIR) + 1:]] = n

        for rel, member in sorted(incoming_yaml.items()):
            here = dom_root / rel
            if not here.is_file():
                plan.new_files += 1
                continue
            plan.replaced += 1
            keep = _our_fields(yaml_io.read(here))
            if keep:
                plan.carried.append((rel, sorted(keep)))

        ours = {str(f.relative_to(dom_root)).replace("\\", "/")
                for f in dom_root.rglob("*.yaml")} if dom_root.is_dir() else set()
        plan.removed_here = sorted(ours - set(incoming_yaml))

        if not apply:
            return plan

        # [중요] `ModularStage/` 는 git 밖이다 — 쓰기 전에 반드시 백업한다
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bdir = Path(backup_dir or Path.home() / "ax-backups") / f"import-{stamp}"
        bdir.mkdir(parents=True, exist_ok=True)
        if dom_root.is_dir():
            shutil.copytree(dom_root, bdir / "domains")
        plan.backup = str(bdir)

        for rel, member in sorted(incoming_yaml.items()):
            here = dom_root / rel
            keep = _our_fields(yaml_io.read(here)) if here.is_file() else {}
            data = yaml_io.load(zf.read(member).decode("utf-8", "replace"))
            if isinstance(data, dict) and keep:
                for k, v in keep.items():
                    data.setdefault(k, v)          # [중요] 들어온 값이 있으면 그쪽을 존중한다
            here.parent.mkdir(parents=True, exist_ok=True)
            yaml_io.write(here, data)

        for n in names:
            if n.startswith(f"{CONTEXT_DIR}/") and not n.endswith("/"):
                t = ctx_root / n[len(CONTEXT_DIR) + 1:]
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_bytes(zf.read(n))
        # [중요] 형식 밖 자산은 zip 에 있을 때만 덮는다 — 없다고 지우지 않는다
        if SIDE_FILE in names:
            (paths.ontology / SIDE_FILE).write_bytes(zf.read(SIDE_FILE))

        plan.applied = True
        plan.notes.append("[중요] 임포트 뒤 재색인이 필요하다: python -m master.context_search.rebuild")
    return plan


# ── CLI ──────────────────────────────────────────────────────────────────────
#
#   python -m master.transfer export [출력디렉토리]     두 벌(full·compat) + README
#   python -m master.transfer import <zip> [--apply]    [중요] 기본은 계획만
#
# [중요] `ModularStage/` 는 git 밖이라 임포트가 되돌릴 수 없다 — `--apply` 는 **먼저 백업**한다.

def main(argv) -> int:
    from .context_search.paths import resolve
    cmd = (argv[0] if argv else "").strip()
    if cmd not in ("export", "import"):
        # [중요] 사용법은 프로젝트 해석보다 **먼저** 답한다 — 인자 없이 부른 사람에게
        #    `AX_PROJECTS_ROOT` 역추적을 던지면 CLI 가 고장 난 줄 안다.
        print(__doc__.split("## ")[0])
        print("  export [출력디렉토리]        두 벌(full·compat) + README")
        print("  import <zip> [--apply]      [중요] 기본은 계획만")
        return 2
    try:
        paths = resolve("")
    except Exception as e:                                # noqa: BLE001
        print(f"  [중요] 프로젝트를 못 잡았다 — {e}")
        return 1
    if cmd == "export":
        rest = [a for a in argv[1:] if not a.startswith("-")]
        for r in export_both(paths, rest[0] if rest else None):
            print("  " + r.summary)
            print(f"      {r.path}")
        print("\n  [중요] compat 으로는 AX 상태를 복원할 수 없다 — 그 용도는 full 이다.")
        return 0
    if cmd == "import":
        rest = [a for a in argv[1:] if not a.startswith("-")]
        if not rest:
            print("  import <zip> [--apply]")
            return 2
        try:
            plan = import_(paths, rest[0], apply="--apply" in argv)
        except RuntimeError as e:
            print(f"  [중요] {e}")
            return 1
        print("  " + plan.summary)
        for rel, fields in plan.carried[:8]:
            print(f"       이월 {rel} — {', '.join(fields)}")
        if len(plan.carried) > 8:
            print(f"      … 외 {len(plan.carried) - 8}건")
        for n in plan.removed_here[:5]:
            print(f"      [주의] zip 에 없다(남겨 둠): {n}")
        for n in plan.notes:
            print(f"      {n}")
        if not plan.applied:
            print("\n  [중요] 아무것도 쓰지 않았다. 반영하려면 `--apply`.")
        return 0
    return 2


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main(_sys.argv[1:]))
