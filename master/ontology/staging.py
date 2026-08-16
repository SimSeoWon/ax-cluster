"""온톨로지 스테이징 편집 세션 — 원전 η.9 이식 (소 3.1.7 · `#190`, 2026-08-15).

    begin(paths, domain)     `<pkg>.staging` 사본 생성 (멱등 — 이미 있으면 resume)
    working_pkg(paths, dom)   편집 대상 — 세션이 있으면 staging, 없으면 라이브
    commit(paths, domain)     [중요] rename swap + 색인 **1회** 재빌드
    discard(paths, domain)    staging 통째 폐기 — 라이브 무영향

## [중요] 이것은 `DoubleBufferedIndex` 패턴의 파일시스템 버전이다 (원전 표현 그대로)

우리 벡터 색인이 이미 같은 것을 한다 — `context_search/generation.py` 의 A/B 세대. 편집 중에는
라이브를 건드리지 않고, **커밋 시점에 원자적으로 교체**하고 그때 **한 번만** 재색인한다.

    편집 중  staging 사본만 바뀐다 → 라이브를 읽는 검색·조회는 **영향이 없다**
    커밋     pkg → `<pkg>.bak` · staging → pkg (rename) → 색인 1회
    폐기     staging 삭제 — 라이브는 처음부터 안 건드렸으니 되돌릴 것이 없다

## [중요] 원전 판단 넷을 그대로 옮긴다 — 전부 「과설계 방지」다

**① 세션을 강제하지 않는다.** `working_pkg` 는 세션이 있으면 staging, 없으면 라이브를 준다 —
*"세션 없이도 즉석 단건 편집은 그대로 동작(과설계 방지 — 매번 세션 강제 안 함)"*.

**② 세션 메타는 staging **밖**의 형제 파일이다.** `<pkg>.staging.meta`. [중요] 안에 두면
`staging → pkg` rename 때 **그대로 pkg 안에 끼어들어가 오염된다.** 원전이 그 자리를 명시해 뒀다.

**③ 라이브가 세션 중 바뀌어도 하드 블로킹하지 않는다.** `live_changed_during_session=True` 로
**알리기만** 한다. 원전 근거: *"온톨로지 편집은 저빈도 이벤트라 새 락/머지 인프라 없이 로그
가시성으로 충분하다고 판단, 과설계 방지"*. [주의] 막고 싶어지지만, 막으면 락·머지가 따라온다.

**④ 백업은 1세대만.** `<pkg>.bak` 를 덮어쓴다 — *"무한 누적 방지"*.

## [주의] 여기서 `mtime` 을 쓰는 것은 괜찮다 — σ.9.0 과 다르다

오늘 σ.9.0 이식에서 **`mtime` 이 우리 환경에서 무의미**했다(갓 클론한 미러라 소스 400개가 전부
같은 날짜). [중요] **여기는 다르다**: 비교 대상이 `domain.yaml` — **우리 도구가 직접 쓰는 파일**이고
git checkout 이 아니다. 신호원이 실제로 그 값을 움직인다. **같은 도구라도 어디에 쓰는지가
판정을 바꾼다.**
"""
from __future__ import annotations

import shutil
from pathlib import Path

STAGING_SUFFIX = ".staging"
META_SUFFIX = ".staging.meta"
BACKUP_SUFFIX = ".bak"
MANIFEST = "domain.yaml"


class StagingError(RuntimeError):
    """세션을 다룰 수 없다. [중요] **모르는 채로 교체하지 않는다.**"""


def pkg_path(paths, domain: str) -> Path:
    """도메인 패키지. [중요] 이름을 검증한다 — 경로 탈출은 여기서 막는다."""
    d = (domain or "").strip()
    if not d or "/" in d or "\\" in d or d.startswith(".") or ".." in d:
        raise StagingError(f"쓸 수 없는 도메인 이름이다: {domain!r}")
    root = (Path(paths.ontology) / "domains").resolve()
    p = (root / d).resolve()
    if not str(p).startswith(str(root) + "/"):
        raise StagingError(f"도메인 디렉토리 밖을 가리킨다: {domain!r}")
    return p


def staging_paths(pkg: Path) -> tuple:
    """`(staging, meta)`. [중요] **메타는 staging 밖의 형제**다 (머리말 ②)."""
    return pkg.with_name(pkg.name + STAGING_SUFFIX), pkg.with_name(pkg.name + META_SUFFIX)


def working_pkg(paths, domain: str) -> Path:
    """편집 대상 — 세션이 있으면 staging, 없으면 라이브. [중요] **세션을 강제하지 않는다.**"""
    pkg = pkg_path(paths, domain)
    staging, _ = staging_paths(pkg)
    return staging if staging.is_dir() else pkg


def in_session(paths, domain: str) -> bool:
    staging, _ = staging_paths(pkg_path(paths, domain))
    return staging.is_dir()


def _manifest_mtime(pkg: Path) -> float:
    m = pkg / MANIFEST
    try:
        return m.stat().st_mtime if m.exists() else 0.0
    except OSError:
        return 0.0


def begin(paths, domain: str) -> dict:
    """staging 사본 생성. **멱등** — 이미 있으면 `resumed`.

    라이브 manifest 의 mtime 을 메타에 적어 둔다 → commit 때 *"세션 중 라이브가 바뀌었나"* 를
    본다(백그라운드 재합성 등).
    """
    pkg = pkg_path(paths, domain)
    if not pkg.is_dir():
        return {"status": "not_found", "domain": domain, "reason": "도메인 패키지가 없다"}
    staging, meta = staging_paths(pkg)
    if staging.is_dir():
        return {"status": "resumed", "domain": domain, "staging": str(staging)}
    try:
        shutil.copytree(pkg, staging)
    except OSError as e:
        raise StagingError(f"staging 사본을 만들지 못했다: {e}") from e
    mtime = _manifest_mtime(pkg)
    try:
        meta.write_text(str(mtime), encoding="utf-8")
    except OSError as e:
        # [중요] 메타를 못 쓰면 **변경 감지가 꺼진다** — 조용히 넘기지 않고 사실을 싣는다.
        #    세션 자체는 유효하므로 막지는 않는다(원전의 best-effort 와 같은 방향).
        return {"status": "started", "domain": domain, "staging": str(staging),
                "meta_error": f"세션 메타를 쓰지 못했다 — 변경 감지 없이 진행: {e}"}
    return {"status": "started", "domain": domain, "staging": str(staging),
            "live_mtime": mtime}


def commit(paths, domain: str, *, sync=None) -> dict:
    """[중요] rename swap + 색인 **1회**. `sync` 를 주면 그것을 부른다(테스트에서 주입).

    순서가 중요하다: `pkg → .bak` 다음에 `staging → pkg`. [중요] **staging 을 먼저 옮기면
    목적지가 점유돼 실패**하고, 그때 라이브가 이미 사라져 있으면 복구가 어려워진다.
    """
    pkg = pkg_path(paths, domain)
    staging, meta = staging_paths(pkg)
    if not staging.is_dir():
        return {"status": "no_session", "domain": domain}

    # ① 세션 중 라이브가 바뀌었나 — [중요] **막지 않고 알린다** (머리말 ③)
    live_changed = None
    if meta.exists():
        try:
            recorded = float(meta.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            recorded = None
        if recorded is not None:
            live_changed = _manifest_mtime(pkg) != recorded

    # ② 백업은 1세대만 (머리말 ④)
    backup = pkg.with_name(pkg.name + BACKUP_SUFFIX)
    try:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if pkg.exists():
            pkg.rename(backup)
        staging.rename(pkg)
    except OSError as e:
        raise StagingError(f"교체 실패 — 라이브 상태를 확인할 것: {e}") from e
    try:
        meta.unlink()
    except OSError:
        pass

    # ③ 색인은 여기서 **한 번만** — 편집 중에는 돌리지 않았다
    index = {"ran": False}
    if sync is not None:
        try:
            index = {"ran": True, "result": str(sync(paths))}
        except Exception as e:                               # noqa: BLE001
            # [중요] 교체는 이미 끝났다 — 색인 실패가 그것을 되돌리지 않는다. 사실만 싣는다.
            index = {"ran": True, "error": f"{type(e).__name__}: {e}"}

    out = {"status": "committed", "domain": domain, "backup": str(backup), "index": index}
    if live_changed is not None:
        out["live_changed_during_session"] = live_changed
        if live_changed:
            out["note"] = ("[주의] 세션 중 라이브가 바뀌었다 (백그라운드 재합성 등). 막지 않았다 — "
                           "원전 판단: 저빈도 이벤트라 락·머지 인프라 없이 가시성으로 충분")
    else:
        out["live_changed_during_session"] = None
        out["note"] = "세션 메타가 없어 변경 감지를 못 했다"
    return out


def discard(paths, domain: str) -> dict:
    """staging 통째 폐기. [중요] **라이브는 처음부터 안 건드렸으니 되돌릴 것이 없다.**"""
    pkg = pkg_path(paths, domain)
    staging, meta = staging_paths(pkg)
    if not staging.is_dir():
        return {"status": "no_session", "domain": domain}
    shutil.rmtree(staging, ignore_errors=True)
    try:
        meta.unlink()
    except OSError:
        pass
    return {"status": "discarded", "domain": domain,
            "live_untouched": pkg.is_dir()}


def status(paths, domain: str = "") -> dict:
    """세션 현황. `domain` 을 비우면 전부 훑는다 — [중요] **열린 세션을 잊는 것이 위험**하다."""
    root = Path(paths.ontology) / "domains"
    if not root.is_dir():
        return {"sessions": [], "error": f"도메인 디렉토리가 없다: {root}"}
    names = [domain] if domain else sorted(
        p.name[:-len(STAGING_SUFFIX)] for p in root.iterdir()
        if p.is_dir() and p.name.endswith(STAGING_SUFFIX))
    out = []
    for n in names:
        try:
            pkg = pkg_path(paths, n)
        except StagingError as e:
            out.append({"domain": n, "error": str(e)})
            continue
        staging, meta = staging_paths(pkg)
        if not staging.is_dir():
            continue
        out.append({"domain": n, "staging": str(staging),
                    "meta": meta.exists(),
                    "live_changed": (_manifest_mtime(pkg) != float(
                        meta.read_text(encoding="utf-8").strip()))
                    if meta.exists() and meta.read_text(encoding="utf-8").strip()
                       .replace(".", "").isdigit() else None})
    return {"sessions": out}


def default_sync(paths):
    """우리 색인 동기 — `domain_index.sync`. commit 이 **한 번만** 부른다."""
    from ..context_search import domain_index
    return domain_index.sync(paths)


def main(argv: list | None = None) -> int:
    import json
    import sys
    from ..context_search.paths import resolve

    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "status"
    if cmd in ("-h", "--help", "help"):
        print("사용법: python -m master.ontology.staging status|begin|commit|discard [도메인]")
        print("  [중요] 편집 중에는 라이브가 안 바뀐다. commit 이 원자적으로 교체하고 색인 1회.")
        print("  [주의] 세션을 강제하지 않는다 — 단건 편집은 세션 없이도 된다(원전 판단).")
        return 0
    paths = resolve("")
    dom = args[1] if len(args) > 1 else ""
    if cmd == "status":
        print(json.dumps(status(paths, dom), ensure_ascii=False, indent=2))
        return 0
    if not dom:
        print("도메인 이름이 필요하다")
        return 2
    fn = {"begin": begin, "discard": discard}.get(cmd)
    if fn:
        print(json.dumps(fn(paths, dom), ensure_ascii=False, indent=2))
        return 0
    if cmd == "commit":
        print(json.dumps(commit(paths, dom, sync=default_sync), ensure_ascii=False, indent=2))
        return 0
    print(f"모르는 명령: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
