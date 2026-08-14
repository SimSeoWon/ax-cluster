"""클러스터 셀프테스트 드라이런 — 원전 `cluster_selftest.py` 이식 **1단계**.

🔴 **이것이 증명하는 것 하나**: 서버가 **매니페스트에만** 실어 보낸 토큰(NONCE)이 durable
산출물에 나타나면, *"서버가 모은 컨텍스트가 git 으로 실려 가 작업장이 읽고 소비했다"* 가
증명된다. 원전이 이 자리에 값을 매긴 이유(사용자 2026-07-05): *"시킬 일을 억지로 만드는 것도
고역"* — 사람이 가짜 일감을 지어낼 필요 없이 서버가 캔드 작업을 주입한다.

## 단계를 나눈 이유

    1단계 (여기)   격리 저장소 + `fake_workshop` → **NONCE 라운드트립 기제**를 증명
    2단계 (#141)   실 큐 · 실 작업장 · 실 백엔드(로컬 LLM/agy) → e2e

🔴 **1단계를 먼저 하는 것은 게으름이 아니라 강제다.** 마스터 정본(`<프로젝트>/repo/`)은 push 가
봉인돼 있다(`DISABLED://마스터는-소스저장소에-push하지-않는다-PLAN.md-2.1`).

> 🔴 **근거 만료 2026-08-15 (소 1.2.2 · `#123`).** 그 봉인은 **열렸다** — 별도 쓰기 표면
> `gitea-write` + `pre-push` 가드가 들어왔다. 따라서 *"강제였다"* 는 더 이상 사실이 아니다.
> ⚠️ **다만 제약이 봉인에서 가드로 옮겨졌다**(실측: `refs/heads/selftest/<slug>` 는 가드가
> **거부**한다 — 허용은 `attempt/*`·`task/*` 뿐). 2단계(`#141`)는 이제 **막힌 것이 아니라
> 결정이 필요한 것**이다: 가드에 `selftest/*` 를 더할지, 셀프테스트를 `attempt/` 아래로
> 둘지, 계속 미룰지(그러면 **근거를 새로 써야 한다**). → 리포트 16 §12.9 원전은 인프라 PC 가
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


def _ssh(host: str, user: str, cmd: str, *, timeout: int = 180) -> tuple:
    """작업장에서 셸 한 번. `(rc, out)`. **예외를 던지지 않는다 — 실패도 사실이다.**"""
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                        f"{user}@{host}", cmd],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _q(method: str, url: str, payload=None, *, timeout: int = 30) -> tuple:
    """큐 HTTP 한 번. `(rc, json|텍스트)`. **예외 대신 사실을 돌려준다.**

    🔴 세 서비스 전부 bearer 토큰이 필수다(fail-closed). 토큰 파일 위치는 `auth` 가 SSOT 이므로
    경로를 여기 다시 쓰지 않는다.
    """
    import json as _json
    import urllib.error
    import urllib.request
    from ..auth import token_file
    try:
        tok = token_file().read_text(encoding="utf-8").strip()
    except OSError as e:
        return 0, f"토큰을 읽지 못했다: {e}"
    data = _json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, (_json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:                                  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


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


# ─────────────────────────────────────────────────────────────
# 2단계 — 🔴 실 작업장 · 실 Gitea
#
# ⚠️ **마스터는 push 하지 못한다**(정본 push 봉인). 그래서 git 쓰기는 전부 작업장에서 돌고
# 마스터는 **조율하고 독립적으로 검증**한다(읽기는 허용). 즉 이 하니스가 증명하는 것은
# *"2-tier·매니페스트·NONCE 라운드트립이 실 Gitea 에서 돈다"* 이고, *"마스터가 쓰기 주체"*
# 는 **증명하지 않는다** — 그건 봉인이 풀려야 재는 것이다(#123).
#
# 격리: 작업장의 **메인 체크아웃을 건드리지 않는다** — 옆에 worktree 둘을 만든다.
#   wtA = 서버 역할 (골조·매니페스트 작성 → push, 그리고 verify_and_merge)
#   wtB = 작업장 역할 — 🔴 `worktree add <base2>` 로 **git 으로만** 매니페스트를 받는다
# ─────────────────────────────────────────────────────────────

def run_live(*, host: str, user: str, checkout: str, tasks: int = 2,
             work_fn_cmd=None, keep: bool = False, base_nonce: str = "",
             via_queue: bool = False, queue_url: str = "http://127.0.0.1:8101",
             logf=None) -> DryRun:
    """실 작업장·실 Gitea 로 한 바퀴.

    `work_fn_cmd(gidx, probe_rel, nonce_key, work_id)` 는 wtB 에서 돌 셸 명령을 돌려준다
    (없으면 스크립트 편집 = 2a). 🔴 **`work_id` 를 인자로 넘기는 이유**: 호출자가 매니페스트
    경로를 만들려면 그 값이 필요한데, 밖에서 따로 계산하면 초 단위로 어긋나 프롬프트가 없는
    파일을 가리킨다. 첫 실 구동(2026-08-14)에서 우연히 초가 맞아 **통과가 운이었을 수 있는**
    상태였다 — 계약으로 막는다.

    🔴 정리는 `finally` 다 — 원격 브랜치(selftest/attempt/durable)와 worktree 를 지운다.
    probe 는 증거가 아니라 시험 산출물이다. `keep=True` 면 남긴다.
    """
    log = logf or (lambda stage, msg: None)
    n = max(1, int(tasks))
    ts = time.strftime("%Y%m%d_%H%M%S")
    base_nonce = base_nonce or f"CSTNONCE{ts}_{os.getpid() % 100000}"
    work_id = f"selftest_{ts}"
    slug = f"cluster_selftest_{ts}"
    st_branch = f"selftest/{slug}"
    nonces = {i: f"{base_nonce}_{i}" for i in range(n)}
    probe_rels = {i: f"cluster_selftest/probe_{ts}_{i}.py" for i in range(n)}
    man_rel = MANIFEST_REL_FMT.format(work_id=work_id)
    wtA, wtB = f"{checkout}/../_ax_st_A_{ts}", f"{checkout}/../_ax_st_B_{ts}"
    r = DryRun(work_id=work_id, tasks=n, nonces=nonces)
    made_remote: list = []
    qwork = ""
    qtasks: dict = {}

    def sh(cmd: str, *, cwd: str = checkout, timeout: int = 180) -> tuple:
        return _ssh(host, user, f'cd "{cwd}" && {cmd}', timeout=timeout)

    try:
        rc, out = sh("git rev-parse --abbrev-ref HEAD && git status --porcelain | wc -l")
        r.chk("작업장 트리가 깨끗하다 (메인 체크아웃 미접촉 전제)",
              rc == 0 and out.strip().endswith("0"), out[:200])
        if r.fails:
            return r

        # ── 1. wtA: 서버 역할 worktree ──────────────────────────
        sh("git fetch -q origin")
        rc, out = sh(f'git worktree add -q -b {st_branch} "{wtA}" origin/main')
        r.chk("wtA(서버 역할) worktree 생성", rc == 0, out[:200])
        if r.fails:
            return r
        log("isolate", f"wtA={wtA} branch={st_branch}")

        # ── 2. probe 골조 + 매니페스트를 base 에 커밋·push ───────
        for i in range(n):
            body = probe_source(i).replace("'", "'\\''")
            sh(f'mkdir -p "$(dirname {probe_rels[i]})" && '
               f"printf '%s' '{body}' > {probe_rels[i]}", cwd=wtA)
        man_body = (
            "# 컨텍스트 매니페스트 (서버 1회 수집 — 작업장은 검색 말고 읽기)\n\n"
            "## 계약 (contracts)\n"
            "post: 각 selftest_probe_<i>() 는 매니페스트의 NONCE_<i> 문자열을 반환\n\n"
            + nonce_section(nonces)).replace("'", "'\\''")
        sh(f'mkdir -p "$(dirname {man_rel})" && printf \'%s\' \'{man_body}\' > {man_rel}', cwd=wtA)
        # 🔴 add -f — `.ax/` 가 gitignore 여도 추적한다 (원전 실측 함정)
        rc, out = sh(f"git add -A && git add -f {man_rel} && "
                     f'git commit -q -m "[skeleton] {n} selftest probes + manifest {ts}"', cwd=wtA)
        r.chk("골조+매니페스트 커밋", rc == 0, out[:200])
        rc, base2 = sh("git rev-parse HEAD", cwd=wtA)
        base2 = base2.strip()
        rc, out = sh(f"git push -q -u origin {st_branch}", cwd=wtA)
        r.chk("🔴 실 Gitea 에 selftest 브랜치 push", rc == 0, out[:200])
        if rc == 0:
            made_remote.append(st_branch)
        log("push", f"base2={base2[:8]} → {st_branch}")

        # ── 2b. 🔴 큐에 work + task 등재 (via_queue) ──────────────
        # 원전 순서를 지킨다: **매니페스트를 base 에 넣은 뒤** task 를 등재한다.
        # (task_id 는 등록 후 발급이라 매니페스트 경로를 task_id 로 잡으면 rebase race 가 난다.)
        qtasks: dict = {}
        if via_queue:
            st, wr = _q("POST", f"{queue_url}/api/v1/works", {
                "title": f"[cluster-selftest] {ts} ({n} tasks)",
                "target_repo": checkout, "target_branch": st_branch,
                "branch_isolation": True, "created_branch_at": base2, "slug": slug,
                "decomposition": "".join(f"- L0 selftest_probe_{i}\n" for i in range(n)),
                "distribution_mode": "push", "force_duplicate": True})
            qwork = (wr or {}).get("work_id", "") if isinstance(wr, dict) else ""
            r.chk("🔴 큐에 work 등재", bool(qwork), f"{st} {str(wr)[:200]}")
            for i in range(n):
                st, tr = _q("POST", f"{queue_url}/api/v1/tasks", {
                    "work_id": qwork, "type": "implement_module",
                    "task_data": {"stem": f"probe_{ts}_{i}",
                                  "classes": [f"selftest_probe_{i}"]},
                    "base_commit": base2, "target_file": probe_rels[i], "header_file": "",
                    "depends_on": [], "hierarchy_level": 0, "priority": 0,
                    "stem": f"probe_{ts}_{i}", "origin": "selftest"})
                tid_q = (tr or {}).get("task_id", "") if isinstance(tr, dict) else ""
                r.chk(f"큐에 task[{i}] 등재", bool(tid_q), f"{st} {str(tr)[:200]}")
                qtasks[i] = tid_q
            r.chk("전 task 가 depends_on 없이 동시 claimable",
                  len(qtasks) == n and all(qtasks.values()))
            log("queue", f"work={qwork} tasks={list(qtasks.values())}")

        # ── 3. wtB: 작업장 역할 — git 으로만 매니페스트를 받는다 ──
        rc, out = sh(f'git worktree add -q --detach "{wtB}" {base2}')
        r.chk("wtB(작업장 역할) worktree 생성", rc == 0, out[:200])
        rc, out = sh(f"test -f {man_rel} && git ls-files {man_rel} && git status --porcelain", cwd=wtB)
        r.chk("🔴 매니페스트가 **git 으로** 작업장 트리에 도착했다 (직접 쓴 것 0)",
              rc == 0 and man_rel in out and out.strip().endswith(man_rel), out[:200])

        # ── 4. 각 probe: (큐 claim →) 작업장 편집 → attempt push (→ submit/verify) ──
        #
        # 🔴 `via_queue` 면 **어느 probe 를 받을지 큐가 정한다.** 우리가 순서를 고르면 claim
        # 로직(우선순위·의존·epoch 발급)을 재는 게 아니라 우회하는 것이 된다.
        by_qtid = {v: k for k, v in qtasks.items() if v}
        order = list(range(n))
        claimed: dict = {}
        if via_queue:
            order = []
            for _ in range(n):
                stc, tc = _q("POST", f"{queue_url}/api/v1/tasks/claim",
                             {"worker_id": f"selftest-{host}", "verify_capable": False})
                qtid = (tc or {}).get("task_id", "") if isinstance(tc, dict) else ""
                idx = by_qtid.get(qtid)
                r.chk(f"큐 claim {len(order)+1}/{n} — 우리 task 를 받았다",
                      idx is not None, f"{stc} task_id={qtid!r}")
                if idx is None:
                    break
                claimed[idx] = tc
                order.append(idx)
            r.chk("🔴 claim 이 epoch 를 발급했다 (fencing 전제)",
                  bool(claimed) and all(int(t.get("epoch", 0)) >= 1 for t in claimed.values()),
                  str({k: v.get("epoch") for k, v in claimed.items()}))
            r.chk(f"전 task 가 claim 됐다 ({len(order)}/{n})", len(order) == n)

        for i in order:
            tid = f"{work_id}.{i}"
            att, dur = attempt_branch(tid, host.replace(".", "-"), f"t{i}"), durable_branch(tid)
            sh(f"git checkout -q -B {att} {base2}", cwd=wtB)
            if work_fn_cmd is None:
                # 2a — 스크립트 편집. 🔴 NONCE 를 인자로 주지 않는다: 매니페스트에서 grep 한다.
                cmd = (f'N=$(grep -oP "^NONCE_{i}=\\\\K\\\\S+" {man_rel} || true); '
                       f'printf \'"""[SELFTEST] probe {i} — 구현됨."""\\n\\n\\n'
                       f'def selftest_probe_{i}() -> str:\\n    return "%s"\\n\' "$N" > {probe_rels[i]}')
            else:
                cmd = work_fn_cmd(i, probe_rels[i], f"NONCE_{i}", work_id)
            rc, out = sh(cmd, cwd=wtB, timeout=600)
            r.chk(f"probe[{i}] 작업장 편집", rc == 0, out[:300])
            rc, out = sh(f"git add -A && git commit -q -m '[selftest] probe {i}' && "
                         f"git push -q --force origin {att}", cwd=wtB)
            r.chk(f"probe[{i}] attempt push", rc == 0, out[:200])
            if rc == 0:
                made_remote.append(att)
            # 서버 역할(wtA)이 검증·머지
            rc, out = sh(f"git fetch -q origin {att} && git checkout -q -B {dur} origin/{att} && "
                         f"git push -q origin {dur}", cwd=wtA)
            r.chk(f"probe[{i}] durable 생성·push", rc == 0, out[:200])
            if rc == 0:
                made_remote.append(dur)
            if via_queue and qtasks.get(i):
                qtid = qtasks[i]
                rc_h, head = sh(f"git rev-parse HEAD", cwd=wtB)
                sts, sres = _q("POST", f"{queue_url}/api/v1/tasks/{qtid}/submit", {
                    "branch": att, "head_commit": head.strip(),
                    "self_check": {"selftest": True},
                    "epoch": int(claimed.get(i, {}).get("epoch", 1))})
                r.chk(f"probe[{i}] 큐 submit", sts == 200 and isinstance(sres, dict)
                      and sres.get("ok", True) is not False, f"{sts} {str(sres)[:200]}")
                stv, vres = _q("POST", f"{queue_url}/api/v1/tasks/{qtid}/verify",
                               {"result": "pass", "passed": True})
                r.chk(f"probe[{i}] 큐 verify(pass)", stv == 200, f"{stv} {str(vres)[:200]}")
                stg, tst = _q("GET", f"{queue_url}/api/v1/tasks/{qtid}")
                status = (tst or {}).get("status", "") if isinstance(tst, dict) else ""
                r.chk(f"🔴 probe[{i}] 큐 상태가 verified", status == "verified",
                      f"status={status!r}")

        # ── 5. 🔴 마스터가 **독립적으로** 검증한다 (읽기만) ──────
        #
        # ⚠️ **bare 저장소 읽기에는 `gitea` 그룹이 필요하다.** 대화형 세션은 그룹 추가 이전에
        # 시작됐으면 그것이 없고, 그때 git 은 *"저장소가 아니다"* 라고 해서 **원인을 감춘다**
        # (`consumer.py` 머리말이 2026-08-08 에 실측해 적어 둔 함정 — 2026-08-14 이 하니스의
        # 첫 실 구동에서 그대로 밟았다: `fetch rc=128`).
        # 🔴 그룹 판정을 다시 쓰지 않고 색인기의 헬퍼를 **재사용**한다 — 복제하면 어긋난다.
        from ..events.consumer import _git as _mirror_git
        mirror = Path(__file__).resolve().parents[2] / "ModularStage" / "repo"
        ok_n = 0
        for i in range(n):
            dur = durable_branch(f"{work_id}.{i}")
            rc_f, out_f = _mirror_git(mirror, "fetch", "-q", "origin", dur)
            rc_s, body = _mirror_git(mirror, "show", f"FETCH_HEAD:{probe_rels[i]}")
            if rc_f == 0 and rc_s == 0 and nonces[i] in body and "[PSEUDO]" not in body:
                ok_n += 1
            else:
                log("verify", f"probe[{i}] 실패 — fetch rc={rc_f} ({out_f[:80]}) "
                              f"show rc={rc_s} body={body[:100]!r}")
        r.chk(f"🔴 마스터 독립 검증 — NONCE 라운드트립 ({ok_n}/{n})", ok_n == n, f"{ok_n}개")

        r.ok = not r.fails
        return r
    except Exception as e:                                  # noqa: BLE001
        r.error = f"{type(e).__name__}: {e}"
        r.chk("예외 없이 완주", False, r.error)
        return r
    finally:
        if keep:
            r.kept_at = f"{host}:{wtA},{wtB} · 원격: {', '.join(made_remote)}"
            log("cleanup", f"keep — 보존: {r.kept_at}")
        else:
            if via_queue and qtasks:
                for tid_q in qtasks.values():
                    if tid_q:
                        _q("POST", f"{queue_url}/api/v1/tasks/{tid_q}/cancel", {})
                # 🔴 **work 도 종결한다.** 원전 실측(2026-06-21, 배포에서 5건 발견):
                #    task cancel·브랜치 삭제만으론 work 메타가 `in_progress` 로 잔존해
                #    watcher 가 paused 되고 큐에 잔재가 쌓인다.
                if qwork:
                    stp, _ = _q("PATCH", f"{queue_url}/api/v1/works/{qwork}",
                                {"merge_status": "cancelled"})
                    r.chk("🔴 큐의 work 도 종결됐다 (in_progress 잔존 방지)", stp == 200, str(stp))
            for br in made_remote:
                sh(f"git push -q origin --delete {br} 2>&1 | tail -1")
            sh(f'git worktree remove --force "{wtA}" 2>&1 | tail -1')
            sh(f'git worktree remove --force "{wtB}" 2>&1 | tail -1')
            sh("git worktree prune")
            sh(f"git branch -D {st_branch} 2>&1 | tail -1")
            for i in range(n):
                sh(f"git branch -D {durable_branch(f'{work_id}.{i}')} 2>&1 | tail -1")
            # 🔴 **로컬 attempt 도 지운다.** wtB 가 `checkout -B <attempt>` 로 만든 브랜치는
            #    공유 저장소의 ref 라, worktree 를 지워도 **ref 는 남는다.** 2026-08-14 첫 실
            #    구동 3회에서 로컬 attempt 7개가 쌓인 것을 사후 점검이 잡았다 — 원격만 보고
            #    "흔적 0" 이라 단정했으면 놓쳤을 자리다.
            # ⚠️ `for-each-ref 'refs/heads/attempt/{id}.*'` 는 **안 맞는다** — 그 `*` 는 `/` 를
            #    넘지 못하고 브랜치명이 `attempt/<id>.<i>/<host>/<ts>` 로 슬래시가 셋이다.
            #    (2026-08-14 실측: for-each-ref 0건 / `branch --list` 6건.) 검증된 쪽을 쓴다.
            sh(f'git branch --list "attempt/{work_id}.*" | tr -d " *" '
               f"| xargs -r -n1 git branch -D 2>&1 | tail -2")
            rc_l, left_local = sh(
                f'git branch --list "*{work_id}*" | wc -l')
            r.chk("🔴 정리 후 작업장 로컬에도 흔적 0", left_local.strip() in ("0", ""),
                  f"남음={left_local.strip()}")
            rc, left = sh(f"git ls-remote --heads origin | grep -c '{work_id}\\|{slug}' || true")
            r.chk("🔴 정리 후 원격에 흔적 0", left.strip() in ("0", ""), f"남음={left.strip()}")
            log("cleanup", f"원격 {len(made_remote)}건·worktree 2개 제거 (남음={left.strip()})")
