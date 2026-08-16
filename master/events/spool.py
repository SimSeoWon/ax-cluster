"""디렉토리 스풀 — 영속 · 단일 소비자 · 중복 합치기 (PLAN §5.4.5, §5.4.5-a).

**파일 하나 = 이벤트 하나.** append-only jsonl 을 쓰지 않는 이유는 소비 시점의 경합이다:
소비자가 파일을 rename 으로 가져가는 순간 **이미 열려 있던 생산자가 rename 된 파일에
계속 쓴다.** 창이 좁을 뿐 유실이고, **웹훅에서 유실은 영구다.**

    ~/ax-spool/
        tmp/        rename 전 임시 파일 (같은 FS 여야 원자적)
        incoming/   생산자가 넣은 것
        claimed/    소비자가 처리 중인 배치
        rejected/   검증 실패 — [중요] 지우지 않는다(감사)

[중요] **at-least-once 다.** 크래시하면 `claimed/` 가 남고 재기동 시 다시 처리한다.
exactly-once 를 만들지 않는 이유는 필요가 없기 때문이다 — 색인은 워터마크(커밋 해시)
기준 따라잡기라 **멱등**이다(§5.5.3-c).

[중요] **합치기가 안전한 근거도 같다.** 같은 `project_id` 의 이벤트 N 개에서 최신 하나만 남기고
버려도 되는 것은, 소비자가 개별 이벤트가 아니라 **`last_indexed_commit` → HEAD** 를
따라잡기 때문이다. 워터마크가 타임스탬프였다면 이 합치기는 안전하지 않다.
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from ..projects.config import normalize_project_id

DEFAULT_SPOOL = Path.home() / "ax-spool"

# 색인기가 만든 커밋에 붙는 트레일러. 이게 붙은 push 는 소비하지 않는다 (§5.5.3-d).
INDEX_TRAILER = "[ax-index]"

_SUBDIRS = ("tmp", "incoming", "claimed", "rejected")


class SpoolError(RuntimeError):
    pass


@dataclass
class Event:
    """훅이 넣는 한 건. `project_id` 는 **필수** — 없으면 소급이 불가능하다 (§5.5.3-⑤)."""

    project_id: str
    ref: str = ""
    old: str = ""
    new: str = ""
    at: str = ""
    subject: str = ""      # HEAD 커밋 제목/메시지. 재귀 차단 판정에 쓴다
    path: Path | None = None   # 이 이벤트가 담긴 파일 (읽어 온 경우)
    raw: dict = field(default_factory=dict)

    @property
    def is_index_output(self) -> bool:
        """색인기가 만든 커밋인가 (§5.5.3-d ⓑ)."""
        return INDEX_TRAILER in (self.subject or "")

    def to_dict(self) -> dict:
        d = dict(self.raw)
        d.update(project_id=self.project_id, ref=self.ref, old=self.old,
                 new=self.new, at=self.at)
        if self.subject:
            d["subject"] = self.subject
        return d

    @classmethod
    def from_dict(cls, d: dict, path: Path | None = None) -> "Event":
        if not isinstance(d, dict):
            raise SpoolError(f"이벤트가 매핑이 아니다: {type(d).__name__}")
        pid = str(d.get("project_id") or "").strip()
        if not pid:
            # §5.5.3-⑤ — 소급 불가하므로 받아들이지 않는다.
            raise SpoolError("project_id 가 없다. 프로젝트가 1개여도 필수다 (§5.5.3-⑤).")
        return cls(
            project_id=pid,
            ref=str(d.get("ref") or ""),
            old=str(d.get("old") or ""),
            new=str(d.get("new") or ""),
            at=str(d.get("at") or ""),
            subject=str(d.get("subject") or ""),
            path=path,
            raw=d,
        )


@dataclass
class Batch:
    """소비자가 받아 가는 한 묶음."""

    dir: Path
    events: list[Event]                       # 합치기 후 — project_id 당 하나
    coalesced_away: int = 0                   # 합치기로 버린 개수
    skipped_index_output: int = 0             # 재귀 차단으로 건너뛴 개수
    rejected: int = 0                         # 검증 실패로 rejected/ 로 보낸 개수

    def __len__(self) -> int:
        return len(self.events)

    def summary(self) -> str:
        return (
            f"{len(self.events)}건 처리 대상 "
            f"(합치기로 {self.coalesced_away}건 절약 · "
            f"색인출력 {self.skipped_index_output}건 스킵 · 거부 {self.rejected}건)"
        )


def coalesce(events: Iterable[Event]) -> tuple[list[Event], int]:
    """`project_id` 별로 **최신 하나만** 남긴다 (§5.5.3-⑤ 의 합치기 키).

    비교 키는 casefold — `Sim/ModularStage` 와 `sim/modularstage` 는 같은 것이다
    (§5.5.4-④). 입력 순서를 "오래된 것 → 최신" 으로 보고 나중 것이 이긴다.
    반환: (남은 이벤트, 버린 개수)
    """
    latest: dict[str, Event] = {}
    dropped = 0
    for ev in events:
        key = normalize_project_id(ev.project_id)
        if key in latest:
            dropped += 1
        latest[key] = ev
    return list(latest.values()), dropped


class Spool:
    """디렉토리 스풀. 생산자는 `enqueue`, 소비자는 `claim_batch` → `done`."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.environ.get("AX_EVENT_SPOOL") or DEFAULT_SPOOL)
        for d in _SUBDIRS:
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self._lock_fd: int | None = None

    # ── 경로 ──────────────────────────────────────────
    @property
    def tmp(self) -> Path: return self.root / "tmp"
    @property
    def incoming(self) -> Path: return self.root / "incoming"
    @property
    def claimed(self) -> Path: return self.root / "claimed"
    @property
    def rejected(self) -> Path: return self.root / "rejected"
    @property
    def lock_path(self) -> Path: return self.root / "consumer.lock"

    # ── 생산 ──────────────────────────────────────────
    def enqueue(self, event: Event | dict) -> Path:
        """이벤트 하나를 넣는다. **임시 파일 → rename** 이라 부분 기록이 보이지 않는다."""
        ev = event if isinstance(event, Event) else Event.from_dict(event)
        name = f"{time.time_ns()}-{secrets.token_hex(4)}.json"
        tmp = self.tmp / name
        tmp.write_text(json.dumps(ev.to_dict(), ensure_ascii=False), encoding="utf-8")
        final = self.incoming / name
        os.replace(tmp, final)   # 같은 FS — 원자적
        return final

    # ── 단일 소비자 ────────────────────────────────────
    def acquire(self) -> bool:
        """비차단 `flock`. **이미 도는 소비자가 있으면 False** — 에러가 아니다.

        프로세스가 죽으면 커널이 놓으므로 스테일 락이 남지 않는다.
        """
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._lock_fd = fd
        return True

    def release(self) -> None:
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    def __enter__(self) -> "Spool":
        if not self.acquire():
            raise SpoolError("소비자가 이미 돌고 있다 (flock). 둘이 돌면 순서가 깨진다.")
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    # ── 소비 ──────────────────────────────────────────
    def orphan_batches(self) -> list[Path]:
        """크래시로 남은 배치. **재기동 시 이것부터 처리한다** (at-least-once)."""
        return sorted(d for d in self.claimed.iterdir() if d.is_dir())

    def claim_batch(self, *, is_registered=None) -> Batch:
        """`incoming/` 을 통째로 가져와 검증·합치기까지 끝낸 배치를 돌려준다.

        `is_registered(project_id) -> bool` 을 주면 등록되지 않은 프로젝트를 거부한다
        (§5.5.4-④ 의 casefold 조회를 넘기면 된다). 주지 않으면 그 검사를 건너뛴다.
        """
        files = sorted(f for f in self.incoming.iterdir() if f.is_file())
        batch_dir = self.claimed / f"{time.time_ns()}-{secrets.token_hex(3)}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            # rename 이므로 여기서부터는 생산자가 건드릴 수 없다.
            os.replace(f, batch_dir / f.name)
        return self._read_batch(batch_dir, is_registered=is_registered)

    def _read_batch(self, batch_dir: Path, *, is_registered=None) -> Batch:
        good: list[Event] = []
        rejected = 0
        for f in sorted(batch_dir.iterdir()):
            if not f.is_file():
                continue
            try:
                ev = Event.from_dict(json.loads(f.read_text(encoding="utf-8")), path=f)
                if is_registered is not None and not is_registered(ev.project_id):
                    raise SpoolError(
                        f"등록되지 않은 project_id: {ev.project_id!r} (§5.5.4-④)"
                    )
            except (json.JSONDecodeError, SpoolError, OSError) as e:
                self._reject(f, str(e))
                rejected += 1
                continue
            good.append(ev)

        # 재귀 차단 (§5.5.3-d ⓑ) — 합치기 **전에** 거른다.
        kept = [e for e in good if not e.is_index_output]
        skipped = len(good) - len(kept)

        events, dropped = coalesce(kept)
        return Batch(dir=batch_dir, events=events, coalesced_away=dropped,
                     skipped_index_output=skipped, rejected=rejected)

    def _reject(self, f: Path, reason: str) -> None:
        """[중요] 지우지 않는다. 조용히 사라지면 '훅이 안 옴' 과 '거부됨' 을 구분할 수 없다."""
        target = self.rejected / f.name
        try:
            os.replace(f, target)
            target.with_suffix(target.suffix + ".why").write_text(
                reason + "\n", encoding="utf-8"
            )
        except OSError:
            pass

    def done(self, batch: Batch) -> None:
        """처리 성공. **여기서만** 배치를 지운다 — 그 전에 죽으면 다시 처리된다."""
        for f in list(batch.dir.iterdir()):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            batch.dir.rmdir()
        except OSError:
            pass

    def pending_count(self) -> int:
        return sum(1 for f in self.incoming.iterdir() if f.is_file())

    def iter_all_pending(self, *, is_registered=None) -> Iterator[Batch]:
        """재기동 복구 → 신규. **고아 배치를 먼저** 내보낸다."""
        for d in self.orphan_batches():
            yield self._read_batch(d, is_registered=is_registered)
        yield self.claim_batch(is_registered=is_registered)
