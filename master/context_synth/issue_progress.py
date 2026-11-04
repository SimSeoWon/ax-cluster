"""일감 마감 추적 ↔ 리뷰 큐 동기화 · 해시별 진행 노트 (`#884` T3).

사용자 결정(2026-11-04): 작업 세션이 마감 해시를 등록하고 떠나면(T1), 색인기가 그 커밋 리뷰를
우선순위 10 으로 넣는다(T2). 이 모듈은 **리뷰 큐 소비자 쪽**에서 추적 기록을 큐에 맞추고, 해시의
커밋 리뷰가 끝날 때마다(done · abandoned — *"abandoned 도 끝난 것으로 보고 노트에 쓴다"* · skipped 도
적는다) 그 일감에 **짧은 진행 노트**를 남긴다. 종합 리뷰(T4)는 여기서 하지 않는다.

    sync_issue_tracks(paths, *, noter=None, watermark=None, logf=None) -> dict

`review_runner.main` 이 소비자 잠금 안에서 **drain 앞**(`retry_range_notes` 바로 뒤)과 **drain 뒤**에
한 번씩 부른다 — 이번 회차에 끝난 리뷰의 노트가 같은 회차에 나간다. LLM 0.

## 한 라운드에서 하는 일 (`issue_track.open_rounds` 전부)

    ① 큐 → 해시   waiting·queued 해시의 `commit:<sha>` 항목이
                     done        → done (R 번호 · 지적 수 — fix_index)
                     abandoned   → abandoned (why = last_why)
                     pending·running·failed 이고 해시가 waiting → `issue_link._apply`(우선순위 10 · queued)
    ② 워터마크    waiting 이고 큐 항목이 없는 해시가 색인 워터마크(`index.last_indexed_commit`)의
                   조상이면 → skipped("색인 워터마크 통과 · 리뷰 미등재").
                   미러(`paths.repo`)에 그 커밋이 아직 없으면 그대로 waiting(미러 지연, `#880`)
    ③ 노트        종결됐는데 noted=False 인 해시를 **라운드당 노트 하나**로 묶어 남긴다.
                   성공하면 각 해시 noted=True · 실패(`[주의]` 로 시작하는 결과 또는 예외)면 그대로 둬서
                   다음 회차가 다시 한다

[중요] 노트는 자동 경로로 세션이 읽는 글이다 — **사실만 적고 명령형을 쓰지 않는다**
(`~/CLAUDE.md` 「자동 경로로 LLM 에게 보내는 글에 명령형을 쓰지 않는다」).
🔴 [중요] 기본 noter(실 Redmine)는 **레지스트리에 등록된 트윈 루트에서만** 쓴다 — `review_runner.
notify_range` 와 같은 가드(2026-11-03 임시 디렉토리 테스트가 실제 #879 에 노트를 남겼다).
[중요] 소비자를 깨지 않는다 — 추적 파일이 깨졌거나(`IssueTrackError`) 라운드 하나가 예외를 내도
크게 찍고 다음 라운드로 간다. 추적 파일이 없으면 잠금 파일도 만들지 않고 돌아간다.
[주의] 추적에 없는 큐 항목은 건드리지 않는다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import issue_link as il
from . import issue_track as it
from . import review_queue as rq

WATERMARK_SKIP_WHY = "색인 워터마크 통과 · 리뷰 미등재"
_SEV = (("high", "높음"), ("mid", "중간"), ("low", "낮음"))
_WHY_MAX = 100


def _default_noter(issue_id, *, notes: str) -> str:
    from .. import redmine                                         # noqa: PLC0415
    return redmine.update_issue(int(issue_id), notes=notes)


def _git(repo, *args) -> int:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              text=True, timeout=30).returncode
    except (OSError, subprocess.SubprocessError):
        return -1


def _has_commit(repo, sha: str) -> bool:
    return bool(sha) and _git(repo, "cat-file", "-e", f"{sha}^{{commit}}") == 0


def _watermark_of(paths, logf) -> str:
    """트윈 `config.yaml` 의 `index.last_indexed_commit` — 못 읽으면 빈 값(건너뜀 판정 안 함)."""
    try:
        from ..projects.config import ProjectConfig                # noqa: PLC0415
        cfg = getattr(paths, "config", None) or Path(paths.root) / "config.yaml"
        if not Path(cfg).is_file():
            return ""
        return (ProjectConfig.load(Path(cfg)).last_indexed_commit or "").strip().lower()
    except Exception as e:                                          # noqa: BLE001
        logf(f"[issue-progress] [주의] 색인 워터마크를 읽지 못했다 — 워터마크 판정 생략: "
             f"{type(e).__name__}: {e}")
        return ""


def _short(text, limit: int = _WHY_MAX) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _done_note(item: dict) -> str:
    for h in reversed(item.get("history") or []):
        if h.get("result") == "done":
            return str(h.get("note") or "")
    return ""


def _review_facts(root, sha: str) -> tuple:
    """(R 번호, 지적 수|None, 심각도 사전). 번호가 없으면 한 번 훑고(`sweep`, 멱등) 다시 찾는다."""
    from . import fix_index as fx                                   # noqa: PLC0415
    serial = fx.serial_for_commit(root, sha)
    if not serial:
        fx.sweep(root)
        serial = fx.serial_for_commit(root, sha)
    if not serial:
        return "", None, {}
    doc = fx.get_doc(root, serial)
    if not doc.get("ok"):
        return serial, None, {}
    return serial, len(doc.get("items_detail") or []), dict(doc.get("severity") or {})


def _sync_round(paths, rnd: dict, by_key: dict, wm: str, counts: dict, log) -> None:
    """①② — 한 라운드의 해시를 큐·워터마크에 맞춘다. 예외는 호출부가 잡는다."""
    root = paths.root
    n, rnum = rnd["issue_id"], rnd["round"]
    tag = f"#{n} 회차 {rnum}"
    for h in rnd["hashes"]:
        sha, cur = h["sha"], h["state"]
        if cur in it.HASH_TERMINAL:
            continue
        item = by_key.get(sha)
        if item is not None:
            st = item.get("state")
            if st == "done":
                serial, findings, _ = _review_facts(root, sha)
                why = "" if serial else _short(_done_note(item)) or "리뷰 번호 없음"
                res = it.set_hash(root, n, sha, state="done", serial=serial, findings=findings,
                                  why=why, round=rnum, logf=log)
                counts["done" if res.get("ok") else "errors"] += 1
                log(f"[issue-progress] {tag} {sha[:12]} 큐 done → done"
                    + (f" · {serial} · 지적 {findings}" if serial else f" · {why}")
                    + ("" if res.get("ok") else f" — 거절 {res.get('reason')}: {res.get('why')}"))
            elif st == "abandoned":
                why = _short(item.get("last_why")) or "사유 미기록"
                res = it.set_hash(root, n, sha, state="abandoned", why=why, round=rnum, logf=log)
                counts["abandoned" if res.get("ok") else "errors"] += 1
                log(f"[issue-progress] {tag} {sha[:12]} 큐 abandoned → abandoned · {why}"
                    + ("" if res.get("ok") else f" — 거절 {res.get('reason')}: {res.get('why')}"))
            elif cur == "waiting":
                # T2 와 같은 연결(우선순위 10 · meta · queued) — 코드를 복제하지 않고 그 함수를 부른다
                res = il._apply(root, n, rnum, sha, item, log)
                counts["queued" if res.get("ok") else "errors"] += 1
                log(f"[issue-progress] {tag} {sha[:12]} 큐 {st} → 연결"
                    + (f" (우선순위 {res.get('priority')})" if res.get("ok")
                       else f" 실패 {res.get('reason')}: {res.get('why')}"))
            else:
                counts["unchanged"] += 1      # queued + 큐 진행 중 — 할 일 없다
            continue
        # ② 큐 항목 없음
        if cur == "queued":
            counts["unchanged"] += 1
            log(f"[issue-progress] [주의] {tag} {sha[:12]} queued 인데 큐에 항목이 없다 — 그대로 둔다")
            continue
        if not wm:
            counts["unchanged"] += 1
            continue
        repo = paths.repo
        if not _has_commit(repo, sha):
            counts["unchanged"] += 1
            log(f"[issue-progress] {tag} {sha[:12]} 미러에 아직 없다 — waiting 유지(미러 지연)")
            continue
        if not _has_commit(repo, wm):
            counts["unchanged"] += 1
            log(f"[issue-progress] [주의] {tag} 워터마크 {wm[:12]} 가 미러에 없다 — 판정 생략")
            continue
        if _git(repo, "merge-base", "--is-ancestor", sha, wm) == 0:
            res = it.set_hash(root, n, sha, state="skipped", why=WATERMARK_SKIP_WHY,
                              round=rnum, logf=log)
            counts["skipped" if res.get("ok") else "errors"] += 1
            log(f"[issue-progress] {tag} {sha[:12]} 워터마크 {wm[:12]} 통과 · 큐 항목 없음 → skipped"
                + ("" if res.get("ok") else f" — 거절 {res.get('reason')}: {res.get('why')}"))
        else:
            counts["unchanged"] += 1


def note_text(root, rnd: dict, fresh: list) -> str:
    """라운드의 진행 노트 — 머리줄(끝난 수·남은 수) + 새로 종결된 해시 한 줄씩. 사실만 적는다."""
    total = len(rnd["hashes"])
    left = len(it.pending_hashes(rnd))
    lines = [f"해시 리뷰 진행 (회차 {rnd['round']}) — {total - left}/{total} 끝남 · 남은 {left}"]
    for h in fresh:
        head = f"- `{h['sha'][:12]}`"
        st = h["state"]
        if st == "done":
            serial, findings = h.get("serial") or "", h.get("findings")
            sev = {}
            if serial:
                try:
                    _s, f2, sev = _review_facts(root, h["sha"])
                    findings = f2 if f2 is not None else findings
                except Exception:                                   # noqa: BLE001 — 건수는 보조 정보다
                    sev = {}
            if serial:
                body = f" {serial}"
                if findings is not None:
                    body += f" · 지적 {findings}"
                    if sev:
                        body += " (" + "·".join(f"{lab} {sev.get(k, 0)}" for k, lab in _SEV) + ")"
                lines.append(head + body)
            else:
                lines.append(head + f" 완료 — {_short(h.get('why')) or '리뷰 번호 없음'}")
        elif st == "abandoned":
            lines.append(head + f" 포기 — {_short(h.get('why')) or '사유 미기록'}")
        else:
            lines.append(head + f" 생략 — {_short(h.get('why')) or '사유 미기록'}")
    return "\n".join(lines)


def _note_round(paths, rnd: dict, noter, counts: dict, log) -> None:
    """③ — 종결·미기록 해시를 노트 하나로. 실패면 noted 를 건드리지 않는다."""
    fresh = [h for h in rnd["hashes"] if h["state"] in it.HASH_TERMINAL and not h.get("noted")]
    if not fresh:
        return
    n, rnum = rnd["issue_id"], rnd["round"]
    tag = f"#{n} 회차 {rnum}"
    if noter is None:
        counts["note_skipped"] += 1
        log(f"[issue-progress] [주의] {tag} 진행 노트 생략 — 등록된 트윈 루트가 아니다(대역 미주입) · "
            f"미기록 {len(fresh)}건 유지")
        return
    try:
        text = note_text(paths.root, rnd, fresh)
        out = str(noter(n, notes=text))
    except Exception as e:                                          # noqa: BLE001
        out = f"[주의] {type(e).__name__}: {e}"
    if out.startswith("[주의]"):
        counts["note_failed"] += 1
        log(f"[issue-progress] [중요] {tag} 진행 노트 실패 — 다음 회차 재시도({len(fresh)}건): {out[:160]}")
        return
    counts["noted_notes"] += 1
    for h in fresh:
        res = it.mark_hash_noted(paths.root, n, h["sha"], True, round=rnum, logf=log)
        if res.get("ok"):
            counts["noted_hashes"] += 1
        else:
            counts["errors"] += 1
            log(f"[issue-progress] [중요] {tag} {h['sha'][:12]} 노트는 남았는데 noted 표시 실패 — "
                f"다음 회차에 중복될 수 있다: {res.get('reason')}: {res.get('why')}")
    log(f"[issue-progress] {tag} 진행 노트 — 해시 {len(fresh)}건 ({out[:60]})")


def sync_issue_tracks(paths, *, noter=None, watermark=None, logf=None) -> dict:
    """열린 마감 라운드를 리뷰 큐·색인 워터마크에 맞추고 진행 노트를 남긴다. 예외를 올리지 않는다.

    `noter(issue_id, notes=...) -> str` — 생략하면 실 Redmine(등록된 트윈 루트에서만).
    `watermark` — 생략하면 트윈 `config.yaml` 의 `index.last_indexed_commit`.
    반환: 건수 사전(`rounds`·`done`·`abandoned`·`skipped`·`queued`·`unchanged`·`noted_notes`·
    `noted_hashes`·`note_failed`·`note_skipped`·`errors`) + `ok`.
    """
    log = logf or print
    counts = {k: 0 for k in ("rounds", "done", "abandoned", "skipped", "queued", "unchanged",
                             "noted_notes", "noted_hashes", "note_failed", "note_skipped", "errors")}
    root = paths.root
    try:
        if not it.state_path(root).exists():
            return {"ok": True, **counts}
        rounds = it.open_rounds(root)
        if not rounds:
            return {"ok": True, **counts}
        by_key = {}
        for x in rq.items(root):
            if x.get("kind") == "commit":
                by_key[str(x.get("key") or "").lower()] = x
        wm = (str(watermark).strip().lower() if watermark is not None else _watermark_of(paths, log))
        if noter is None:
            from . import review_runner as rr                       # noqa: PLC0415
            noter = _default_noter if rr._is_registered_root(paths) else None
    except it.IssueTrackError as e:
        log(f"[issue-progress] [중요] 일감 마감 추적 기록을 믿을 수 없다 — 동기화 건너뜀(소비자는 계속): {e}")
        return {"ok": False, "reason": "track_corrupt", "why": str(e), **counts}
    except Exception as e:                                          # noqa: BLE001
        log(f"[issue-progress] [중요] 동기화 준비 실패 — 건너뜀(소비자는 계속): {type(e).__name__}: {e}")
        return {"ok": False, "reason": "error", "why": f"{type(e).__name__}: {e}", **counts}

    for rnd in rounds:
        counts["rounds"] += 1
        n, rnum = rnd.get("issue_id"), rnd.get("round")
        try:
            _sync_round(paths, rnd, by_key, wm, counts, log)
            fresh = it.rounds(root, n)
            cur = next((r for r in fresh if r["round"] == rnum), None)
            if cur is not None:
                _note_round(paths, cur, noter, counts, log)
        except Exception as e:                                      # noqa: BLE001 — 다른 라운드는 계속
            counts["errors"] += 1
            sev = "[중요]" if isinstance(e, it.IssueTrackError) else "[주의]"
            log(f"[issue-progress] {sev} #{n} 회차 {rnum} 동기화 실패 — 다음 라운드로: "
                f"{type(e).__name__}: {e}")
    log(f"[issue-progress] {Path(str(root)).name} 라운드 {counts['rounds']} — done {counts['done']} · "
        f"포기 {counts['abandoned']} · 생략 {counts['skipped']} · 연결 {counts['queued']} · "
        f"노트 {counts['noted_notes']}(해시 {counts['noted_hashes']}) · 노트 실패 {counts['note_failed']} · "
        f"오류 {counts['errors']}")
    return {"ok": counts["errors"] == 0 and counts["note_failed"] == 0, **counts}
