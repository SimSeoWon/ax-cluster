"""수집 세션 귀속 출처 실측 — 미귀속 원인·스냅샷 토큰·usage_log session_id 결합 기회를 읽기 전용으로 센다 (`#1018`, 웨이파인더 `#741`).

🔴 [중요] **왜 지금 있나.** 수집된 세션 사본(`session_usage`)의 대부분이 `_unassigned` 이고
   work_id·task_id 는 전부 비어 있다. 뒤 노드들 — `#1019`(usage_log session_id → 프로젝트·work·task 결합) ·
   `#1020`(경로 규칙: `.ax-issues/<N>`·윈도우 이중 구분자 `_norm`) · `#1021`(session_id 스탬프 커버리지) ·
   `#1022`(/usage 미귀속 원인별 표시) · `#1023`(재검증) — 가 고치기 **전의 기준선**을 숫자로 남긴다.

    python -m master.work.session_provenance [--json] [--raw-root PATH] [--store PATH] [--projects-root PATH]

[중요] **읽기 전용이다.** 원본 사본 루트·스냅샷 루트·프로젝트 루트 어디에도 쓰지 않는다.
   LLM·SSH·수집·reparse 를 부르지 않는다. 귀속 판정은 `session_usage` 의 `attribute`·`_norm`·
   `workshop_paths`·`load_index` 를, 토큰 합은 `usage_dashboard._normal_record` 를 그대로 쓴다(두 벌 금지).

[중요] **출력에 경로·원문을 싣지 않는다.** 범주·호스트(IP)·도구·프로젝트명·건수·이슈 번호만 싣는다.
   cwd·origin·홈 경로·절대 경로는 표에도 JSON 에도 stderr 로그에도 나가지 않는다.

## 미귀속 원인 분류 — 순서가 계약이다 (한 항목은 정확히 한 원인)

    1 empty_cwd             cwd 가 비었거나 없다
    2 master_home           host == local 이고 cwd 가 마스터 홈(주입 `home`)과 정확히 같다
    3 windows_double_slash  윈도우 호스트(`HOSTS`)이고 cwd 에 구분자가 연달아 있으며, 연속 구분자를
                            하나로 접으면 `attribute` 가 등록 체크아웃에 잇는다 — `_norm` 결함(`#1020`)
    4 ax_issues             정규화한 cwd 에 `/.ax-issues/<숫자>` 구간이 있다 (이슈 번호를 센다)
    5 tmp_ax                POSIX cwd 가 `/tmp/ax-` 로 시작한다
    6 tmp_other             그 밖의 `/tmp/` 아래
    7 other                 나머지

[주의] 4 는 체크아웃 접두를 따지지 않는다 — 등록 체크아웃 **아래**의 `.ax-issues` 는 이미 그 프로젝트로
   귀속되므로(접두 일치), 미귀속에 남는 것은 체크아웃 밖의 worktree 다. 귀속된 쪽은 따로 센다
   (`assigned_ax_issues`·`assigned_ax_work`) — task·work 가 비어 있는 그 몫이 `#1020` 의 대상이다.

## session_id 를 얻는 법 (usage_log 결합)

색인 항목 하나의 세션 id 후보 = ⑴ 연결된 스냅샷의 `session_id`(파서가 읽은 값 — codex `session_meta.id` ·
claude `sessionId`) ∪ ⑵ origin 에서 읽은 id(codex 는 파일 이름 끝의 uuid — `usage.py` 실측 2026-10-09
「thread_id = rollout 파일 이름의 uuid」 · claude 는 파일 이름(확장자 제외) · agy 는 `brain/<대화 id>/`).
usage_log 한 줄의 `session_id` 가 이 후보 중 하나와 같으면 「결합 가능」이다. 여러 항목이 맞으면 색인 키
정렬 순 첫 항목의 귀속(프로젝트 또는 미귀속 원인)으로 나눈다. host 일치는 따지지 않는다.

[주의] 스냅샷 토큰은 **예비**다 — Claude 파일 간 응답 중복(`#740`) 보정 전 합이다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

from .session_usage import (DEFAULT_RAW, DEFAULT_STORE, HOSTS, UNASSIGNED, _key, _norm,
                            attribute, load_index, workshop_paths)

CAUSES = ("empty_cwd", "master_home", "windows_double_slash", "ax_issues",
          "tmp_ax", "tmp_other", "other")
LANE_FAMILIES = ("codex", "agy", "claude", "local", "other")
UNLINKED = "unlinked"
PRELIMINARY = "예비 — 파일 간 중복 보정 전"

_AX_ISSUES = re.compile(r"/\.ax-issues/(\d+)(?:/|$)")
_AX_WORK = re.compile(r"/\.ax/work/[^/]+(?:/|$)")
_REPEATED = re.compile(r"[\\/]{2,}")
_UUID_TAIL = re.compile(r"([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
                        r"[0-9A-Fa-f]{12})$")


def _log(msg: str) -> None:
    # [주의] 경로·cwd·origin 을 싣지 않는다 — 건수와 범주만
    print(f"[session_provenance] {msg}", file=sys.stderr, flush=True)


def _bump(table: dict, *keys, n: int = 1) -> None:
    """중첩 dict 계수기 — 마지막 키에 n 을 더한다."""
    for k in keys[:-1]:
        table = table.setdefault(k, {})
    table[keys[-1]] = table.get(keys[-1], 0) + n


def _sorted(obj):
    """결정적 출력 — dict 는 키 정렬, 그 안도 재귀."""
    if isinstance(obj, dict):
        return {k: _sorted(obj[k]) for k in sorted(obj, key=str)}
    if isinstance(obj, list):
        return [_sorted(v) for v in obj]
    return obj


# ---------------------------------------------------------------- 원인 분류

def _windows(host: str) -> bool:
    return HOSTS.get(host, ("", False))[1]


def classify(cwd: str, host: str, shops: dict, home: str) -> tuple[str, int | None]:
    """미귀속 항목 하나의 원인과(ax_issues 면) 이슈 번호. 순서는 머리말 표 — 첫 일치가 이긴다."""
    cwd = cwd if isinstance(cwd, str) else ""
    if not cwd.strip():
        return "empty_cwd", None
    if host == "local" and cwd.rstrip("/") == str(home).rstrip("/"):
        return "master_home", None
    windows = _windows(host)
    if windows and _REPEATED.search(cwd):
        collapsed = _REPEATED.sub("/", cwd)
        if attribute(collapsed, host, shops)[0] is not None:
            return "windows_double_slash", None
    flat = _REPEATED.sub("/", _norm(cwd, windows))
    m = _AX_ISSUES.search(flat)
    if m:
        return "ax_issues", int(m.group(1))
    if not windows:
        if cwd.startswith("/tmp/ax-"):
            return "tmp_ax", None
        if cwd.startswith("/tmp/"):
            return "tmp_other", None
    return "other", None


# ---------------------------------------------------------------- 1. 원본 색인

def _owner(entry: dict) -> str:
    return entry.get("project") or UNASSIGNED


def raw_index_section(index: dict, shops: dict, home: str) -> tuple[dict, dict]:
    """색인 → (보고 절, {색인 키: 귀속 라벨}). 라벨은 `project:<이름>` 또는 `unassigned:<원인>`."""
    by_project: dict = {}
    causes = {c: 0 for c in CAUSES}
    by_tool: dict = {}
    by_host: dict = {}
    issues: dict = {}
    labels: dict = {}
    stamped = assigned_issues = assigned_work = 0
    assigned_issue_numbers: dict = {}
    unassigned = 0
    for key in sorted(index):
        e = index[key]
        host, tool = str(e.get("host") or ""), str(e.get("tool") or "")
        cwd = e.get("cwd") if isinstance(e.get("cwd"), str) else ""
        _bump(by_project, _owner(e))
        if e.get("work_id") or e.get("task_id"):
            stamped += 1
        if e.get("project"):
            labels[key] = f"project:{e['project']}"
            flat = _REPEATED.sub("/", _norm(cwd, _windows(host)))
            m = _AX_ISSUES.search(flat)
            if m:
                assigned_issues += 1
                _bump(assigned_issue_numbers, int(m.group(1)))
            if _AX_WORK.search(flat):
                assigned_work += 1
            continue
        unassigned += 1
        cause, issue = classify(cwd, host, shops, home)
        labels[key] = f"unassigned:{cause}"
        causes[cause] += 1
        _bump(by_tool, cause, tool)
        _bump(by_host, cause, host)
        if issue is not None:
            _bump(issues, issue)
    total_causes = sum(causes.values())
    ok = total_causes == unassigned
    if not ok:
        _log(f"[경고] 원인 합 {total_causes} != 미귀속 {unassigned}")
    _log(f"원본 색인 {len(index)}건 · 미귀속 {unassigned}건 · 원인 합 일치={ok}")
    section = {
        "total": len(index), "by_project": by_project, "unassigned": unassigned,
        "causes": causes, "causes_by_tool": by_tool, "causes_by_host": by_host,
        "cause_sum_ok": ok,
        "ax_issue_numbers": {str(k): v for k, v in sorted(issues.items())},
        "work_or_task_set": stamped,
        "assigned_ax_issues": assigned_issues,
        "assigned_ax_issue_numbers": {str(k): v for k, v in sorted(assigned_issue_numbers.items())},
        "assigned_ax_work": assigned_work,
    }
    return section, labels


# ---------------------------------------------------------------- 2. 스냅샷 토큰

def _read_snapshots(store: Path):
    """(색인 키, 스냅샷 dict) — 정렬 순. 못 읽은 파일은 (None, None)."""
    root = Path(store)
    if not root.is_dir():
        return
    for path in sorted(root.glob("*/*/*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                raise ValueError("스냅샷 형식")
            key = _key(str(data.get("host") or path.parent.parent.name),
                       str(data.get("tool") or path.parent.name), str(data.get("origin") or ""))
        except (OSError, ValueError, TypeError):
            yield None, None
            continue
        yield key, data


def snapshot_section(store: Path, labels: dict) -> tuple[dict, dict]:
    """스냅샷 토큰을 귀속 라벨별로 합한다(예비). 반환 (보고 절, {색인 키: 스냅샷 session_id}).

    잇는 키는 `session_usage._key(host, tool, origin)` — 스냅샷이 스스로 싣는 세 값이다.
    색인에 없는 스냅샷은 `unlinked`, 스냅샷이 없는 색인 항목은 `index_without_snapshot` 으로 센다.
    """
    from .usage_dashboard import _normal_record
    rows: dict = {}
    sids: dict = {}
    linked: set = set()
    unreadable = invalid = 0
    for key, data in _read_snapshots(store):
        if key is None:
            unreadable += 1
            continue
        tool = key.split("\t", 2)[1]
        label = labels.get(key, UNLINKED)
        if key in labels:
            linked.add(key)
        sid = data.get("session_id")
        if key in labels and isinstance(sid, str) and sid:
            sids[key] = sid
        row = rows.setdefault(label, {"files": 0, "records": 0, "tokens": 0, "by_tool": {}})
        row["files"] += 1
        for raw in data["records"]:
            try:
                rec = _normal_record(raw, session=True, tool=tool)
            except (ValueError, TypeError):
                invalid += 1
                continue
            row["records"] += 1
            row["tokens"] += rec["tokens"] or 0
            _bump(row["by_tool"], tool, n=rec["tokens"] or 0)
    files = sum(r["files"] for r in rows.values())
    _log(f"스냅샷 {files}건 · 미연결 {rows.get(UNLINKED, {}).get('files', 0)}건 · "
         f"못 읽음 {unreadable} · 잘못된 레코드 {invalid}")
    section = {"label": PRELIMINARY, "files": files, "unreadable": unreadable,
               "invalid_records": invalid, "by_label": rows,
               "index_without_snapshot": len(labels) - len(linked)}
    return section, sids


# ---------------------------------------------------------------- 3. usage_log 커버리지

def origin_session_id(tool: str, origin: str) -> str:
    """origin(원래 상대 경로)에서 세션 id. 못 읽으면 빈 문자열."""
    parts = PurePosixPath(str(origin).replace("\\", "/")).parts
    if not parts:
        return ""
    if tool == "agy":
        return parts[1] if len(parts) >= 3 and parts[0] == "brain" else ""
    stem = parts[-1].removesuffix(".jsonl")
    if tool == "codex":
        m = _UUID_TAIL.search(stem)
        return m.group(1) if m else ""
    if tool == "claude":
        return stem
    return ""


def session_map(index: dict, snapshot_sids: dict) -> dict:
    """session_id → 색인 키 목록(정렬). 후보는 머리말 「session_id 를 얻는 법」."""
    out: dict = {}
    for key in sorted(index):
        e = index[key]
        ids = {origin_session_id(str(e.get("tool") or ""), str(e.get("origin") or "")),
               snapshot_sids.get(key, "")}
        for sid in sorted(i for i in ids if i):
            out.setdefault(sid, []).append(key)
    return out


def lane_family(lane: object) -> str:
    name = lane.casefold().split(":", 1)[0] if isinstance(lane, str) else ""
    return name if name in LANE_FAMILIES[:-1] else "other"


def usage_log_section(projects_root: Path, names: list, sessions: dict, labels: dict) -> dict:
    """프로젝트별·레인 계열별 행 수 · session_id 있는 행 · 수집 세션과 맞는 행(= `#1019` 기회)."""
    per: dict = {}
    joinable: dict = {}
    bad = 0
    for name in sorted(names):
        path = Path(projects_root) / name / "usage_log.jsonl"
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            _log(f"[주의] {name} usage_log 읽기 실패")
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    raise ValueError
            except ValueError:
                bad += 1
                continue
            fam = lane_family(rec.get("lane"))
            row = per.setdefault(name, {}).setdefault(fam, {"rows": 0, "with_session_id": 0,
                                                            "matched": 0})
            row["rows"] += 1
            sid = rec.get("session_id")
            if not (isinstance(sid, str) and sid.strip()):
                continue
            row["with_session_id"] += 1
            keys = sessions.get(sid.strip())
            if keys:
                row["matched"] += 1
                _bump(joinable, labels.get(keys[0], UNLINKED))
    total = sum(r["matched"] for p in per.values() for r in p.values())
    _log(f"usage_log 프로젝트 {len(per)}개 · 결합 가능 {total}행 · 깨진 줄 {bad}")
    return {"by_project": per, "joinable": total, "joinable_by_label": joinable,
            "invalid_lines": bad}


# ---------------------------------------------------------------- 묶기

def measure(*, raw_root: Path = DEFAULT_RAW, store: Path = DEFAULT_STORE,
            projects_root: Path | None = None, home: Path | None = None,
            shops: dict | None = None, names: list | None = None) -> dict:
    """세 절을 잰다. 읽기 전용. `shops`·`names` 는 검사 주입용(없으면 레지스트리에서)."""
    if shops is None or names is None:
        from ..projects.config import Registry
        reg = Registry.load(Path(projects_root) if projects_root is not None else None)
        projects_root = reg.root
        names = list(reg.names) if names is None else names
        shops = workshop_paths(reg.root) if shops is None else shops
    home = str(home if home is not None else Path.home())
    index = load_index(Path(raw_root))
    raw, labels = raw_index_section(index, shops, home)
    snaps, sids = snapshot_section(Path(store), labels)
    sessions = session_map(index, sids)
    usage = usage_log_section(Path(projects_root), names or [], sessions, labels) \
        if projects_root is not None else {"by_project": {}, "joinable": 0,
                                           "joinable_by_label": {}, "invalid_lines": 0}
    return _sorted({"issue": 1018, "raw_index": raw, "snapshots": snaps, "usage_log": usage})


# ---------------------------------------------------------------- 사람용 표

def render(rep: dict) -> str:
    r, s, u = rep["raw_index"], rep["snapshots"], rep["usage_log"]
    out = ["세션 귀속 출처 실측 (#1018 · #741)", "",
           f"[1] 원본 색인 — 전체 {r['total']}건 · 미귀속 {r['unassigned']}건"]
    for name, n in r["by_project"].items():
        out.append(f"  {name:<24} {n:>7}")
    out.append("  미귀속 원인 (순서: " + " → ".join(CAUSES) + ")")
    for cause in CAUSES:
        n = r["causes"].get(cause, 0)
        tools = " ".join(f"{t}={v}" for t, v in r["causes_by_tool"].get(cause, {}).items())
        hosts = " ".join(f"{h}={v}" for h, v in r["causes_by_host"].get(cause, {}).items())
        out.append(f"  {cause:<22} {n:>7}   도구[{tools}]   호스트[{hosts}]")
    out.append(f"  원인 합 일치: {'예' if r['cause_sum_ok'] else '아니오(경고)'}")
    if r["ax_issue_numbers"]:
        out.append("  미귀속 .ax-issues 이슈: " +
                   ", ".join(f"#{k}={v}" for k, v in r["ax_issue_numbers"].items()))
    out.append(f"  work_id·task_id 채워진 항목: {r['work_or_task_set']}")
    out.append(f"  귀속됐지만 .ax-issues/<N> 아래: {r['assigned_ax_issues']}"
               + (" (" + ", ".join(f"#{k}={v}" for k, v in r["assigned_ax_issue_numbers"].items())
                  + ")" if r["assigned_ax_issue_numbers"] else ""))
    out.append(f"  귀속됐지만 .ax/work/<task> 아래: {r['assigned_ax_work']}")
    out += ["", f"[2] 스냅샷 토큰 ({s['label']}) — 파일 {s['files']} · 못 읽음 {s['unreadable']} · "
                f"잘못된 레코드 {s['invalid_records']} · 스냅샷 없는 색인 항목 {s['index_without_snapshot']}"]
    for label, row in s["by_label"].items():
        tools = " ".join(f"{t}={v:,}" for t, v in row["by_tool"].items())
        out.append(f"  {label:<34} 파일 {row['files']:>6} · 레코드 {row['records']:>7} · "
                   f"토큰 {row['tokens']:>15,}   [{tools}]")
    out += ["", f"[3] usage_log session_id 커버리지 — 결합 가능(#1019 기회) {u['joinable']}행 · "
                f"깨진 줄 {u['invalid_lines']}"]
    for name, fams in u["by_project"].items():
        for fam, row in fams.items():
            out.append(f"  {name:<16} {fam:<8} 행 {row['rows']:>7} · session_id {row['with_session_id']:>7}"
                       f" · 수집 세션과 일치 {row['matched']:>7}")
    if u["joinable_by_label"]:
        out.append("  일치 세션의 현재 귀속: " +
                   " · ".join(f"{k}={v}" for k, v in u["joinable_by_label"].items()))
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="수집 세션 귀속 출처 실측 (#1018) — 읽기 전용")
    ap.add_argument("--json", action="store_true", help="기계용 JSON 을 stdout 에")
    ap.add_argument("--raw-root", default=str(DEFAULT_RAW))
    ap.add_argument("--store", default=str(DEFAULT_STORE))
    ap.add_argument("--projects-root", default=None,
                    help="기본은 AX_PROJECTS_ROOT (레지스트리)")
    a = ap.parse_args(argv)
    from ..projects.config import ConfigError
    try:
        rep = measure(raw_root=Path(a.raw_root), store=Path(a.store),
                      projects_root=Path(a.projects_root) if a.projects_root else None)
    except ConfigError:
        _log("레지스트리를 읽지 못했다 — AX_PROJECTS_ROOT 또는 --projects-root 를 확인")
        return 2
    sys.stdout.write(json.dumps(rep, ensure_ascii=False, indent=2) + "\n" if a.json else render(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
