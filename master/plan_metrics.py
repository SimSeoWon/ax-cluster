"""플랜 **효용 계측** — `#864` T2·T3. 읽기 전용, LLM 0.

    python -m master.plan_metrics issue <id...> [--json] [--gap-min 30]
    python -m master.plan_metrics baseline --version-id 19 [--json]
    python -m master.plan_metrics compare --version-id 19 --issues 861 857 852 [--json]

재료는 넷이다 — Redmine 이슈(노트 이력 포함, 공개 읽기) · 이슈 본문의 플랜 표 · `git log` ·
`plan_events.jsonl`(거절 기록, `plan_events`). 아무것도 쓰지 않는다.

플랜 지표(`issue`):
  tasks      상태별 개수 · 태스크별 리드타임(첫 작업중 → 완료, 노트 시각) · 차단 횟수 ·
             되돌림(차단→작업중 · 작업중→대기) 횟수
  evidence   완료 전이 노트 중 커밋 해시가 있는 비율과 검사 수치가 있는 비율(따로 센다)
  scope      `#<id>` 를 언급한 커밋이 바꾼 파일 중 태스크 「대상」 칸 밖의 것
             [주의] **근사다** — 「대상」은 자유 서술이라 경로처럼 생긴 토큰만 뽑아 대조한다
  rejections plan_events 의 그 이슈 거절 수·종류
  resume     [주의] **근사다** — 같은 이슈의 연속 전이 사이가 N분 이상이면 교대로 보고, 직전에
             작업중이던 태스크를 교대 뒤 첫 전이가 이어 잡았는지 센다

기준선(`baseline`): 플랜 없는 일감도 잴 수 있는 것만 — 생성→종결 리드타임 · 재개(종결·해결
상태에서 열린 상태로) 횟수 · 해결 상태 체류 시간 · 종결 노트의 근거(해시·검사 수치). 플랜 전용
지표는 기준선에서 N/A 다. 상태의 종결 여부는 `/issue_statuses.json` 의 `is_closed` 로 읽고,
「해결」 계열(작업 뒤 대기 상태)만 이름으로 지정한다(`POST_WORK_NAMES`).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from urllib.request import urlopen

REPO = Path(__file__).resolve().parent.parent
PLAN_PREFIX = "플랜 "
TRANS_RE = re.compile(r"^플랜 (\S+): (\S*) → (\S+)(?: — (.*))?\Z", re.S)
# 커밋 해시: 7~40 자 16진수, **문자와 숫자를 둘 다** 포함해야 한다(날짜 20261031·영단어 오탐 방지).
HASH_RE = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}(?![0-9A-Za-z])")
# 검사 수치: `N/N` · `N건` · `통과` + (`#865` T1) 대문자 `OK` · `N경우` · `rc=N`/`rcN`.
#   [주의] `N대` 단독은 넣지 않는다 — 「워커 3대에 배달」처럼 결과가 아닌 수량에도 붙는다(「3대 OK」는 OK 가 잡는다).
#   `OK` 는 영문자 경계만 본다 — 한글이 \w 라 `\b` 로는 「검사OK」·「184 OK」 구분이 흔들린다.
TEST_RE = re.compile(r"\d+/\d+|\d+\s*건|통과|(?<![A-Za-z])OK(?![A-Za-z])|\d+\s*경우"
                     r"|(?<![A-Za-z])rc\s*=?\s*\d+")
PATH_RE = re.compile(r"[\w./*-]+\.(?:py|md|json|toml|yaml|yml|sh)\b")
# `#865` T2 — 작업 커밋: 제목이 `종류(… #N …)` 모양(`fix(#862 T1)` · `fix(#861 T2, #857 T7)`).
#   「후속 #N」·「(#826 · #852)」처럼 제목에 지나가며 단 언급은 범위 밖이다.
WORK_SCOPE_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*\(([^)]*)\)")
DIR_RE = re.compile(r"(?<![\w/:])[A-Za-z_][\w.-]*(?:/[\w.-]+)*/(?![\w*])")
WORKING, DONE, BLOCKED, WAITING = "작업중", "완료", "차단", "대기"
POST_WORK_NAMES = ("해결", "검토")
RESOLVED_NAME = "해결"
WORKING_STATUS_NAME = "진행"     # 기준선 착수 근사 — 첫 「진행」 상태 전이 (#865 T4)
APPROX = "근사"


# ── 시각 ────────────────────────────────────────────────────────────────

def ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def minutes(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 60, 1)


# ── 가져오기 (주입 가능) ─────────────────────────────────────────────────

def _base() -> str:
    from master import redmine
    return redmine.base_url()


def http_json(path: str, *, opener=urlopen) -> dict:
    with opener(f"{_base()}{path}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_issue(issue_id, *, get=http_json) -> dict:
    return get(f"/issues/{int(issue_id)}.json?include=journals")["issue"]


def fetch_statuses(*, get=http_json) -> dict[int, dict]:
    return {int(s["id"]): s for s in get("/issue_statuses.json")["issue_statuses"]}


def fetch_version_issue_ids(version_id, *, get=http_json, page: int = 100) -> list[int]:
    ids, offset = [], 0
    while True:
        got = get(f"/issues.json?fixed_version_id={int(version_id)}&status_id=*"
                  f"&limit={page}&offset={offset}")
        ids += [int(i["id"]) for i in got.get("issues") or []]
        offset += page
        if offset >= int(got.get("total_count") or 0) or not got.get("issues"):
            return ids


def git_run(args: list[str], *, repo: Path = REPO) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def issue_commits(issue_id, *, git=git_run) -> list[dict]:
    """`#<id>` 를 언급한 커밋(모든 ref)과 바꾼 파일. `#86` 은 `#861` 과 맞지 않는다."""
    out = git(["log", "--all", "-E", f"--grep=#{int(issue_id)}([^0-9]|$)", "--name-only",
               "--format=%x1e%H%x1f%B%x1f"])
    own = re.compile(rf"#{int(issue_id)}(?!\d)")
    commits = []
    for chunk in out.split("\x1e"):
        if "\x1f" not in chunk:
            continue
        h, body, files = chunk.split("\x1f", 2)
        if not own.search(body):                     # grep 이 넓게 잡은 것을 한 번 더 거른다
            continue
        subject = body.strip().splitlines()[0] if body.strip() else ""
        ws = WORK_SCOPE_RE.match(subject)
        commits.append({"hash": h.strip(), "subject": subject,
                        "primary": bool(own.search(subject)),   # 제목에 언급 = 그 일감의 커밋
                        "work": bool(ws and own.search(ws.group(1))),   # 제목 범위 칸에 = 작업 커밋 (#865)
                        "files": [f.strip() for f in files.splitlines() if f.strip()]})
    return commits


# ── 플랜 전이 ───────────────────────────────────────────────────────────

def plan_transitions(journals: list[dict]) -> list[dict]:
    out = []
    for j in sorted(journals or [], key=lambda j: j.get("created_on") or ""):
        m = TRANS_RE.match((j.get("notes") or "").strip())
        if m:
            out.append({"at": ts(j.get("created_on")), "task": m.group(1), "from": m.group(2),
                        "to": m.group(3), "note": (m.group(4) or "").strip()})
    return out


def has_hash(text: str) -> bool:
    return bool(HASH_RE.search(text or ""))


def has_test(text: str) -> bool:
    return bool(TEST_RE.search(text or ""))


def task_stats(trans: list[dict]) -> dict[str, dict]:
    per: dict[str, dict] = {}
    for t in trans:
        s = per.setdefault(t["task"], {"started": None, "done": None, "blocked": 0,
                                       "unblocked": 0, "back_to_waiting": 0})
        if t["to"] == WORKING and s["started"] is None:
            s["started"] = t["at"]
        if t["to"] == DONE and s["done"] is None:
            s["done"] = t["at"]
        if t["to"] == BLOCKED:
            s["blocked"] += 1
        if t["from"] == BLOCKED and t["to"] == WORKING:
            s["unblocked"] += 1
        if t["from"] == WORKING and t["to"] == WAITING:
            s["back_to_waiting"] += 1
    return {k: {"lead_min": minutes(v["started"], v["done"]), "blocked": v["blocked"],
                "reopen": v["unblocked"] + v["back_to_waiting"],
                "blocked_to_working": v["unblocked"], "working_to_waiting": v["back_to_waiting"]}
            for k, v in per.items()}


def evidence_fidelity(trans: list[dict]) -> dict:
    done = [t for t in trans if t["to"] == DONE]
    n = len(done)
    h = sum(has_hash(t["note"]) for t in done)
    c = sum(has_test(t["note"]) for t in done)
    e = sum(has_hash(t["note"]) or has_test(t["note"]) for t in done)
    ratio = (lambda x: round(x / n, 3) if n else None)
    return {"done_transitions": n, "with_hash": h, "with_test": c, "with_either": e,
            "hash_ratio": ratio(h), "test_ratio": ratio(c), "either_ratio": ratio(e)}


def resume_accuracy(trans: list[dict], gap_min: float = 30) -> dict:
    """[근사] N분 이상 공백을 교대로 본다 — 직전 작업중 태스크를 공백 뒤 첫 전이가 이어 잡았나."""
    working: set[str] = set()
    gaps = countable = continued = 0
    cases = []
    for i, t in enumerate(trans):
        if t["to"] == WORKING:
            working.add(t["task"])
        else:
            working.discard(t["task"])
        if i + 1 >= len(trans):
            break
        nxt = trans[i + 1]
        gap = minutes(t["at"], nxt["at"])
        if gap is None or gap < gap_min:
            continue
        gaps += 1
        if not working:
            cases.append({"gap_min": gap, "working": [], "next": nxt["task"], "continued": None})
            continue
        countable += 1
        ok = nxt["task"] in working
        continued += ok
        cases.append({"gap_min": gap, "working": sorted(working), "next": nxt["task"],
                      "continued": ok})
    return {"label": APPROX, "gap_min": gap_min, "gaps": gaps, "countable": countable,
            "idle_gaps": gaps - countable, "continued": continued,
            "ratio": round(continued / countable, 3) if countable else None, "cases": cases}


# ── 범위 이탈 ───────────────────────────────────────────────────────────

def target_tokens(targets: list[str]) -> list[str]:
    toks: list[str] = []
    for cell in targets:
        cell = (cell or "").replace("`", " ")
        for tok in PATH_RE.findall(cell) + DIR_RE.findall(cell):
            tok = tok.strip()
            if tok.startswith("./"):
                tok = tok[2:]
            if tok and tok not in toks:
                toks.append(tok)
    return toks


def in_targets(path: str, tokens: list[str]) -> bool:
    for tok in tokens:
        if tok.endswith("/"):
            if path.startswith(tok) or f"/{tok}" in f"/{path}":
                return True
        elif any(ch in tok for ch in "*?["):
            if fnmatch(path, tok) or fnmatch(path, f"*/{tok}"):
                return True
        elif path == tok or path.endswith("/" + tok):
            return True
    return False


def scope_drift(commits: list[dict], targets: list[str]) -> dict:
    """대상 밖 파일. `primary_*` 는 **제목에** 이슈를 단 커밋만 센 값 — 본문에서 지나가며 언급한
    커밋(인수인계·다른 일감)이 이탈을 부풀리는 것을 갈라 본다."""
    tokens = target_tokens(targets)

    def measure(cs):
        files = sorted({f for c in cs for f in c["files"]})
        outside = [f for f in files if not in_targets(f, tokens)]
        return files, outside

    files, outside = measure(commits)
    pfiles, poutside = measure([c for c in commits if c.get("primary")])
    wcs = [c for c in commits if c.get("work")]
    wfiles, woutside = measure(wcs)
    return {"label": APPROX, "commits": [c["hash"][:9] for c in commits], "files": len(files),
            "target_tokens": tokens, "outside": outside,
            "outside_ratio": round(len(outside) / len(files), 3) if files else None,
            "primary_commits": sum(1 for c in commits if c.get("primary")),
            "primary_files": len(pfiles), "primary_outside": poutside,
            "primary_outside_ratio": round(len(poutside) / len(pfiles), 3) if pfiles else None,
            "work_commits": [c["hash"][:9] for c in wcs], "work_files": len(wfiles),
            "work_outside": woutside,
            "work_outside_ratio": round(len(woutside) / len(wfiles), 3) if wfiles else None,
            "note": "「대상」 칸은 자유 서술 — 경로처럼 생긴 토큰만 대조한 근사치"}


# ── 플랜 갱신 내용 (#865 T3) ─────────────────────────────────────────────

PLAN_SET_PREFIXES = ("플랜 등록", "플랜 갱신")
_TASK_FIELDS = ("goal", "target", "deps", "check", "steps")


def _desc_change(j: dict) -> tuple[str, str] | None:
    for d in j.get("details") or []:
        if d.get("name") == "description" and d.get("property", "attr") == "attr":
            return d.get("old_value") or "", d.get("new_value") or ""
    return None


def _parse_or_none(body: str):
    from master import plan_block as PB
    try:
        return PB.parse(body)
    except PB.PlanError:
        return None


def plan_changes(journals: list[dict]) -> dict:
    """플랜 등록·갱신 노트마다 **무엇이 바뀌었나** — 저널 description 상세의 전후 본문으로 비교한다.

    갱신 노트 자체는 「추가 없음 · 제거 없음」만 적어 대상 확장 같은 변화가 안 보였다(#862 실측).
    대상 변경은 경로 토큰으로 「확장」(새 토큰만)·「축소」(빠진 토큰만)·「변경」으로 나눈다.
    전후 본문이 없거나 파싱이 안 되면 그 이벤트는 `diff: None` 으로 남긴다(추측하지 않는다).
    """
    events = []
    for j in sorted(journals or [], key=lambda j: j.get("created_on") or ""):
        note = (j.get("notes") or "").strip()
        if not note.startswith(PLAN_SET_PREFIXES):
            continue
        kind = "등록" if note.startswith("플랜 등록") else "갱신"
        why = note.split("사유:", 1)[1].strip() if "사유:" in note else ""
        ev = {"at": ts(j.get("created_on")), "kind": kind, "why": why, "diff": None}
        ch = _desc_change(j)
        old_p = new_p = None
        if ch is not None:
            old_p, new_p = _parse_or_none(ch[0]), _parse_or_none(ch[1])
        if ch is not None and new_p is not None:
            old_t = {t.id: t for t in (old_p.tasks if old_p else [])}
            new_t = {t.id: t for t in new_p.tasks}
            fields: dict[str, list[str]] = {}
            targets = []
            for tid in [t for t in new_t if t in old_t]:
                for f in _TASK_FIELDS:
                    if getattr(old_t[tid], f) != getattr(new_t[tid], f):
                        fields.setdefault(f, []).append(tid)
                if old_t[tid].target != new_t[tid].target:
                    a = target_tokens([old_t[tid].target])
                    b = target_tokens([new_t[tid].target])
                    plus = [x for x in b if x not in a]
                    minus = [x for x in a if x not in b]
                    label = ("확장" if plus and not minus else "축소" if minus and not plus else "변경")
                    targets.append({"task": tid, "change": label, "added": plus, "removed": minus})
            ev["diff"] = {"added": [t for t in new_t if t not in old_t],
                          "removed": [t for t in old_t if t not in new_t],
                          "fields": fields, "targets": targets}
        events.append(ev)
    diffs = [e["diff"] for e in events if e["diff"]]
    return {"events": events,
            "registers": sum(1 for e in events if e["kind"] == "등록"),
            "updates": sum(1 for e in events if e["kind"] == "갱신"),
            "unreadable": sum(1 for e in events if e["diff"] is None),
            "tasks_added_after_register": sum(len(d["added"]) for e, d in
                                              ((e, e["diff"]) for e in events if e["diff"])
                                              if e["kind"] == "갱신"),
            "tasks_removed": sum(len(d["removed"]) for d in diffs),
            "target_changes": sum(len(d["targets"]) for d in diffs),
            "target_expansions": sum(1 for d in diffs for t in d["targets"] if t["change"] == "확장")}


# ── 기준선 (플랜 없는 일감도 잴 수 있는 것) ─────────────────────────────────

def _status_changes(issue: dict) -> list[tuple[datetime, int, int, dict]]:
    out = []
    for j in sorted(issue.get("journals") or [], key=lambda j: j.get("created_on") or ""):
        for d in j.get("details") or []:
            if d.get("name") == "status_id" and d.get("property", "attr") == "attr":
                try:
                    out.append((ts(j["created_on"]), int(d.get("old_value")),
                                int(d.get("new_value")), j))
                except (TypeError, ValueError):
                    continue
    return out


def work_start(issue: dict, statuses: dict[int, dict]) -> tuple[datetime | None, str]:
    """착수 시각 (`#865` T4) — 가장 이른 것: 첫 「진행」 상태 전이 · 플랜 등록 노트 · 첫 플랜 「작업중」 전이.

    플랜 없는 일감은 「진행」 전이만 남는다. 아무것도 없으면 `(None, "")` — 측정 불가로 센다
    (M6 32건 중 「진행」을 거친 것은 13건뿐이었다, 실측 2026-11-01).
    """
    working = {i for i, st in statuses.items() if st.get("name") == WORKING_STATUS_NAME}
    cands = [(when, "진행 전이") for when, _o, new, _j in _status_changes(issue) if new in working]
    for j in issue.get("journals") or []:
        note = (j.get("notes") or "").strip()
        if note.startswith("플랜 등록"):
            cands.append((ts(j.get("created_on")), "플랜 등록"))
    cands += [(t["at"], "플랜 작업중") for t in plan_transitions(issue.get("journals") or [])
              if t["to"] == WORKING]
    cands = [c for c in cands if c[0] is not None]
    return min(cands, key=lambda c: c[0]) if cands else (None, "")


def baseline_metrics(issue: dict, statuses: dict[int, dict], *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    closed = {i for i, s in statuses.items() if s.get("is_closed")}
    post = {i for i, s in statuses.items() if s.get("name") in POST_WORK_NAMES}
    resolved = {i for i, s in statuses.items() if s.get("name") == RESOLVED_NAME}
    changes = _status_changes(issue)
    created, closed_on = ts(issue.get("created_on")), ts(issue.get("closed_on"))
    reopen = sum(1 for _, old, new, _ in changes
                 if old in (closed | post) and new not in (closed | post))
    # 해결 체류: 상태 구간을 이어 붙여 해결 구간만 더한다(종결 이후 구간은 뺀다)
    cur = changes[0][1] if changes else int((issue.get("status") or {}).get("id") or 0)
    at = created
    in_resolved = 0.0
    for when, _old, new, _j in changes:
        if cur in resolved and at and when:
            in_resolved += (when - at).total_seconds()
        cur, at = new, when
    if cur in resolved and at:
        in_resolved += ((closed_on or now) - at).total_seconds()
    closing = [j for _, _o, new, j in changes if new in closed]
    start, start_src = work_start(issue, statuses)
    note = (closing[-1].get("notes") or "") if closing else None
    return {
        "id": issue.get("id"), "subject": issue.get("subject", ""),
        "status": (issue.get("status") or {}).get("name", ""),
        "closed": closed_on is not None,
        "lead_hours": round((closed_on - created).total_seconds() / 3600, 2)
        if (closed_on and created) else None,
        "start_lead_hours": round((closed_on - start).total_seconds() / 3600, 2)
        if (closed_on and start) else None,
        "start_source": start_src,
        "reopen": reopen,
        "resolved_hours": round(in_resolved / 3600, 2),
        "close_note": None if note is None else {"hash": has_hash(note), "test": has_test(note)},
    }


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 2) if xs else None


def aggregate(rows: list[dict]) -> dict:
    closed = [r for r in rows if r["closed"]]
    notes = [r["close_note"] for r in rows if r["close_note"] is not None]
    n = len(notes)
    share = (lambda k: round(sum(1 for x in notes if k(x)) / n, 3) if n else None)
    return {"issues": len(rows), "closed": len(closed),
            "lead_hours_median": _med([r["lead_hours"] for r in closed]),
            "lead_hours_mean": _mean([r["lead_hours"] for r in closed]),
            "start_lead_hours_median": _med([r["start_lead_hours"] for r in closed
                                             if r.get("start_lead_hours") is not None]),
            "start_lead_hours_mean": _mean([r["start_lead_hours"] for r in closed
                                            if r.get("start_lead_hours") is not None]),
            "start_measured": sum(1 for r in closed if r.get("start_lead_hours") is not None),
            "reopened_issues": sum(1 for r in rows if r["reopen"]),
            "reopen_total": sum(r["reopen"] for r in rows),
            "resolved_hours_median": _med([r["resolved_hours"] for r in rows]),
            "close_notes": n,
            "close_note_hash_share": share(lambda x: x["hash"]),
            "close_note_test_share": share(lambda x: x["test"]),
            "close_note_either_share": share(lambda x: x["hash"] or x["test"])}


PLAN_ONLY = ("tasks", "task_lead_min", "evidence(완료 전이 노트)", "scope_drift", "rejections",
             "resume(근사)")


# ── 이슈 하나의 플랜 지표 ───────────────────────────────────────────────

def issue_metrics(issue: dict, *, commits: list[dict], events: list[dict] | None,
                  statuses: dict[int, dict], gap_min: float = 30) -> dict:
    from master import plan_block as PB
    try:
        plan = PB.parse(issue.get("description") or "")
        plan_error = ""
    except PB.PlanError as e:
        plan, plan_error = None, str(e)
    trans = plan_transitions(issue.get("journals") or [])
    by_state: dict[str, int] = {}
    for t in (plan.tasks if plan else []):
        by_state[t.state] = by_state.get(t.state, 0) + 1
    stats = task_stats(trans)
    leads = [v["lead_min"] for v in stats.values() if v["lead_min"] is not None]
    rej = None
    if events is not None:
        kinds: dict[str, int] = {}
        for e in events:
            kinds[e.get("kind", "other")] = kinds.get(e.get("kind", "other"), 0) + 1
        rej = {"total": len(events), "by_kind": kinds}
    sets = sum(1 for j in issue.get("journals") or []
               if (j.get("notes") or "").startswith(("플랜 등록", "플랜 갱신")))
    return {
        "id": issue.get("id"), "subject": issue.get("subject", ""),
        "has_plan": plan is not None, "plan_error": plan_error,
        "plan_version": plan.version if plan else None,
        "tasks_by_state": by_state,
        "tasks": {k: v for k, v in stats.items()},
        "task_lead_min_median": _med(leads),
        "transitions": len(trans), "plan_sets": sets,
        "plan_changes": plan_changes(issue.get("journals") or []),
        "blocked_total": sum(v["blocked"] for v in stats.values()),
        "reopen_total": sum(v["reopen"] for v in stats.values()),
        "evidence": evidence_fidelity(trans),
        "scope": scope_drift(commits, [t.target for t in (plan.tasks if plan else [])]),
        "rejections": rej,
        "resume": resume_accuracy(trans, gap_min),
        "baseline": baseline_metrics(issue, statuses),
    }


# ── 출력 ────────────────────────────────────────────────────────────────

def _pct(x):
    return "N/A" if x is None else f"{x * 100:.0f}%"


def _v(x):
    return "N/A" if x is None else str(x)


def _render_changes(pc: dict) -> str:
    head = (f"등록 {pc['registers']} · 갱신 {pc['updates']} · 갱신 때 태스크 추가 "
            f"{pc['tasks_added_after_register']} · 제거 {pc['tasks_removed']} · 대상 변경 "
            f"{pc['target_changes']}(확장 {pc['target_expansions']})"
            + (f" · 전후 비교 불가 {pc['unreadable']}" if pc["unreadable"] else ""))
    rows = []
    for e in pc["events"]:
        if e["kind"] != "갱신":
            continue
        d = e["diff"]
        at = e["at"].strftime("%m-%d %H:%MZ") if e["at"] else "?"
        if d is None:
            what = "전후 비교 불가"
        else:
            bits = ([f"추가 {','.join(d['added'])}"] if d["added"] else []) \
                + ([f"제거 {','.join(d['removed'])}"] if d["removed"] else []) \
                + [f"{t['task']} 대상 {t['change']}"
                   + (f" +{','.join(t['added'])}" if t["added"] else "")
                   + (f" -{','.join(t['removed'])}" if t["removed"] else "") for t in d["targets"]] \
                + [f"{f}:{','.join(ids)}" for f, ids in d["fields"].items() if f != "target"]
            what = " · ".join(bits) or "태스크 정의 변화 없음"
        rows.append(f"\n    {at} {what}" + (f" — 사유: {e['why'][:80]}" if e["why"] else ""))
    return head + "".join(rows)


def render_issue(m: dict) -> str:
    ev, sc, rs, b = m["evidence"], m["scope"], m["resume"], m["baseline"]
    lines = [f"#{m['id']} {m['subject'][:60]}",
             f"  플랜          {'v' + str(m['plan_version']) if m['has_plan'] else '없음'}"
             + (f" (형식 오류: {m['plan_error']})" if m["plan_error"] else ""),
             # [DOC] 「상태별」 줄 — 태스크 상태별 개수를 한 줄로 낸다. 출력 문자열은 바꾸지 않는다.
             # [PSEUDO] 바로 아래 줄 맨 앞의 문자열 조각 f"  상태별        " 은 자리 표시자가 없는 f-string 이라
             # [PSEUDO] pyflakes 가 경고한다(F541). 앞의 f 접두만 지워 일반 문자열로 바꾼다 — 그 외 변경 금지.
             f"  상태별        " + (" · ".join(f"{k} {v}" for k, v in m["tasks_by_state"].items()) or "—"),
             f"  전이/등록     전이 {m['transitions']} · 플랜 등록·갱신 노트 {m['plan_sets']}",
             "  플랜 갱신     " + _render_changes(m["plan_changes"]),
             f"  차단/되돌림   차단 {m['blocked_total']} · 되돌림 {m['reopen_total']}",
             f"  태스크 리드   중앙값 {_v(m['task_lead_min_median'])}분"]
    for tid, v in m["tasks"].items():
        lines.append(f"    {tid:<6} 리드 {_v(v['lead_min'])}분 · 차단 {v['blocked']} · 되돌림 {v['reopen']}")
    lines += [
        f"  근거 충실도   완료 전이 {ev['done_transitions']} · 해시 {ev['with_hash']}({_pct(ev['hash_ratio'])})"
        f" · 검사수치 {ev['with_test']}({_pct(ev['test_ratio'])}) · 둘 중 하나 {_pct(ev['either_ratio'])}",
        f"  범위 이탈[{APPROX}] 커밋 {len(sc['commits'])} · 파일 {sc['files']} · 대상 밖 "
        f"{len(sc['outside'])}({_pct(sc['outside_ratio'])}) · 대상 토큰 {len(sc['target_tokens'])}",
        f"    제목 언급 커밋만: 커밋 {sc['primary_commits']} · 파일 {sc['primary_files']} · 대상 밖 "
        f"{len(sc['primary_outside'])}({_pct(sc['primary_outside_ratio'])})",
        f"    작업 커밋만(종류(#N…)): 커밋 {len(sc['work_commits'])} · 파일 {sc['work_files']} · 대상 밖 "
        f"{len(sc['work_outside'])}({_pct(sc['work_outside_ratio'])})",
    ]
    for f in sc["outside"][:15]:
        lines.append(f"    밖: {f}")
    if len(sc["outside"]) > 15:
        lines.append(f"    … 외 {len(sc['outside']) - 15}")
    rj = m["rejections"]
    lines.append("  거절          " + ("기록 없음(파일 없음·읽기 실패)" if rj is None else
                                     f"{rj['total']}" + (f" — {rj['by_kind']}" if rj["by_kind"] else "")))
    lines.append(f"  재개[{APPROX}]    공백≥{rs['gap_min']:g}분 {rs['gaps']} · 셀 수 있는 것 "
                 f"{rs['countable']} · 이어 잡음 {rs['continued']} ({_pct(rs['ratio'])}) · 유휴 공백 {rs['idle_gaps']}")
    lines.append(f"  기준선 지표   리드 {_v(b['lead_hours'])}h · 착수 리드 {_v(b.get('start_lead_hours'))}h"
                 + (f"({b['start_source']})" if b.get("start_source") else "(측정 불가)")
                 + f" · 재개 {b['reopen']} · 해결 체류 "
                 f"{b['resolved_hours']}h · 종결 노트 근거 "
                 + ("N/A" if b["close_note"] is None else
                    f"해시 {'O' if b['close_note']['hash'] else 'X'} · 검사 {'O' if b['close_note']['test'] else 'X'}"))
    return "\n".join(lines)


def render_baseline(rows: list[dict], agg: dict, title: str) -> str:
    lines = [title, f"  {'id':>5} {'상태':<4} {'리드h':>8} {'착수h':>7} {'재개':>4} {'해결h':>7} 종결근거(해시/검사)  제목"]
    for r in rows:
        cn = r["close_note"]
        ev = "N/A" if cn is None else f"{'O' if cn['hash'] else 'X'}/{'O' if cn['test'] else 'X'}"
        lines.append(f"  {r['id']:>5} {r['status']:<4} {_v(r['lead_hours']):>8} "
                     f"{_v(r.get('start_lead_hours')):>7} {r['reopen']:>4} "
                     f"{r['resolved_hours']:>7} {ev:<19} {r['subject'][:40]}")
    lines.append(render_aggregate(agg))
    lines.append("  플랜 전용 지표(기준선 N/A): " + " · ".join(PLAN_ONLY))
    return "\n".join(lines)


def render_aggregate(a: dict, label: str = "집계") -> str:
    return (f"  {label}: 이슈 {a['issues']} · 종결 {a['closed']} · 리드 중앙 {_v(a['lead_hours_median'])}h"
            f" / 평균 {_v(a['lead_hours_mean'])}h · 착수 리드 중앙 {_v(a.get('start_lead_hours_median'))}h"
            f" / 평균 {_v(a.get('start_lead_hours_mean'))}h (측정 {a.get('start_measured', 0)}/{a['closed']})"
            f" · 재개 이슈 {a['reopened_issues']}(총 {a['reopen_total']})"
            f" · 해결 체류 중앙 {_v(a['resolved_hours_median'])}h · 종결 노트 근거 해시 "
            f"{_pct(a['close_note_hash_share'])} · 검사 {_pct(a['close_note_test_share'])}"
            f" · 하나 이상 {_pct(a['close_note_either_share'])} (n={a['close_notes']})")


# ── CLI ─────────────────────────────────────────────────────────────────

def _load_events(path):
    from master import plan_events as PE
    try:
        p = Path(path) if path else PE.default_path()
    except Exception as e:                            # noqa: BLE001
        print(f"[plan_metrics] 거절 기록 위치를 못 풀었다: {e}", file=sys.stderr)
        return None, None
    return p, (PE.read(p) if p.is_file() else None)


def collect_issues(ids, *, gap_min, events_path=None, get=http_json, git=git_run) -> list[dict]:
    statuses = fetch_statuses(get=get)
    _p, events = _load_events(events_path)
    out = []
    for iid in ids:
        issue = fetch_issue(iid, get=get)
        ev = None if events is None else [e for e in events if str(e.get("issue_id")) == str(iid)]
        out.append(issue_metrics(issue, commits=issue_commits(iid, git=git), events=ev,
                                 statuses=statuses, gap_min=gap_min))
    return out


def collect_baseline(version_id, *, get=http_json) -> list[dict]:
    statuses = fetch_statuses(get=get)
    return [baseline_metrics(fetch_issue(i, get=get), statuses)
            for i in fetch_version_issue_ids(version_id, get=get)]


def main(argv=None, *, get=http_json, git=git_run, out=sys.stdout) -> int:
    ap = argparse.ArgumentParser(prog="python -m master.plan_metrics", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("issue")
    a.add_argument("ids", nargs="+", type=int)
    b = sub.add_parser("baseline")
    b.add_argument("--version-id", type=int, required=True)
    c = sub.add_parser("compare")
    c.add_argument("--version-id", type=int, required=True)
    c.add_argument("--issues", nargs="+", type=int, required=True)
    for p in (a, b, c):
        p.add_argument("--json", action="store_true")
    for p in (a, c):
        p.add_argument("--gap-min", type=float, default=30)
        p.add_argument("--events", default="", help="plan_events.jsonl (기본: 레지스트리의 AXCluster 트윈)")
    args = ap.parse_args(argv)

    if args.cmd == "issue":
        ms = collect_issues(args.ids, gap_min=args.gap_min, events_path=args.events or None,
                            get=get, git=git)
        if args.json:
            out.write(json.dumps(ms, ensure_ascii=False, indent=2, default=str) + "\n")
        else:
            out.write("\n\n".join(render_issue(m) for m in ms) + "\n")
        return 0
    rows = collect_baseline(args.version_id, get=get)
    agg = aggregate(rows)
    if args.cmd == "baseline":
        if args.json:
            out.write(json.dumps({"version_id": args.version_id, "issues": rows, "aggregate": agg,
                                  "na_for_baseline": list(PLAN_ONLY)}, ensure_ascii=False,
                                 indent=2) + "\n")
        else:
            out.write(render_baseline(rows, agg, f"기준선 — 버전 {args.version_id} (플랜 없음)") + "\n")
        return 0
    ms = collect_issues(args.issues, gap_min=args.gap_min, events_path=args.events or None,
                        get=get, git=git)
    plan_agg = aggregate([m["baseline"] for m in ms])
    if args.json:
        out.write(json.dumps({"baseline": {"version_id": args.version_id, "aggregate": agg},
                              "plan": {"issues": [m["id"] for m in ms], "aggregate": plan_agg,
                                       "plan_only": ms},
                              "na_for_baseline": list(PLAN_ONLY)},
                             ensure_ascii=False, indent=2, default=str) + "\n")
    else:
        out.write(f"비교 — 같은 지표만 나란히 (기준선 = 버전 {args.version_id})\n")
        out.write(render_aggregate(agg, "기준선") + "\n")
        out.write(render_aggregate(plan_agg, "플랜  ") + "\n")
        out.write("  플랜 전용 지표(기준선 N/A): " + " · ".join(PLAN_ONLY) + "\n\n")
        out.write("\n\n".join(render_issue(m) for m in ms) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
