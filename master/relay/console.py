"""콘솔 (`#942` T5) — 일감 선택 → 에이전트 선택·교체 → 대화 중계와 미러링.

    /issue    일감을 고른다(작업 세션을 열거나 이어 간다)
    /agent    에이전트를 고른다 — 작업 중간에 바꿀 수 있다
    /status   지금 세션·에이전트·로그 위치
    /reset    지금 에이전트의 세션만 비운다(다음 입력은 새 세션으로 간다)
    /close    마무리 — 일감이 「완료」이고 보고서가 있을 때만 로그를 보관하고 세 세션을 비운다
    /help · /quit
    그 밖의 입력은 지금 에이전트에게 전달한다.

[중요] **전달문에는 사실만 싣는다** — 「세션 기록 파일은 어디고, 몇 번부터가 이 에이전트를 거치지 않은
대화인가」. 무엇을 할지는 싣지 않는다(자동 경로의 명령형은 주입으로 거부된다 — 리포트 60).
[중요] 실패하면 다시 시도하지 않는다 — 사유를 보여 주고 로그에 남긴 뒤 사용자의 다음 입력을 기다린다.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime

from master.relay import agents, store

AGENTS = store.AGENTS
MIRROR_CAP = 600            # 화면에 내는 도구 결과 최대 글자 수 — 로그에는 전부 남는다
LOGGED = ("system", "agent_text", "tool_call", "tool_result", "result", "error", "raw")
CONVERSATION = ("user", "agent_text", "tool_call", "tool_result", "result", "error")
QUOTA_MAX_AGE = 15 * 60
QUOTA_DEFAULT_THRESHOLD = 20.0
_QUOTA_LABELS = {"five_hour": "5시간", "seven_day": "7일"}


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def parse_quota_threshold(value) -> float:
    """환경변수·CLI의 잔여율 임계값. 범위를 벗어나면 거절한다."""
    try:
        threshold = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("한도 임계값은 0~100 사이 유한 숫자여야 한다") from None
    if isinstance(value, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("한도 임계값은 0~100 사이 유한 숫자여야 한다")
    return threshold


def quota_windows(snapshot, now=None) -> dict:
    """관측 15분 이내·리셋 전인 유효 창만 돌려준다. 미래 관측은 믿지 않는다."""
    if not isinstance(snapshot, dict):
        return {}
    current = _finite(time.time() if now is None else now)
    observed = _finite(snapshot.get("observed_at"))
    if (current is None or observed is None or observed <= 0
            or not 0 <= current - observed <= QUOTA_MAX_AGE):
        return {}
    windows = snapshot.get("windows")
    if not isinstance(windows, dict):
        return {}
    valid = {}
    for key in _QUOTA_LABELS:
        raw = windows.get(key)
        if not isinstance(raw, dict):
            continue
        remaining, reset = _finite(raw.get("remaining_pct")), _finite(raw.get("resets_at"))
        if remaining is None or not 0 <= remaining <= 100 or reset is None or reset <= current:
            continue
        try:
            datetime.fromtimestamp(reset)
        except (ValueError, OverflowError, OSError):
            continue
        valid[key] = {"remaining_pct": remaining, "resets_at": reset}
    return valid


def quota_line(agent: str, snapshot, now=None) -> str:
    windows = quota_windows(snapshot, now=now) if agent in ("claude", "codex") else {}
    if not windows:
        return f"[relay] {agent} 잔여 한도 미확인"
    parts = []
    for key, value in windows.items():
        reset = datetime.fromtimestamp(value["resets_at"]).astimezone().strftime("%m-%d %H:%M %Z")
        parts.append(f"{_QUOTA_LABELS[key]} {value['remaining_pct']:g}% (리셋 {reset})")
    return f"[relay] {agent} 잔여 한도 · " + " · ".join(parts)


def _short(s: str, cap: int) -> str:
    s = s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)
    s = s.strip()
    return s if len(s) <= cap else s[:cap] + f" …(+{len(s) - cap}자)"


def header(issue: int, subject: str, log: str, seen: int, last: int, first_time: bool, unseen: int = -1) -> str:
    """전달문 앞에 붙는 사실 문장. `last` = 이번 사용자 입력 바로 앞 기록의 순번,
    `unseen` = 그 사이 이 에이전트를 거치지 않은 **대화 기록** 수(세션 시작·교체 표시는 세지 않는다)."""
    lines = [f"[relay] 작업 세션: Redmine 일감 #{issue}" + (f" «{subject}»" if subject else "") + "."]
    if unseen < 0:
        unseen = max(0, last - seen)
    if unseen > 0:
        lines.append(f"[relay] 세션 기록 파일: {log} (한 줄에 JSON 하나, seq 가 순번).")
        if first_time:
            lines.append(f"[relay] 이 에이전트는 이 작업 세션에 처음 참여한다. 1~{last}번 기록이 앞선 대화다.")
        else:
            lines.append(f"[relay] 이 에이전트가 마지막으로 본 순번은 {seen}번이다. "
                         f"{seen + 1}~{last}번 기록은 이 에이전트를 거치지 않은 대화다.")
    return "\n".join(lines)


class Relay:
    def __init__(self, *, root, cwd, boundary, out=print, inp=input, runner=agents.run,
                 quota_threshold=None):
        self.root, self.cwd, self.boundary = root, str(cwd), boundary
        self.out, self.inp, self.runner = out, inp, runner
        self.issue = 0
        self.subject = ""
        self.agent = ""
        setting = (os.environ.get("AX_RELAY_QUOTA_THRESHOLD", str(QUOTA_DEFAULT_THRESHOLD))
                   if quota_threshold is None else quota_threshold)
        try:
            self.quota_threshold = parse_quota_threshold(setting)
        except ValueError:
            self.quota_threshold = QUOTA_DEFAULT_THRESHOLD
            self.out("[relay] 한도 임계값이 유효하지 않아 기본 20%를 사용한다")
        boundary.dbg = self.dbg         # 경계 판정도 같은 디버그 로그에 남긴다

    def _quota_notice(self, agent: str, snapshot, previous, now=None) -> dict:
        self.out(quota_line(agent, snapshot, now=now))
        warnings = dict(previous) if isinstance(previous, dict) else {}
        windows = quota_windows(snapshot, now=now) if agent in ("claude", "codex") else {}
        for key, value in windows.items():
            reset, remaining = value["resets_at"], value["remaining_pct"]
            if remaining > self.quota_threshold:
                warnings.pop(key, None)
            elif warnings.get(key) != reset:
                warnings[key] = reset
                self.out(f"[relay] {agent} {_QUOTA_LABELS[key]} 잔여 {remaining:g}% "
                         f"(임계 {self.quota_threshold:g}% 이하). 인수인계서 갱신과 /agent 교대를 고려하세요")
        return warnings

    # ── 로그 ──
    def dbg(self, where: str, msg: str) -> None:
        store.debug(self.root, self.issue or None, where, msg)

    def _raw_sink(self, agent: str):
        p = store.session_dir(self.root, self.issue) / f"raw-{agent}.jsonl"
        def sink(line: str) -> None:
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return sink

    # ── 일감 ──
    def choose_issue(self) -> bool:
        c = self.boundary.candidates()
        if not c["ok"]:
            self.out(f"[relay] {c['why']}")
            self.dbg("console.issue", f"후보 조회 실패 — {c['why']}")
            return False
        open_sessions = store.sessions(self.root)
        rows = sorted(c["issues"], key=lambda r: (not r["active"], r["id"] not in open_sessions, -(r["id"] or 0)))
        self.out("[relay] 일감을 고른다 — 번호를 입력한다(빈 줄 = 취소)")
        for r in rows:
            mark = ("작업 중 " if r["active"] else "") + ("세션 있음 " if r["id"] in open_sessions else "")
            self.out(f"  #{r['id']:<5} {r['status']:<4} {mark}{r['subject']}")
        if c.get("why"):
            self.out(f"[relay] 주의: {c['why']}")
        ans = self.inp("일감 번호> ").strip().lstrip("#")
        if not ans:
            return False
        if not ans.isdigit():
            self.out(f"[relay] 번호가 아니다: {ans}")
            return False
        return self.open_issue(int(ans))

    def open_issue(self, issue_id: int) -> bool:
        r = self.boundary.may_open(issue_id)
        if not r["ok"]:
            self.out(f"[relay] #{issue_id} 을 열 수 없다 — {r['why']}")
            self.dbg("console.issue", f"#{issue_id} 열기 거절 — {r['why']}")
            return False
        s = store.open_session(self.root, issue_id)
        self.issue, self.subject = issue_id, r.get("subject", "")
        self.agent = s["state"].get("current", "")
        self.out(f"[relay] 작업 세션 #{issue_id} {'이어감' if s['resumed'] else '시작'} — {self.subject}")
        self.out(f"[relay] 기록 {s['log']} · 디버그 {s['debug']}")
        if self.agent:
            self.out(f"[relay] 지금 에이전트: {self.agent}")
        self.dbg("console.issue", f"#{issue_id} 열림 — 이어감={s['resumed']} 현재 에이전트={self.agent or '(없음)'} cwd={self.cwd}")
        return True

    # ── 에이전트 ──
    def choose_agent(self) -> bool:
        st = store.state(self.root, self.issue)
        self.out("[relay] 에이전트를 고른다 — 번호나 이름(빈 줄 = 그대로)")
        for i, a in enumerate(AGENTS, 1):
            info = st["agents"][a]
            cur = " ← 지금" if a == self.agent else ""
            self.out(f"  {i}) {a:<6} 이 세션에서 {info['turns']}회{cur}")
        ans = self.inp("에이전트> ").strip().lower()
        if not ans:
            return bool(self.agent)
        pick = AGENTS[int(ans) - 1] if ans.isdigit() and 1 <= int(ans) <= len(AGENTS) else ans
        if pick not in AGENTS:
            self.out(f"[relay] 모르는 에이전트: {ans}")
            return False
        return self.set_agent(pick)

    def set_agent(self, agent: str) -> bool:
        if agent == self.agent:
            return True
        prev = self.agent
        store.update_agent(self.root, self.issue, agent, current=True)
        self.agent = agent
        store.append(self.root, self.issue, kind="switch", agent=agent,
                     text=f"에이전트 {prev or '(없음)'} → {agent}")
        self.out(f"[relay] 에이전트 {prev or '(없음)'} → {agent}")
        self.dbg("console.agent", f"교체 {prev or '(없음)'} → {agent}")
        return True

    def reset_agent(self) -> None:
        if not self.agent:
            self.out("[relay] 고른 에이전트가 없다")
            return
        store.update_agent(self.root, self.issue, self.agent, session="", seen=0)
        store.append(self.root, self.issue, kind="switch", agent=self.agent, text=f"{self.agent} 세션 비움")
        self.out(f"[relay] {self.agent} 세션을 비웠다 — 다음 입력은 새 세션으로 간다")
        self.dbg("console.agent", f"{self.agent} 세션 비움(사용자 요청)")

    # ── 대화 ──
    def _mirror(self, agent: str, ev: dict) -> None:
        k, text = ev["kind"], ev["text"]
        if k == "agent_text":
            self.out(f"[{agent}] {text}")
        elif k == "tool_call":
            inp = ev["data"].get("input") if isinstance(ev["data"], dict) else None
            self.out(f"[{agent}] -> 도구 {_short(text, 200)}" + (f" {_short(inp, 300)}" if inp else ""))
        elif k == "tool_result":
            self.out(f"[{agent}] <- 결과 {_short(text, MIRROR_CAP)}")
        elif k == "error":
            self.out(f"[{agent}] !! 실패 {_short(text, MIRROR_CAP)}")
        elif k == "raw":
            self.out(f"[{agent}] ?? 모르는 이벤트 {text} (기록에 원문)")

    def send(self, text: str):
        agent = self.agent
        st = store.state(self.root, self.issue)["agents"][agent]
        last = store.last_seq(self.root, self.issue)
        unseen = sum(1 for r in store.read(self.root, self.issue, after=st["seen"])
                     if r.get("kind") in CONVERSATION)
        head = header(self.issue, self.subject, str(store.log_path(self.root, self.issue)),
                      st["seen"], last, first_time=not st["session"], unseen=unseen)
        store.append(self.root, self.issue, kind="user", agent=agent, text=text)
        prompt = head + "\n\n" + text
        self.dbg("console.send", f"{agent} 로 전달 — 입력 {len(text)}자 · 본 순번 {st['seen']} · 직전 순번 {last} · "
                                 f"안 본 대화 기록 {unseen}건 · 세션 {st['session'] or '(새로)'}")

        def on_event(ev: dict) -> None:
            if ev["kind"] in LOGGED:
                store.append(self.root, self.issue, kind=ev["kind"], agent=agent, text=ev["text"],
                             data=ev["data"] or None)
            self._mirror(agent, ev)

        res = self.runner(agent, prompt, cwd=self.cwd, session=st["session"], on_event=on_event,
                          dbg=self.dbg, raw_sink=self._raw_sink(agent))
        if res.interrupted:
            store.append(self.root, self.issue, kind="error", agent=agent, text="사용자가 중단했다(Ctrl-C)")
            self.out(f"[relay] {agent} 중단됨")
        elif not res.ok:
            store.append(self.root, self.issue, kind="error", agent=agent, text=res.error,
                         data={"rc": res.rc})
            self.out(f"[relay] {agent} 실패 — {res.error}")
            self.out(f"[relay] 자세한 것은 {store.debug_path(self.root, self.issue)}")
        else:
            self.out(f"[relay] {agent} 끝 ({res.seconds:.1f}초)")
        # 세션 ID 는 실패해도 남긴다(다음 입력이 이어 갈 수 있다). 본 순번은 성공했을 때만 올린다.
        snapshot = res.quota if isinstance(res.quota, dict) and res.quota.get("source") == agent else {}
        warnings = self._quota_notice(agent, snapshot, st.get("quota_warning"))
        fields = {"turns": st["turns"] + 1, "quota": snapshot, "quota_warning": warnings}
        if res.session:
            fields["session"] = res.session
        if res.ok:
            fields["seen"] = store.last_seq(self.root, self.issue)
        store.update_agent(self.root, self.issue, agent, **fields)
        return res

    # ── 마무리 ──
    def close(self) -> bool:
        r = self.boundary.closable(self.issue)
        if not r["ok"]:
            self.out(f"[relay] 아직 마무리할 수 없다 — {r['why']}")
            self.dbg("console.close", f"#{self.issue} 마무리 거절 — {r['why']}")
            return False
        n = self.issue
        a = store.archive(self.root, n, why=f"일감 「{r['status']}」 · 보고서 {len(r['reports'])}건")
        self.out(f"[relay] 작업 세션 #{n} 마무리 — 기록을 {a['dest']} 에 보관했고 세 에이전트 세션을 비웠다")
        self.issue, self.subject, self.agent = 0, "", ""
        return True

    def status(self) -> None:
        if not self.issue:
            self.out("[relay] 열린 작업 세션이 없다")
            return
        st = store.state(self.root, self.issue)
        self.out(f"[relay] 작업 세션 #{self.issue} — {self.subject}")
        self.out(f"[relay] 지금 에이전트 {self.agent or '(없음)'} · 기록 {store.last_seq(self.root, self.issue)}번까지 · cwd {self.cwd}")
        for a in AGENTS:
            i = st["agents"][a]
            self.out(f"  {a:<6} {i['turns']}회 · 본 순번 {i['seen']} · 세션 {i['session'] or '(없음)'}")
            self.out(quota_line(a, i.get("quota")))
        self.out(f"[relay] 기록 {store.log_path(self.root, self.issue)}")
        self.out(f"[relay] 디버그 {store.debug_path(self.root, self.issue)}")

    # ── 루프 ──
    HELP = ("/issue 일감 선택 · /agent 에이전트 선택·교체 · /status 상태 · /reset 지금 에이전트 세션 비우기 · "
            "/close 마무리 · /quit 나가기 · 그 밖의 입력은 지금 에이전트에게 전달")

    def loop(self) -> int:
        self.out(f"[relay] {self.HELP}")
        while True:
            try:
                if not self.issue and not self.choose_issue():
                    line = self.inp("[relay] 일감 없음 — /issue 또는 /quit> ").strip()
                    if line in ("/quit", "/q"):
                        return 0
                    continue
                if not self.agent and not self.choose_agent():
                    line = self.inp("[relay] 에이전트 없음 — /agent 또는 /quit> ").strip()
                    if line in ("/quit", "/q"):
                        return 0
                    continue
                line = self.inp(f"#{self.issue} {self.agent}> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.out("")
                self.dbg("console.loop", "입력 끝 — 나간다(세션은 남는다)")
                return 0
            if not line:
                continue
            try:
                if line in ("/quit", "/q"):
                    self.dbg("console.loop", "나간다(세션은 남는다)")
                    return 0
                if line == "/help":
                    self.out(f"[relay] {self.HELP}")
                elif line == "/issue":
                    self.issue, self.subject, self.agent = 0, "", ""
                elif line == "/agent":
                    self.choose_agent()
                elif line == "/status":
                    self.status()
                elif line == "/reset":
                    self.reset_agent()
                elif line == "/close":
                    self.close()
                elif line.startswith("/"):
                    self.out(f"[relay] 모르는 명령: {line} — /help")
                else:
                    self.send(line)
            except store.StoreError as e:
                self.out(f"[relay] 세션 파일 문제 — {e}")
                store.debug(self.root, None, "console.loop", f"StoreError: {e}")
            except Exception as e:                      # noqa: BLE001 — 콘솔을 죽이지 않고 사유를 남긴다
                self.out(f"[relay] 예외 — {type(e).__name__}: {e}")
                store.debug(self.root, None, "console.loop", f"예외 {type(e).__name__}: {e}")


def main(argv=None) -> int:
    import argparse
    from master.relay.boundary import AxIssueBoundary
    ap = argparse.ArgumentParser(prog="python -m master.relay", description="세 CLI 대화 중계 상위 레이어 (#942)")
    ap.add_argument("--issue", type=int, default=0, help="바로 열 일감 번호")
    ap.add_argument("--agent", choices=AGENTS, default="", help="바로 고를 에이전트")
    ap.add_argument("--cwd", default="", help="에이전트 작업 디렉터리(기본: 지금 디렉터리)")
    ap.add_argument("--root", default="", help="세션 저장 위치(기본: ~/ax-state/relay 또는 AX_RELAY_ROOT)")
    ap.add_argument("--quota-threshold", type=parse_quota_threshold, default=None,
                    help="잔여 한도 경고 임계값 0~100 (기본: AX_RELAY_QUOTA_THRESHOLD 또는 20)")
    a = ap.parse_args(argv)
    root = a.root or store.default_root()
    cwd = os.path.abspath(a.cwd or os.getcwd())
    relay = Relay(root=root, cwd=cwd, boundary=AxIssueBoundary(), quota_threshold=a.quota_threshold)
    store.debug(root, None, "console.main", f"시작 — cwd={cwd} root={root} issue={a.issue} agent={a.agent}")
    print(f"[relay] 작업 디렉터리 {cwd}")
    if a.issue and not relay.open_issue(a.issue):
        return 2
    if a.agent and relay.issue:
        relay.set_agent(a.agent)
    return relay.loop()
