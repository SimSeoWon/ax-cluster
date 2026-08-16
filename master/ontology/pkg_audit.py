"""도메인 MD ↔ 패키지 일관성 감사 — 원전 `watcher/ontology_pkg_audit.py`(235줄) 이식
(소 3.1.5 · `#188`, 2026-08-15).

감사 **둘**이고 [중요] **전부 read-only 다. 자동 수정은 없다** (원전: *"자동 수정 X — 카나리 로그만"*).

    ① 도메인 MD 일관성   `context/_domains/*.md` — 중복 stem · `status:` 누락 ·
                         `_archive` 안인데 `status: active`
    ② 패키지 walk        `ontology/domains/<D>/` — objects/actions/invariants 카운트 + 레이어 분포

## [중요] 왜 자동 수정을 하지 않나 (원전 판단을 그대로 옮긴다)

`gaps` 는 *"수치 0건"* 신호일 뿐이고 원인이 둘이다 — **사이클 미진입**과 **LLM 응답 0건**이
디렉토리 부재로 **같은 외양**을 낸다. 원전 주석: *"둘을 구분 안 함: 「수치 0건」 신호만 노출.
진짜 갭이면 fingerprint 리셋이 사용자 액션."* [중요] 구분할 수 없는 것을 자동으로 고치면 정상
상태를 망친다. 이 저장소의 *"자동 승급 폐기 · 사람이 시켜야 부른다"* 와 같은 결이다.

## [주의] 원전과 다른 것 — manifest 파일명

    원전   `_MANIFEST_FILENAME` (도메인 패키지의 존재 표식)
    우리   `domain.yaml`

manifest 가 없는 디렉토리는 **카운트하지 않는다**(원전 그대로) — *"옛 단일 yaml 잔재 또는
손상. audit 책임 밖"*. [중요] 그 판단을 유지한다: 감사가 손상까지 세면 「갭」과 「쓰레기」가 섞인다.

## [중요] 감사가 드러낸 것 — 도메인 이름 규칙이 입구마다 다르다 (실측 2026-08-15)

첫 실 구동에서 갭 1건이 나왔다: `_archive` 안에 `status: active` 인 도메인 MD 하나
(`미션 태스크 스냅샷 동기화.20260813-015409.md`). [주의] **나는 이것을 「한글 이름이라 규약
위반」으로 읽었고 틀렸다** (사용자 정정: *"한글로 저장할 수 있도록 수정했을 거야"*).

실제로는 **입구가 둘이고 규칙이 반대**다:

    master/ontology/create.py   [중요] 한글 도메인명 **거부**(`CreateError`) —
                                *"경로·URL·검색 식별자에서 깨진다. 원본이 같은 이유로 거부"*
    master/webui/board.py       [완료] 한글 도메인명 **허용**(의도) — 실측 기록까지 있다:
                                *"내가 `[A-Za-z0-9_-]` 로 좁혔더니 한글 도메인명이 통째로
                                날아가 파일명이 `domain` 이 됐다(2026-08-13). 리눅스에서
                                한글 파일명은 문제가 아니다."* 게다가 LLM 에게 **한글 이름을
                                제안하라**고 시킨다

[중요] **이것은 결함이 아니다 — 이전 마일스톤에서 만든 한글 지원의 산물이다** (사용자 2026-08-15:
*"지금은 복각을 우선하고 있고, 한글 지원은 이전 마일스톤에서 만든 거야. 일단 보관하고 메모를
남겨뒀다가, 복각이 끝난 뒤 머지하자."*)

[주의] **그래서 여기서 판정하지 않고, 고치지도 않는다.** 이 감사는 read-only 이고, 두 입구의
차이는 **복각이 끝난 뒤 머지할 항목**이다 → `#194`. [중요] **감사가 그것을 「갭」으로 표시하는 것은
정상이다** — 감사는 원전 기준으로 보고, 그 기준과 우리 한글 지원이 만나는 자리를 드러내는 것이
이 순간의 값이다. 갭 문장을 지우거나 규칙을 지금 바꾸면 **머지할 때 무엇이 달랐는지 알 수 없다.**

## PyYAML 의존 0

원전 정신을 유지한다 — 디렉토리 walk + glob 카운트 + frontmatter **정규식** 파싱만.
[중요] 감사가 파서에 의존하면 **파서가 깨질 때 감사도 함께 눈을 감는다.**
"""
from __future__ import annotations

import re
from pathlib import Path

MANIFEST = "domain.yaml"                 # [주의] 원전 `_MANIFEST_FILENAME` 의 우리 이름
OBJECTS, ACTIONS, INVARIANTS = "objects", "actions", "invariants"
LAYER_DIRS = ("L1", "L2", "L3")
ARCHIVE_GLOB = "_archive/**/*.md"

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _frontmatter(text: str) -> dict:
    """frontmatter 를 **정규식으로** 읽는다 (PyYAML 0 — 머리말 참조).

    스칼라만 본다. 감사가 필요한 것은 `status:` 하나이고, 중첩 구조를 읽으려 들면 파서가 된다.
    """
    m = _FM_RE.match(text or "")
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if line.startswith((" ", "\t", "-")) or ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip("'\"")
    return out


# ── ① 도메인 MD 일관성 ────────────────────────────────────────────────────────

def audit_domain_md(context_dir) -> dict:
    """`context/_domains/*.md` 일관성. [중요] read-only.

    검출 셋 (원전 그대로):

        duplicate_stems  직속 + `_archive/` 에 같은 stem — **어느 게 정본인지 모호하다**
        missing_status   frontmatter 에 `status:` 없음 — 승급 누락 또는 손상
        archive_active   `_archive` 안인데 `status: active` — archive 시 flip 안 됨
    """
    d = Path(context_dir) / "_domains"
    if not d.is_dir():
        return {"duplicate_stems": [], "missing_status": [], "archive_active": [],
                "direct_count": 0, "archive_count": 0, "unreadable": [],
                "error": f"도메인 MD 디렉토리가 없다: {d}"}

    # `_` 로 시작하는 것은 `_overview` 등 — 도메인이 아니다 (원전과 같은 제외)
    direct = [p for p in sorted(d.glob("*.md")) if not p.name.startswith("_")]
    archive = sorted(d.glob(ARCHIVE_GLOB))

    dup = sorted({p.stem for p in direct} & {p.stem for p in archive})
    missing, arch_active, unreadable = [], [], []

    for p in direct + archive:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            # [중요] 조용히 건너뛰지 않는다 — 원전은 `except: continue` 였다
            unreadable.append(f"{p.name}: {e}")
            continue
        status = _frontmatter(text).get("status")
        if not status:
            missing.append(p.name)
            continue
        if "_archive" in p.parts and status == "active":
            arch_active.append(p.name)

    return {"duplicate_stems": dup, "missing_status": missing,
            "archive_active": arch_active, "direct_count": len(direct),
            "archive_count": len(archive), "unreadable": unreadable}


def md_gaps(result: dict) -> list:
    """사람이 읽는 갭 문장들. 갭이 없으면 **빈 목록**(노이즈를 만들지 않는다)."""
    gaps = []
    if result.get("error"):
        return [f"[중요] {result['error']}"]
    if result["duplicate_stems"]:
        gaps.append(f"[중요] 중복 stem {len(result['duplicate_stems'])}건 (직속+archive, 정본 모호): "
                    + ", ".join(result["duplicate_stems"]))
    if result["missing_status"]:
        gaps.append(f"[주의] frontmatter `status:` 누락 {len(result['missing_status'])}건: "
                    + ", ".join(result["missing_status"][:8]))
    if result["archive_active"]:
        gaps.append(f"[중요] `_archive` 안 `status: active` {len(result['archive_active'])}건 "
                    "(archive 시 flip 안 됨): " + ", ".join(result["archive_active"][:8]))
    if result.get("unreadable"):
        gaps.append(f"[중요] 읽지 못한 파일 {len(result['unreadable'])}건 — 감사에서 빠졌다")
    return gaps


# ── ② 패키지 walk ─────────────────────────────────────────────────────────────

def audit_packages(ontology_dir) -> dict:
    """`ontology/domains/<D>/` walk → 도메인별 entity 카운트 + 레이어 분포. [중요] read-only."""
    out = {"domains": [], "totals": {"domains": 0, "objects": 0, "actions": 0,
                                     "invariants": 0}, "gaps": [], "skipped": []}
    root = Path(ontology_dir) / "domains"
    if not root.is_dir():
        out["error"] = f"도메인 패키지 디렉토리가 없다: {root}"
        return out

    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir():
            continue
        if not (pkg / MANIFEST).exists():
            # [주의] 원전 판단 그대로 — *"옛 단일 yaml 잔재 또는 손상. audit 책임 밖"*.
            #    [중요] 다만 **세어서 보고**한다(원전은 조용히 건너뛴다) — 몇 개를 안 봤는지 모르면
            #    「도메인 N개」가 전부인지 알 수 없다.
            out["skipped"].append(pkg.name)
            continue
        n_obj = len(list(pkg.glob(f"L*/{OBJECTS}/*.yaml")))
        n_act = len(list(pkg.glob(f"L*/{ACTIONS}/*.yaml")))
        n_inv = len(list(pkg.glob(f"L*/{INVARIANTS}/*.yaml")))
        dist = {ld: len(list((pkg / ld / OBJECTS).glob("*.yaml")))
                for ld in LAYER_DIRS if (pkg / ld / OBJECTS).is_dir()}
        out["domains"].append({"name": pkg.name, "objects": n_obj, "actions": n_act,
                               "invariants": n_inv, "layer_dist": dist})
        out["totals"]["domains"] += 1
        out["totals"]["objects"] += n_obj
        out["totals"]["actions"] += n_act
        out["totals"]["invariants"] += n_inv

    # [중요] 갭은 「수치 0건」 신호일 뿐이다 — 원인을 구분하지 않는다 (머리말 참조)
    for d in out["domains"]:
        if d["objects"] == 0:
            out["gaps"].append(f"{d['name']}: objects=0 (분류 미완료 가능)")
        if d["actions"] == 0:
            out["gaps"].append(f"{d['name']}: actions=0 (actions 미추출)")
    return out


# ── 리포트 ────────────────────────────────────────────────────────────────────

def format_report(md: dict, pkg: dict) -> str:
    out = ["# 온톨로지 일관성 감사", "", "## ① 도메인 MD", ""]
    if md.get("error"):
        out += [f"[중요] {md['error']}", ""]
    else:
        out += [f"- 직속 **{md['direct_count']}건** · `_archive` {md['archive_count']}건", ""]
        g = md_gaps(md)
        out += (["[중요] **갭 " + str(len(g)) + "건**", ""] + [f"- {x}" for x in g] + [""]
                if g else ["[완료] 갭 없음", ""])

    out += ["## ② 도메인 패키지", ""]
    if pkg.get("error"):
        out += [f"[중요] {pkg['error']}", ""]
        return "\n".join(out)
    t = pkg["totals"]
    out += [f"- 도메인 **{t['domains']}** · objects {t['objects']} · actions {t['actions']} "
            f"· invariants {t['invariants']}", ""]
    if pkg.get("skipped"):
        out += [f"[주의] `{MANIFEST}` 가 없어 세지 않은 디렉토리 {len(pkg['skipped'])}개: "
                + ", ".join(pkg["skipped"]), ""]
    out += ["| 도메인 | obj | act | inv | 레이어 분포 |", "|---|---|---|---|---|"]
    for d in pkg["domains"]:
        dist = " ".join(f"{ld}={d['layer_dist'][ld]}" for ld in LAYER_DIRS
                        if ld in d["layer_dist"])
        out.append(f"| `{d['name']}` | {d['objects']} | {d['actions']} | {d['invariants']} "
                   f"| {dist or '—'} |")
    out.append("")
    if pkg["gaps"]:
        out += [f"[주의] **갭 {len(pkg['gaps'])}건** — [중요] 「수치 0건」 신호일 뿐이다. 사이클 미진입과 "
                "LLM 응답 0건이 **같은 외양**을 내므로 자동으로 고치지 않는다", ""]
        out += [f"- {g}" for g in pkg["gaps"]] + [""]
    else:
        out += ["[완료] 갭 없음", ""]
    return "\n".join(out)


def run_for_project(paths) -> dict:
    """진단 + 리포트 파일. [중요] **아무것도 고치지 않는다.**

    출력 `<프로젝트 데이터>/analysis/ontology_audit_report.md` (§5.5).
    """
    md = audit_domain_md(paths.context)
    pkg = audit_packages(paths.ontology)
    out_dir = Path(paths.root) / "analysis"
    p = out_dir / "ontology_audit_report.md"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        p.write_text(format_report(md, pkg) + "\n", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "reason": f"리포트 쓰기 실패: {e}", "md": md, "packages": pkg}
    return {"ok": True, "files": [str(p)], "md": md, "packages": pkg,
            "gaps": len(md_gaps(md)) + len(pkg.get("gaps", []))}


def main(argv: list | None = None) -> int:
    import sys
    from ..context_search.paths import resolve

    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] in ("-h", "--help", "help"):
        print("사용법: python -m master.ontology.pkg_audit [프로젝트]")
        print("  [중요] read-only 다 — 진단만 하고 아무것도 고치지 않는다")
        return 0
    paths = resolve(args[0] if args else "")
    r = run_for_project(paths)
    print(format_report(r["md"], r["packages"]))
    if r.get("files"):
        print(f"→ {r['files'][0]}")
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
