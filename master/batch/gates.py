"""유휴 배치 시간 게이트 — 원전 `watcher/watch_state.py` 84~233줄 이식
(소 3.4.4 · `#192`, 2026-08-14).

## 🔴 왜 이 파일이 생겼나 — 배치가 얹힐 자리가 없었다

원전 `watch.py` 는 **한 루프 안에 유휴 사이클**을 두고, `watch_state` 의 시간 게이트
(`_should_run_weekly_plan` · `_should_run_recipe_synthesis` · `_should_run_rag_analysis` +
`_mark_*_done`)로 배치를 돌렸다. 우리는 `watch_state` 를 이식할 때 **`in_progress` 일시정지만**
가져왔다(소 3.5.1 → `events/gate.py`). 그래서 실측 2026-08-14 기준 주기 구동 주체가
**둘뿐**이었다(색인 따라잡기 · 상태 스냅샷) — 와처의 서버 배치 16개 능력이 전부 미복각인데
**이식해도 돌 자리가 없는** 상태였다.

## 🔴 폴링 루프로 복각하지 않는다 — 이미 기각된 설계다

`docs/3-open-items.md` 가 두 번 확정해 뒀다:

    §5.4.2  🔴 `watch.py` 의 `while True` 폴링 루프는 **이식 대상이 아니다** (Gitea 이벤트 구동).
            단 *"상주 프로세스 자체는 여전히 필요"*
    §5.4.3  `process_lifecycle.py`·`network_firewall.py` 는 폐기 —
            *"리눅스 등가물로 고쳐 쓰지 않고 **systemd 에 넘긴다**"*

→ 자리는 **`ax-batch.timer`** 다. 유휴 사이클의 *"때가 되면 돈다"* 는 타이머가, *"작업 중이면
안 돈다"* 는 **이미 이식된 `events/gate.py`** 가 맡는다(원전의 같은 조건 — git lock 경쟁).

## 🔴 원전과 다르게 둔 것 둘

**① 게이트를 하나로 접었다.** 원전은 배치마다 함수를 따로 뒀지만 스스로 *"recipe 합성 게이트와
**동일 구조**"* 라고 적어 뒀다 — 조건 다섯(활성 · 입력 최소치 · 시각 · 요일 · 최소 간격)이
같고 상수만 다르다. 그래서 `Schedule` 하나로 접고 배치별로 값을 준다. **재설계가 아니라
같은 것을 한 번만 쓰는 것**이다.

**② `now` 를 주입할 수 있다.** 원전은 `datetime.now()` 를 직접 부른다. 우리는 인자로 받는다 —
🔴 **원전 자신이 같은 이유로 `attempt_branch(ts=…)` 를 인자로 뒀다**(*"테스트에서 시간을
고정할 수 있어야 한다"*). 시간이 박히면 이 게이트는 검증할 수 없다.

⚠️ **지금 이식한 것은 `rag_analysis` 게이트뿐이다.** `weekly_plan`·`recipe_synthesis` 는
그 배치(`#155`·`#157`)가 아직 없다 — 게이트만 옮기면 **입력 없는 배치**를 만드는 것과 같은
실수다(소 3.4.5 에서 같은 함정을 한 번 피했다). 구조는 여기 있으니 배치가 올 때 값만 준다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# 원전 상수 — `_should_run_rag_analysis` / `_should_run_recipe_synthesis` 의 값 그대로
MIN_DAILY_GAP_HOURS = 12
MIN_WEEKLY_GAP_DAYS = 6


@dataclass(frozen=True)
class Schedule:
    """배치 하나의 시간 게이트 설정. **원전의 config 키 이름을 그대로 쓴다.**"""

    key: str                      # config 키 접두 (`rag_analysis` → `rag_analysis_hour` …)
    hour: int = 23                # 이 시각 **이후**에만 돈다
    schedule: str = "weekly"      # `daily` | `weekly`
    day: str = "sunday"           # weekly 일 때 그 요일만
    min_entries: int = 10         # 입력이 이보다 적으면 돌지 않는다

    def from_config(self, cfg: dict) -> "Schedule":
        """프로젝트 config 의 `batch:` 절로 덮어쓴다. 없는 키는 **원전 기본값**을 쓴다."""
        b = ((cfg or {}).get("batch") or {})
        def pick(name, default, cast):
            try:
                return cast(b.get(f"{self.key}_{name}", default))
            except (TypeError, ValueError):
                return default
        return Schedule(
            key=self.key,
            hour=pick("hour", self.hour, int),
            schedule=str(pick("schedule", self.schedule, str)).lower(),
            day=str(pick("day", self.day, str)).lower(),
            min_entries=pick("min_entries", self.min_entries, int),
        )


@dataclass
class Verdict:
    """돌릴 것인가 · 왜. 🔴 **이유를 항상 들고 있다** — 안 도는 이유를 모르면 고장과 구별이 안 된다."""

    run: bool
    reason: str
    key: str = ""

    @property
    def line(self) -> str:
        return f"{'▶' if self.run else '·'} {self.key}: {self.reason}"


def enabled(cfg: dict, key: str) -> bool:
    """`batch.<key>` 가 꺼져 있나. 🔴 **기본은 켜짐**(원전과 같다 — `config.get(k, True)`)."""
    b = ((cfg or {}).get("batch") or {})
    return bool(b.get(key, True))


def marker_path(root: Path, key: str) -> Path:
    """`_last_<key>` 마커. 원전은 `.claude/analysis/_last_analysis` 처럼 산출물 옆에 뒀다 —
    우리는 프로젝트 데이터 밑 `batch/` 에 모은다(§5.5, 배치가 여럿이 될 자리다)."""
    return Path(root) / "batch" / f"_last_{key}"


def read_marker(root: Path, key: str) -> datetime | None:
    p = marker_path(root, key)
    if not p.is_file():
        return None
    try:
        return datetime.fromisoformat(p.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        # 🔴 못 읽으면 **없는 것으로 본다** — 원전과 같다(`except: pass` 후 진행).
        #    방향이 안전하다: 한 번 더 도는 것이 영원히 안 도는 것보다 낫다.
        return None


def write_marker(root: Path, key: str, *, now: datetime | None = None) -> dict:
    """돌았다고 표시한다. 🔴 실패를 **값으로** 돌린다 (조용히 넘기면 매 회차 다시 돈다)."""
    p = marker_path(root, key)
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(stamp, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "reason": f"마커 기록 실패: {e}"}
    return {"ok": True, "at": stamp}


def should_run(sched: Schedule, cfg: dict, root: Path, *, input_count: int,
               now: datetime | None = None) -> Verdict:
    """조건 다섯을 **원전 순서 그대로** 본다. 하나라도 어긋나면 이유와 함께 `run=False`.

        ① 활성        `batch.<key>` (기본 켜짐)
        ② 입력 최소치  `<key>_min_entries`
        ③ 시각        `<key>_hour` 이후
        ④ 요일        weekly 면 `<key>_day` 만
        ⑤ 최소 간격    daily 12시간 · weekly 6일 (마지막 실행 이후)
    """
    now = now or datetime.now()
    s = sched.from_config(cfg)

    if not enabled(cfg, s.key):
        return Verdict(False, f"config 에서 꺼져 있다 (batch.{s.key}=false)", s.key)
    if input_count < s.min_entries:
        return Verdict(False, f"입력 부족 {input_count} < {s.min_entries}건", s.key)
    if now.hour < s.hour:
        return Verdict(False, f"시각 미달 — {now.hour}시 < {s.hour}시", s.key)
    if s.schedule == "weekly":
        today = now.strftime("%A").lower()
        if today != s.day:
            return Verdict(False, f"요일 불일치 — 오늘 {today}, 지정 {s.day}", s.key)

    last = read_marker(root, s.key)
    if last is not None:
        if s.schedule == "daily" and (now - last).total_seconds() < MIN_DAILY_GAP_HOURS * 3600:
            return Verdict(False,
                           f"간격 미달 — 마지막 {last.isoformat(timespec='minutes')} "
                           f"({MIN_DAILY_GAP_HOURS}시간 필요)", s.key)
        if s.schedule == "weekly" and (now - last).days < MIN_WEEKLY_GAP_DAYS:
            return Verdict(False,
                           f"간격 미달 — 마지막 {last.isoformat(timespec='minutes')} "
                           f"({MIN_WEEKLY_GAP_DAYS}일 필요)", s.key)

    return Verdict(True, f"조건 충족 (입력 {input_count}건 · {s.schedule})", s.key)


# 🔴 지금 자리가 있는 배치 하나. 원전 `_should_run_rag_analysis` 의 상수 그대로
# (hour 23 · weekly · sunday · min_entries 10).
RAG_ANALYSIS = Schedule(key="rag_analysis", hour=23, schedule="weekly", day="sunday",
                        min_entries=10)
