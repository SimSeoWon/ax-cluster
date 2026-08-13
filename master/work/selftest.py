"""클러스터 셀프테스트 드라이런 — 원전 `cluster_selftest.py` 이식 **1단계**.

🔴 **이것이 증명하는 것 하나**: 서버가 **매니페스트에만** 실어 보낸 토큰(NONCE)이 durable
산출물에 나타나면, *"서버가 모은 컨텍스트가 git 으로 실려 가 작업장이 읽고 소비했다"* 가
증명된다. 원전이 이 자리에 값을 매긴 이유(사용자 2026-07-05): *"시킬 일을 억지로 만드는 것도
고역"* — 사람이 가짜 일감을 지어낼 필요 없이 서버가 캔드 작업을 주입한다.

## 단계를 나눈 이유

    1단계 (여기)   격리 저장소 + `fake_workshop` → **NONCE 라운드트립 기제**를 증명
    2단계 (#141)   실 큐 · 실 작업장 · 실 백엔드(로컬 LLM/agy) → e2e

🔴 **1단계를 먼저 하는 것은 게으름이 아니라 강제다.** 마스터 정본(`<프로젝트>/repo/`)은 push 가
봉인돼 있다(`DISABLED://마스터는-소스저장소에-push하지-않는다-PLAN.md-2.1`). 원전은 인프라 PC 가
push 할 수 있어서 라이브 저장소에 worktree 격리로 셀프테스트 브랜치를 올렸지만, 우리는 그 자리에
**임시 저장소**를 쓴다. 격리의 목적(*"라이브 데몬 메인 트리 미접촉"*)은 더 강하게 달성된다.

## ⚠️ 우리와 원전이 다른 것 — 매니페스트 배달 경로

    원전   git-carried — `.claude/tasks/<id>/context.md` 를 base 에 **커밋**해서 보낸다.
           작업장은 base 를 체크아웃하면 디스크에 그것이 있고, **검색을 안 한다**(백엔드 평준화).
    우리   scp — `infer.py` 가 `./{work}/{task}/manifest.md` 로 **파일 전송**한다.

🔴 **NONCE 증명은 git-carried 성질에 기댄다.** 그래서 이 드라이런은 원전 방식으로 매니페스트를
커밋한다. ⚠️ 실전 경로(scp)를 이 방식으로 바꿀지는 **별도 결정**이다 — git-carried 는 재배정
무손실(새 작업장이 같은 base 만 체크아웃하면 자동으로 갖는다)과 *"어떤 컨텍스트로 이 코드가
나왔나"* 가 git 히스토리에 남는 것을 얻고, 대신 원전이 물린 `.claude/` gitignore 함정
(`git add -A` 가 스테이징을 못 해 `nothing to commit` rc=1)을 같이 물려받는다. → `git add -f`.

## ⚠️ 정리에 대해 — probe 는 증거가 아니다

`coordinator.cleanup_attempts` 는 기본이 `delete=False` 다(실작업 attempt 는 **증거 보존**,
08-09 결정). 🔴 **셀프테스트 probe 는 그 대상이 아니다** — 자동 생성된 시험 산출물이므로
원전대로 지운다(`delete=True`). 남기려면 `keep=True`.

🔴 원전이 정리에서 실측한 결함 하나를 같이 옮긴다: *"task cancel·브랜치 삭제만으론 work 메타가
`in_progress` 로 잔존해 watcher 가 paused 되고 큐에 잔재가 쌓인다(2026-06-21 배포에서 5건 발견)"*.
2단계에서 큐를 붙일 때 **work 종결까지** 해야 한다.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import coordinator as C
from .branch_names import attempt_branch, durable_branch

MANIFEST_REL_FMT = ".ax/tasks/{work_id}/context.md"
NONCE_HEADING = "## 셀프테스트 토큰"


# ─────────────────────────────────────────────────────────────
# probe 스켈레톤 — 🔴 배너를 명시한다 (원전, 사용자 2026-07-05)
# ─────────────────────────────────────────────────────────────

def probe_source(gidx: int) -> str:
    """작업장이 채울 트리비얼 스켈레톤.

    🔴 본문에 `[SELFTEST]` 배너를 박는 이유가 원전에 적혀 있다 — 작성 백엔드가 *"이건 셀프테스트
    probe 다"* 를 분명히 알게 하고, **사소한 작업이라도 반드시 파일을 실제 편집하고 완료 신호를
    내도록** 유도해 *narration-only 완료 환각*(파일 미변경)을 막는다.
    """
    return (
        '"""[SELFTEST] 클러스터 셀프테스트 프로브 — 실제 제품 코드 아님 (자동 생성·검증 후 폐기).\n\n'
        "분산 파이프라인 e2e 검증용 시험 태스크다. 작업장은 서버가 실어 보낸 컨텍스트 매니페스트를\n"
        f"읽고 그 안의 NONCE_{gidx} 를 반환하도록 이 함수를 **실제로 편집**한다\n"
        "(매니페스트 전달·소비 라운드트립 증명). 사소해 보여도 반드시 파일을 편집하고 완료 신호를 낼 것.\n"
        '"""\n\n\n'
        f"def selftest_probe_{gidx}() -> str:\n"
        f"    # [PSEUDO] 매니페스트의 '{NONCE_HEADING}' 절에 적힌 NONCE_{gidx} 값을 그대로 반환하라.\n"
        f'    #          예: return "CSTNONCE..."  — 그 값만 문자열 리터럴로.\n'
        f"    #          매니페스트에 NONCE_{gidx} 가 없으면 빈 문자열을 반환한다. 다른 코드 추가 금지.\n"
        "    raise NotImplementedError\n"
    )


def impl_source(gidx: int, nonce: str) -> str:
    """작업장이 낸 결과물 — `[PSEUDO]` 가 제거되고 NONCE 를 반환한다."""
    return (
        f'"""[SELFTEST] probe {gidx} — 구현됨."""\n\n\n'
        f"def selftest_probe_{gidx}() -> str:\n"
        f'    return "{nonce}"\n'
    )


def nonce_section(nonces: dict) -> str:
    """매니페스트에 덧붙일 절. 🔴 **스켈레톤 본문에는 없다** — 그게 증명의 조건이다."""
    lines = "\n".join(f"NONCE_{i}={n}" for i, n in sorted(nonces.items()))
    return (
        f"{NONCE_HEADING}\n"
        f"{lines}\n\n"
        "각 NONCE_<i> 는 서버가 **매니페스트로만** 전달한다(스켈레톤 본문엔 없음). "
        "`selftest_probe_<i>()` 가 NONCE_<i> 를 반환하면 매니페스트가 작업장까지 git 으로 실려 가 "
        "소비됐음이 증명된다.\n"
    )


def extract_nonce(manifest_text: str, gidx: int) -> str:
    """매니페스트에서 `NONCE_<gidx>` 를 뽑는다. 없으면 빈 문자열.

    ⚠️ **없으면 빈 문자열**이 맞다 — 원전 프롬프트도 그렇게 지시한다. 여기서 예외를 던지면
    *"매니페스트가 안 갔다"* 는 사실이 단정 실패가 아니라 크래시로 나타나 원인이 흐려진다.
    """
    m = re.search(rf"^NONCE_{gidx}=(\S+)\s*$", manifest_text or "", re.MULTILINE)
    return m.group(1) if m else ""


def manifest_reading_workshop(gidx: int, work_id: str):
    """🔴 **NONCE 를 인자로 받지 않는다** — 디스크의 매니페스트에서 읽는다.

    이것이 증명의 핵심이다. 값을 주입하면 *"우리가 아는 값을 우리가 썼다"* 를 확인할 뿐이고,
    **git 이 실어 줬는지**는 아무것도 말해 주지 않는다. 실전에서 이 자리는 작업장의 `claude -p` 다.
    """
    def _fn(repo: Path, target_rel: str) -> None:
        man = repo / MANIFEST_REL_FMT.format(work_id=work_id)
        text = man.read_text(encoding="utf-8") if man.exists() else ""
        nonce = extract_nonce(text, gidx)
        p = repo / target_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(impl_source(gidx, nonce), encoding="utf-8")
    return _fn


# ─────────────────────────────────────────────────────────────
# 드라이런
# ─────────────────────────────────────────────────────────────

@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class DryRun:
    ok: bool = False
    work_id: str = ""
    tasks: int = 0
    nonces: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    fails: list = field(default_factory=list)
    kept_at: str = ""
    error: str = ""

    def chk(self, name: str, cond: bool, detail: str = "") -> None:
        self.checks.append(Check(name, bool(cond), detail))
        if not cond:
            self.fails.append(name)


def _sh(cwd: Path, *args: str) -> None:
    r = subprocess.run(["git", "-c", "user.email=cluster@local", "-c", "user.name=ax-cluster",
                        "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise C.GitError(f"git {' '.join(args)} rc={r.returncode}: {(r.stderr or '').strip()}")


def run_dry(*, tasks: int = 3, keep: bool = False, base_nonce: str = "",
            workshop: str = "dryrun", logf=None) -> DryRun:
    """격리 저장소에서 2-tier + NONCE 라운드트립을 한 바퀴 돌린다.

    반환값의 `fails` 가 비어 있으면 통과. `keep=True` 면 임시 저장소를 남긴다(경로는 `kept_at`).
    """
    log = logf or (lambda stage, msg: None)
    n = max(1, int(tasks))
    ts = time.strftime("%Y%m%d_%H%M%S")
    base_nonce = base_nonce or f"CSTNONCE{ts}_{os.getpid() % 100000}"
    work_id = f"selftest_{ts}"
    nonces = {i: f"{base_nonce}_{i}" for i in range(n)}
    probe_rels = {i: f"cluster_selftest/probe_{ts}_{i}.py" for i in range(n)}
    r = DryRun(work_id=work_id, tasks=n, nonces=nonces)

    tmp = Path(tempfile.mkdtemp(prefix=f"ax_selftest_{ts}_"))
    try:
        # ── 1. 격리 저장소 (bare origin + 작업 클론) ─────────────
        origin, work = tmp / "origin.git", tmp / "work"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
        log("isolate", f"격리 저장소 {tmp}")

        # ── 2. probe 스켈레톤 커밋·push (base1) ──────────────────
        for i in range(n):
            p = work / probe_rels[i]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(probe_source(i), encoding="utf-8")
        _sh(work, "add", "-A")
        _sh(work, "commit", "-q", "-m", f"[skeleton] {n} selftest probes {ts}")
        _sh(work, "push", "-q", "origin", "main")
        log("skeleton", f"probe {n}개 커밋")

        # ── 3. 🔴 매니페스트를 base 에 커밋 (task 등재 **전**) ────
        # 원전 실측: task_id 키 경로는 등록 **후** 발급이라 rebase race 가 난다 →
        # work_id 키로 task 등재 전 base 에 포함해 그 race 를 구조적으로 없앤다.
        man = work / MANIFEST_REL_FMT.format(work_id=work_id)
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(
            "# 컨텍스트 매니페스트 (서버 1회 수집 — 작업장은 검색 말고 읽기)\n\n"
            "## 계약 (contracts)\n"
            "post: 각 selftest_probe_<i>() 는 매니페스트의 NONCE_<i> 문자열을 반환\n\n"
            + nonce_section(nonces),
            encoding="utf-8")
        # 🔴 `add -f` — 원전이 실 저장소에서 물린 함정. `.ax/`(원전은 `.claude/`)가 gitignore 면
        #    `add -A` 는 스테이징을 못 하고 commit 이 `nothing to commit` rc=1 로 죽는다.
        #    gitignore 는 add 만 막고 **checkout 은 안 막으므로** 강제 추적하면 작업장 디스크에 나타난다.
        _sh(work, "add", "-f", MANIFEST_REL_FMT.format(work_id=work_id))
        _sh(work, "commit", "-q", "-m", f"[manifest] {work_id} ({n} nonces)")
        _sh(work, "push", "-q", "origin", "main")
        base2 = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                               capture_output=True, text=True).stdout.strip()
        log("manifest", f"매니페스트 커밋 base2={base2[:8]}")
        r.chk("매니페스트가 base 에 실렸다", bool(base2))
        r.chk("🔴 스켈레톤 본문에 NONCE 가 없다",
              all(nonces[i] not in probe_source(i) for i in range(n)))

        # ── 4. 🔴 작업장 트리를 **새로 클론**한다 ────────────────
        # 이게 증명의 조건이다. 서버가 매니페스트를 쓴 트리에서 그대로 읽으면 *"git 이 실어
        # 줬다"* 와 *"우리가 놔둔 파일을 읽었다"* 를 구분할 수 없다 — 리포트 13 §14 의
        # 「주입은 계약을 재고 실물을 재지 않는다」가 더 미묘한 형태로 나오는 자리다.
        # 새 클론은 **base2 를 체크아웃해서만** 매니페스트를 갖는다.
        shop = tmp / "shop"
        subprocess.run(["git", "clone", "-q", str(origin), str(shop)], check=True)
        _sh(shop, "checkout", "-q", base2)
        man_in_shop = shop / MANIFEST_REL_FMT.format(work_id=work_id)
        r.chk("🔴 매니페스트가 **git 으로** 작업장 트리에 도착했다", man_in_shop.exists(),
              str(man_in_shop))
        # 🔴 "git 으로 왔다" 를 실제로 단정한다 — 추적 중이고, 트리가 깨끗하다(직접 쓴 것 0).
        tracked = subprocess.run(["git", "-C", str(shop), "ls-files",
                                  MANIFEST_REL_FMT.format(work_id=work_id)],
                                 capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(shop), "status", "--porcelain"],
                               capture_output=True, text=True).stdout.strip()
        r.chk("매니페스트가 git 에 추적되어 있다", bool(tracked), tracked)
        r.chk("작업장 트리가 깨끗하다 (직접 쓴 것 0)", not dirty, dirty[:200])
        log("clone", f"작업장 트리 {shop.name} — base2 체크아웃")

        # ── 5. 각 probe 를 한 바퀴 — 🔴 **두 트리로 갈라서** ─────
        # 원전 주석: *"real 모드는 합성(run_round)을 쓰지 않고 assign(서버) … push_attempt(원격
        # 작업장) … verify_and_merge(서버) 로 비동기 분리하되 같은 함수들을 재사용한다."*
        # 드라이런도 그 형태로 태워야 실전 경로를 잰다.
        for i in range(n):
            tid = f"{work_id}.{i}"
            a = C.assign_attempt(tid, workshop, f"t{i}")                      # 서버
            C.push_attempt(shop, a["attempt"], base2,                          # 작업장
                           manifest_reading_workshop(i, work_id), probe_rels[i],
                           message=f"[selftest] probe {i}", logf=log)
            res = C.verify_and_merge(work, a["attempt"], a["durable"],          # 서버
                                     submit_epoch=1, current_epoch=1, logf=log)
            r.chk(f"probe[{i}] durable merge", bool(res.get("merged")), res.get("reason", ""))

        # ── 5. 단정 — durable 에 NONCE 라운드트립 + [PSEUDO] 제거 ──
        ok_n = 0
        for i in range(n):
            tid, dur = f"{work_id}.{i}", durable_branch(f"{work_id}.{i}")
            _sh(work, "fetch", "-q", "origin", dur)
            body = subprocess.run(["git", "-C", str(work), "show", f"origin/{dur}:{probe_rels[i]}"],
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace").stdout
            has, clean = nonces[i] in body, "[PSEUDO]" not in body
            if has and clean:
                ok_n += 1
            else:
                log("verify", f"probe[{i}] 실패 — nonce={'있음' if has else '없음'} "
                              f"pseudo={'제거' if clean else '잔존'}")
        r.chk(f"🔴 매니페스트 NONCE 라운드트립 (durable {ok_n}/{n})", ok_n == n, f"{ok_n}개")

        # attempt 가 남아 있다 (증거)
        refs = subprocess.run(["git", "-C", str(work), "ls-remote", "--heads", "origin"],
                              capture_output=True, text=True).stdout
        r.chk("attempt 브랜치가 원격에 있다",
              all(attempt_branch(f"{work_id}.{i}", workshop, f"t{i}") in refs for i in range(n)))

        # ── 6. 정리 — 🔴 probe 는 증거가 아니므로 지운다 ─────────
        if keep:
            r.kept_at = str(tmp)
            log("cleanup", f"keep — 격리 저장소 보존: {tmp}")
        else:
            for i in range(n):
                tid = f"{work_id}.{i}"
                C.cleanup_attempts(work, tid, delete=True, logf=log)
                subprocess.run(["git", "-C", str(work), "push", "-q", "origin",
                                "--delete", durable_branch(tid)], capture_output=True)
            left = subprocess.run(["git", "-C", str(work), "ls-remote", "--heads", "origin"],
                                  capture_output=True, text=True).stdout
            r.chk("정리 후 probe 브랜치가 남지 않는다",
                  all(f"{work_id}.{i}" not in left for i in range(n)), left.strip()[:200])

        r.ok = not r.fails
        return r
    except Exception as e:                                  # noqa: BLE001
        r.error = f"{type(e).__name__}: {e}"
        r.chk("예외 없이 완주", False, r.error)
        return r
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
