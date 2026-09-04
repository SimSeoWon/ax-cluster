"""task_queue logic 분리 (2026-07-18) — work 종결 후처리: auto-cleanup·통합 빌드·Redmine (facade = logic.py).

lifecycle → cleanup 단방향 의존 — 이 모듈은 logic_lifecycle 을 import 하지 않는다.
"""
import base64
import json
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional
from .persistence import (
    TaskIndex, _tq_log, _git_repo, _git
)
from .logic_persist import update_work_meta


def _read_redmine_config(root: Path, project: str = "") -> dict:
    """redmine 설정. 큐 루트 `config.json` → 없으면 **마스터의 정본 해석자**로 폴백.

    [중요] **폴백이 없으면 이 이식본은 리눅스에서 영구히 침묵한다** (실측 2026-09-03):
    원전은 인프라 PC 의 `config.json` 에 redmine 3종을 적어 두는 배포 형태였는데, 우리
    큐 루트(`/home/sim/ax-state`)에는 그 파일이 **없다**. 그래서 `rm_cfg` 가 빈 dict 가 되고
    ⑹ 완료 통보가 *"config.redmine_url 미설정"* 으로 조용히 반환됐다.

    폴백 출처는 이미 있는 것들이다 — 새로 만들지 않았다:
        url      `redmine.base_url()`  (env `AX_REDMINE_URL` → 기본값)
        api_key  `redmine.api_key()`   (env → **컨테이너 DB**. `#347` 이 지적한 그 경로)
        project  `redmine.project_of(<work 의 project>)` — 레지스트리의 `redmine.project`

    [주의] `project_of` 는 **폴백하지 않는다**(`#293`) — 미설정이면 빈 문자열이고, 그때는
    이슈를 만들지 않는다. 조용히 `modularstage` 로 떨어지면 남의 프로젝트를 오염시킨다.
    """
    cfg_path = root / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding='utf-8-sig') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    url = (cfg.get("redmine_url") or "").rstrip("/")
    key = cfg.get("redmine_api_key") or ""
    proj = cfg.get("redmine_project") or ""
    if not (url and key and proj):
        try:
            from ..redmine import base_url, api_key, project_of
            url = url or base_url()
            key = key or api_key()
            proj = proj or (project_of(project) if project else "")
        except Exception:                                    # noqa: BLE001
            pass
    return {"url": url, "api_key": key, "project": proj}


def _redmine_post_issue(rm_cfg: dict, subject: str, description: str) -> Optional[int]:
    """Redmine 이슈 생성 — 성공 시 issue_id, 실패 시 None.
    redmine_tracker MCP 와 같은 REST 호출 패턴, 단 stdio MCP 우회해 직접 호출."""
    if not (rm_cfg.get("url") and rm_cfg.get("api_key") and rm_cfg.get("project")):
        return None
    url = f"{rm_cfg['url']}/issues.json"
    payload = {"issue": {
        "project_id": rm_cfg["project"],
        "subject": subject,
        "description": description,
    }}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"X-Redmine-API-Key": rm_cfg["api_key"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        iss = data.get("issue") or {}
        return int(iss.get("id")) if iss.get("id") else None
    except Exception:
        return None


def _redmine_add_note(rm_cfg: dict, issue_id: int, notes: str,
                      status_name: str = "") -> bool:
    """기존 이슈에 **노트**를 붙인다 (필요하면 상태도). 성공 여부만 돌려준다.

    [중요] 사건마다 이슈를 새로 만들지 않는다 — work 하나에 이슈 하나이고, 라운드·전진·
    추가 개선·마감이 **그 이슈의 노트**로 쌓인다 (사용자 2026-09-04).
    """
    if not (rm_cfg.get("url") and rm_cfg.get("api_key") and issue_id):
        return False
    issue: dict = {"notes": notes}
    if status_name:
        issue["status_name"] = status_name
    body = json.dumps({"issue": issue}).encode("utf-8")
    req = urllib.request.Request(
        f"{rm_cfg['url']}/issues/{int(issue_id)}.json", data=body, method="PUT",
        headers={"X-Redmine-API-Key": rm_cfg["api_key"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except Exception:                                        # noqa: BLE001
        return False


def create_work_issue_async(idx: TaskIndex, work_id: str):
    """🔴 **등재 시점에** 그 분산 작업의 레드마인 이슈를 만든다 (사용자 2026-09-04:
    *"완료시 만들지말고 작업 등재할때 만들라고"*).

    [주의] 종전에는 **라운드가 끝나야** 이슈가 났다. 그래서 ⑺ 에서 「추가 개선을 하기로 했다」
    같은 결정이 생겨도 적을 자리가 없었고, 기입이 전부 마지막에 몰렸다 — 타이밍이 안 맞았다.

    [중요] 실패는 등재를 막지 않는다 — 큐가 정본이고 레드마인은 기록이다. 다만 **왜 못 만들었는지
    는 찍는다**(조용한 침묵이 이 저장소가 가장 비싸게 치른 부류다).
    """
    def _job():
        try:
            with idx.lock:
                wmeta = idx.works.get(work_id)
                if not wmeta or wmeta.get("redmine_issue_id"):
                    return
                title = wmeta.get("title", work_id)
                target_branch = wmeta.get("target_branch") or "(unknown)"
                project = wmeta.get("project") or ""
            rm_cfg = _read_redmine_config(idx.root, project)
            missing = [n for n, v in (("url", rm_cfg.get("url")),
                                      ("api_key", rm_cfg.get("api_key")),
                                      ("project", rm_cfg.get("project"))) if not v]
            if missing:
                _tq_log(f"[redmine] {work_id} 이슈 생성 스킵 — 없는 것: {', '.join(missing)} "
                        f"(work.project={project!r})", idx.root)
                return
            desc = "\n".join([
                "분산 작업 등재 — 이 이슈에 라운드마다 기록이 쌓인다",
                "",
                f"- work_id: {work_id}",
                f"- 작업 브랜치: `{target_branch}`",
                f"- 프로젝트: {project}",
                "",
                "## 진행 방식",
                "",
                "1. 마스터가 조각을 워커에 파견하고, 조각마다 서브 브랜치에 커밋한다",
                "2. 전부 끝나면 이 이슈에 **라운드 완료** 노트가 붙는다",
                "3. `.33` 이 `ax-advance` 로 서브 브랜치를 작업 브랜치에 머지·빌드하고 전진시킨다",
                "4. 더 고칠 것이 있으면 그 내용을 여기 적고 다음 라운드를 등재한다",
                "5. 마감하면 `main` 머지 뒤 이 이슈를 닫는다",
            ])
            iid = _redmine_post_issue(rm_cfg, f"[분산 작업] {title}", desc)
            if not iid:
                _tq_log(f"[redmine] {work_id} 이슈 생성 실패 (네트워크/인증/필수필드 확인)",
                        idx.root)
                return
            update_work_meta(idx, work_id, redmine_issue_id=iid)
            _tq_log(f"[redmine] {work_id} 등재 이슈 생성: #{iid}", idx.root)
        except Exception as e:                               # noqa: BLE001
            _tq_log(f"[redmine] {work_id} 등재 이슈 예외: {e}", idx.root)

    threading.Thread(target=_job, daemon=True).start()


def _try_create_review_issue_async(idx: TaskIndex, work_id: str,
                                    build_status: str = "passed",
                                    build_log_tail: str = "",
                                    build_error: str = ""):
    """ready_for_review (또는 build_failed) flip 시 Redmine 이슈 자동 생성 (백그라운드).
    실패는 silent — Redmine 미연동 환경에서도 cleanup 흐름 무중단.

    Args:
        build_status: "passed" (default) 또는 "failed" — 통합 빌드 결과
        build_log_tail: 빌드 실패 시 마지막 로그 일부 (이슈 본문에 첨부)
        build_error: 빌드 실패 시 짧은 에러 요약
    """
    def _job():
        try:
            with idx.lock:
                wmeta = idx.works.get(work_id)
                if not wmeta:
                    return
                # [중요] 이슈는 **등재 때** 만들어져 있다 — 라운드 완료는 그 이슈에 **노트**로
                #    붙인다 (사용자 2026-09-04). 없으면(등재 때 실패) 여기서 만든다.
                issue_id = wmeta.get("redmine_issue_id")
                # 멱등 — 같은 라운드의 완료를 두 번 적지 않는다
                _r = int(wmeta.get("round", 1) or 1)
                if int(wmeta.get("noticed_round", 0) or 0) >= _r:
                    return
                title = wmeta.get("title", work_id)
                target_branch = wmeta.get("target_branch") or "(unknown)"
                # [중요] 레드마인 프로젝트는 **work 의 project 축**에서 온다 (`#293`) —
                #    상수로 박으면 NS 의 완료가 ModularStage 에 등재된다.
                work_project = wmeta.get("project") or ""
                # verified / failed / cancelled 분리
                tasks_all = [t for t in idx.tasks.values() if t.get("work_id") == work_id]
                # 🔴 [중요] **이번 라운드 것만 알린다.** work 하나가 여러 라운드를 돌고,
                #    지난 라운드 조각은 ⑺ 에서 이미 작업 브랜치로 들어갔다. 다 실으면
                #    `.33` 이 「이번에 머지할 것」을 목록에서 가려낼 수 없다.
                _round = int(wmeta.get("round", 1) or 1)
                if any(int(t.get("round") or 0) > 0 for t in tasks_all):
                    tasks_all = [t for t in tasks_all
                                 if int(t.get("round") or 0) in (0, _round)]
                tasks_v = [t for t in tasks_all if t.get("status") == "verified"]
                tasks_f = [t for t in tasks_all if t.get("status") == "failed"]
                # 🔴 [중요] `cancelled` 를 **둘로 가른다** (사용자 결정 2026-09-04).
                #    `no_work` = *"골조에 `[PSEUDO]` 가 0개 = 이미 완성된 파일"* 이고 실패도
                #    취소도 아니다. 뭉뚱그리면 공지에서 실패로 읽힌다 — 공지 본문이 사실과
                #    다른 말을 하는 것을 사용자가 「눈속임」이라 불렀다(2026-09-03).
                tasks_cx = [t for t in tasks_all if t.get("status") == "cancelled"]
                tasks_nw = [t for t in tasks_cx if t.get("no_work")]
                tasks_c = [t for t in tasks_cx if not t.get("no_work")]
                files_v = sorted({t.get("target_file", "") for t in tasks_v if t.get("target_file")})
                files_f = sorted({t.get("target_file", "") for t in tasks_f if t.get("target_file")})
                files_c = sorted({t.get("target_file", "") for t in tasks_c if t.get("target_file")})
                nw_details = [(t.get("target_file", "?"),
                               str(t.get("cancel_reason") or "")[:200]) for t in tasks_nw]
                # failed task 의 reason 도 같이 — 사용자 진단용
                fail_details = []
                for t in tasks_f:
                    rf = t.get("target_file", "?")
                    last_fb = t.get("last_feedback") or t.get("last_result") or ""
                    fail_details.append((rf, str(last_fb)[:200]))

            rm_cfg = _read_redmine_config(idx.root, work_project)
            # [중요] **무엇이 없어서 안 갔는지 찍는다.** 종전에는 url 하나만 보고 한 문구로
            #    반환해서, 키가 없는 것과 프로젝트가 없는 것이 같은 침묵으로 보였다.
            missing = [n for n, v in (("url", rm_cfg.get("url")),
                                      ("api_key", rm_cfg.get("api_key")),
                                      ("project", rm_cfg.get("project"))) if not v]
            if missing:
                _tq_log(f"[redmine] {work_id} 스킵 — 없는 것: {', '.join(missing)} "
                        f"(work.project={work_project!r})", idx.root)
                return

            # [주의] **`no_work` 는 미완성이 아니다** — 제목에 「일부 미완성」을 붙이지
            #    않는다. 골조가 완성본이라 채울 것이 없었던 조각이고, 그것은 정상 결과다.
            partial = bool(tasks_f or tasks_c)
            build_failed = (build_status == "failed")
            if build_failed:
                subject_prefix = "[빌드 실패] 통합 빌드 게이트 차단"
            elif partial:
                subject_prefix = "[리뷰 요청 — 일부 미완성]"
            else:
                subject_prefix = "[리뷰 요청]"
            subject = f"{subject_prefix} {title}"
            # [중요] **여기서 「검증 통과」·「빌드 통과」를 주장하지 않는다** (사용자 지적
            #    2026-09-03). 조각 하나씩 도장을 찍는 것은 값이 없고, 마스터는 애초에 빌드를
            #    하지 않는다. 조각의 `verified` 는 *"그 조각 작업이 끝났다"* 는 신호일 뿐이다.
            #    **실제 검사는 `.33` 이 서브 브랜치를 전부 머지한 뒤 한 곳에서 한다.**
            #    [주의] 종전 문구는 `통합 빌드: [완료] 통과` 를 **무조건** 찍었다 — 아무도
            #    빌드하지 않았는데 통과라고 적는 거짓말이었다.
            header_line = f"라운드 {_r} 완료 — 통합·검사·전진 판단 요청"
            lines = [
                header_line,
                "",
                f"- work_id: {work_id}",
                f"- 작업 브랜치: `origin/{target_branch}`",
                f"- 완료된 조각: {len(tasks_v)}건"
                + (f" / 실패: {len(tasks_f)}건" if tasks_f else "")
                + (f" / 할 일 없음: {len(tasks_nw)}건" if tasks_nw else "")
                + (f" / 취소: {len(tasks_c)}건" if tasks_c else ""),
                "",
                "[중요] **아직 아무것도 검증되지 않았다.** 조각은 각자 자기 서브 브랜치에",
                "커밋만 된 상태다 — 통합 빌드도, 교차 파일 정합성 검사도 하지 않았다.",
                "그 검사는 아래 ⑴ 에서 **전부 머지한 뒤 한 번** 한다.",
                "",
                "## 서브 브랜치 (머지 대상)",
            ]
            # [중요] **이름을 여기서 조립하지 않는다** — 규약은 `branch_names.durable_branch`
            #    하나다. 실측 2026-09-05: 여기서 `task/{work}/{task}` 로 만들어 라운드
            #    (`r1/`)가 빠졌고, 사람이 읽는 목록이 **실물과 다른 브랜치**를 가리켰다.
            def _branch_of(t) -> str:
                if t.get("branch"):
                    return str(t["branch"])
                try:
                    from ..work.branch_names import durable_branch     # noqa: PLC0415
                    return durable_branch(work_id, str(t.get("task_id", "")),
                                          int(t.get("round") or 0))
                except Exception:                                      # noqa: BLE001
                    return f"task/{work_id}/{t.get('task_id','')}"

            for t in tasks_v:
                b = _branch_of(t)
                lines.append(f"- `{b}` — `{t.get('target_file','')}`")
            lines.append("")
            lines.append("## 구현 파일")
            for f in files_v[:50]:
                lines.append(f"- `{f}`")
            if len(files_v) > 50:
                lines.append(f"- … 외 {len(files_v) - 50}건")

            if tasks_f:
                lines += ["", "##  미완성 파일 (failed) — 수동 보완 필요"]
                for rf, fb in fail_details[:30]:
                    if fb:
                        lines.append(f"- `{rf}` — {fb}")
                    else:
                        lines.append(f"- `{rf}`")
                if len(fail_details) > 30:
                    lines.append(f"- … 외 {len(fail_details) - 30}건")

            if tasks_nw:
                lines += ["", f"## 할 일 없음 — 골조가 이미 완성본이다 ({len(tasks_nw)}건)", "",
                          "[중요] 실패가 아니다. 이 조각들은 골조에 `[PSEUDO]` 가 0개라",
                          "채울 본문이 없었고 **파견하지 않았다**(추론 비용 0). 원전도 그 경우",
                          "태스크를 skip 한다. 서브 브랜치도 없으므로 머지 대상이 아니다.",
                          "[주의] 의도한 것이 아니라면 **골조에 `[PSEUDO]` 를 넣어** 다시 등재한다.",
                          ""]
                for rf, why in nw_details[:30]:
                    lines.append(f"- `{rf}`" + (f" — {why}" if why else ""))
                if len(nw_details) > 30:
                    lines.append(f"- … 외 {len(nw_details) - 30}건")

            if tasks_c:
                lines += ["", "## 취소된 파일 (cancelled)"]
                for f in files_c[:30]:
                    lines.append(f"- `{f}`")

            if build_failed:
                lines += ["", "## [실패] 통합 빌드 실패 로그 (마지막 부분)"]
                if build_error:
                    lines.append(f"- 요약: {build_error}")
                if build_log_tail:
                    lines.append("```")
                    lines.append(build_log_tail[-2500:])
                    lines.append("```")

            # [중요] **지시는 받는 사람이 실제로 칠 수 있는 것이어야 한다.** 원전 문구는
            #    `master_orchestrator --finalize` 였는데 그 exe 는 `.33` 에 없다 — 있지도
            #    않은 명령을 지시하는 절차서가 원전 이식에서 값을 치른 그 부류(`#297`)다.
            #    🔴 우리 정본 ⑺ 은 요청자(`.33`)가 **`ax-advance`** 로 서브 브랜치를 작업
#    브랜치에 머지·빌드하고 「버그냐 구조냐」를 판단해 **한 칸 전진**시키는 것이다.
#    [주의] `ax-review`(main 반영)와 **다른 단계**다 — 그 둘을 섞어 오지시를 냈다
#    (2026-09-04, 사용자: *"리뷰 요청은 왜한건데? 전혀 다른 스킬을 요청한거 같은데"*).
            lines += [
                "",
                "## 다음 단계 — `.33` 메인 작업 컴퓨터에서 한다 (정본 ⑺ · 라운드 종결)",
                "",
                "[중요] **`main` 에 올리는 단계가 아니다.** 여기서 움직이는 것은 이 work 의",
                f"작업 브랜치 `{target_branch}` 하나이고, 한 칸 **전진**시키는 것이다.",
                "",
                f"1. `.33` 체크아웃에서 `claude` 를 열고 **`work {work_id} 라운드 종결`**",
                "   (또는 `전진시켜`) — **`ax-advance`** 스킬이 잡는다.",
                "   [주의] `#N 리뷰`·`머지 검토`는 **다른 스킬**(`ax-review`)이고 그건 `main`",
                "   반영 단계다 — 라운드 직후에 부르는 것이 아니다.",
                "2. 서브 브랜치를 **전부 작업 브랜치에 머지한다** — 옆에 세운 worktree 에서.",
                "   [중요] 사람의 워킹트리는 건드리지 않는다. `main` 도 만지지 않는다.",
                "3. **거기서 한 번 통합 빌드한다** — 조각별로 나눠 보지 않는다:",
                "   교차 파일 정합성은 전부 모아 놓고 세워야 드러난다.",
                "4. 결과를 보고 **「버그인가, 구조를 고쳐야 하는가」를 판단한다.**",
                "   · 이상 없음 → 승인해 `advance_work(..., confirm=True)` 로 **전진**(push)",
                "   · 버그      → 그 트리에서 고쳐 커밋하거나, 주석 남기고 다음 라운드",
                "   · 구조 수정  → **전진 보류** · `.h`/`.cpp` 에 지시 주석 → 다음 라운드 등재",
                "5. 다음 라운드는 `target_branch` 에 **전진한 그 브랜치**를 실어 재등재한다 —",
                "   서브태스크 브랜치가 전진한 tip 에서 다시 갈라진다.",
            ]
            if partial:
                lines.append("")
                lines.append("[주의] 실패·취소분이 있다 — 그 조각은 머지 대상이 아니다. "
                             "손으로 채우거나 task 를 재등재해 워커를 다시 돌린다.")
            lines += [
                "",
                "## 작업 전체가 끝났으면 — 그때가 `main` 이다",
                "",
                "전진을 여러 번 해서 목표에 닿았을 때만 `ax-review` → "
                "`review.finalize_work(..., confirm=True)`. "
                "[중요] `main` 을 옮기는 것은 사람의 자리다.",
            ]
            description = "\n".join(lines)

            if issue_id:
                if not _redmine_add_note(rm_cfg, int(issue_id), description):
                    _tq_log(f"[redmine] {work_id} 라운드 {_r} 노트 실패 — #{issue_id}", idx.root)
                    return
                update_work_meta(idx, work_id, noticed_round=_r)
                _tq_log(f"[redmine] {work_id} 라운드 {_r} 완료 노트 → #{issue_id}", idx.root)
            else:
                # 등재 때 못 만들었다 — 여기서 만든다 (제목은 등재분과 같은 규약)
                issue_id = _redmine_post_issue(rm_cfg, subject, description)
                if not issue_id:
                    _tq_log(f"[redmine] {work_id} 이슈 생성 실패 (네트워크/인증/필수필드 확인)",
                            idx.root)
                    return
                update_work_meta(idx, work_id, redmine_issue_id=issue_id, noticed_round=_r)
                _tq_log(f"[redmine] {work_id} 이슈 생성: #{issue_id} "
                        f"[주의] 등재 때 만들어졌어야 한다", idx.root)
        except Exception as e:
            _tq_log(f"[redmine] {work_id} 예외: {e}", idx.root)

    threading.Thread(target=_job, daemon=True).start()


# [중요] **여기 있던 `_run_integration_build` 와 `_do_auto_cleanup` 을 지웠다**
# (사용자 확정 2026-09-03, 반복 지시: *"통합자 필요 없다"*).
#
# 원전은 인프라 PC 의 큐 루트가 **git 저장소**이고 거기서 `master_orchestrator.exe` 로 통합
# 빌드까지 돌리는 배포였다. 우리 큐 루트(`/home/sim/ax-state`)는 git 저장소가 아니라서
# `_do_auto_cleanup` 은 초입에서 *"git repo 없음"* 으로 반환했고 — **완료 공지가 그 함수
# 안에 들어 있었기 때문에 공지도 같이 죽었다**(실측 2026-09-03 22:38:59).
#
# 게다가 그 함수의 ⑶단계가 통합 빌드 게이트였다. 정본 ⑺ 은 *"서브 브랜치를 딴 것은 `.33`
# 메인 작업 컴퓨터에서 머지한다"* 이므로 마스터에 그 자리는 없다.
#
# 남긴 것은 **공지 하나**다 — 조각이 전부 terminal 이면 `.33` 에 알린다. 그게 마스터의 끝이다.

_TOAST_PS = """
$ErrorActionPreference = "Stop"
[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]
$tpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$tx = $tpl.GetElementsByTagName("text")
[void]$tx.Item(0).AppendChild($tpl.CreateTextNode("{title}"))
[void]$tx.Item(1).AppendChild($tpl.CreateTextNode("{body}"))
$toast = New-Object Windows.UI.Notifications.ToastNotification $tpl
$aid = "{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe"
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($aid).Show($toast)
"""


def _push_desktop_notice(idx: TaskIndex, work_id: str, text: str) -> None:
    """🔴 **요청자 화면에 밀어 준다 — 토스트 알림으로** (사용자 2026-09-05).

    [중요] 지금 알림은 전부 **당기는(pull)** 구조다 — 레드마인 이슈 · `:8103` · `.33` 세션 훅.
    켜져 있는 세션과 **사람**에게는 아무것도 안 뜬다. 실측 2026-09-05: 라운드가 끝났는데
    `.33` 세션이 *"완료 노티 안 오는거야?"* 로 물었고 사람이 직접 상태를 캐물었다.
    (`#356` — 레드마인 SMTP 미설정이라 메일 경로도 없다.)

    [주의] **`msg.exe` 는 쓰지 않는다** — 처음에 그걸로 배선했더니 사용자가
    *"에러창처럼 띄우는 사람이 어디있어"* 라고 했다. 모달 대화상자는 알림이 아니다.
    지금은 **윈도우 토스트**(`ToastNotificationManager`)이고, 실측 2026-09-05 `.33` 에서 떴다.

    [중요] 명령은 **`-EncodedCommand`(UTF-16LE base64)** 로 보낸다 — PowerShell 을 ssh 인라인
    으로 넘기면 `$`·따옴표가 깨져 **출력이 아예 없는** 실패가 난다(메모리
    `live_test_starts_clean` ⑹). 인코딩해 보내면 한글 본문도 그대로 간다.

    [주의] 실패는 삼킨다 — 레드마인 노트가 정본이고 이 알림은 덤이다. 다만 **사유는 찍는다.**
    """
    try:
        from ..client.bundle import workshops                     # noqa: PLC0415
        wmeta = idx.works.get(work_id) or {}
        project = str(wmeta.get("project") or "").strip()
        if not project:
            return
        targets = [(h, u) for h, u, _p, _d, role, _dp in workshops(project)
                   if str(role) == "requester" and h and u]
    except Exception as e:                                        # noqa: BLE001
        _tq_log(f"[notify-desktop] {work_id} 대상 조회 실패 — {type(e).__name__}: {e}", idx.root)
        return
    if not targets:
        _tq_log(f"[notify-desktop] {work_id} 요청자 작업장이 없다 — 밀 곳이 없다", idx.root)
        return
    body = str(text).replace('"', "'").replace("\n", " ")[:200]
    script = _TOAST_PS.format(title="AX 분산 작업", body=body)
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    for host, user in targets:
        try:
            r = subprocess.run(
                ["ssh", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                 f"{user}@{host}", f"powershell -NoProfile -EncodedCommand {enc}"],
                capture_output=True, text=True, timeout=40)
            if r.returncode == 0:
                _tq_log(f"[notify-desktop] {work_id} → {host} 토스트 띄움", idx.root)
            else:
                _tq_log(f"[notify-desktop] {work_id} → {host} 실패 rc={r.returncode} "
                        f"{(r.stderr or '').strip()[:120]}", idx.root)
        except Exception as e:                                    # noqa: BLE001
            _tq_log(f"[notify-desktop] {work_id} → {host} 예외 — {type(e).__name__}: {e}",
                    idx.root)


def _auto_cleanup_work_async(idx: TaskIndex, work_id: str):
    """조각이 전부 끝났다 — **요청자(`.33`)에 완료를 공지한다.** 그게 전부다.

    [중요] 이름은 호출부(`logic_lifecycle`·`logic`) 계약을 지키려고 남겼다. 하는 일은
    **공지 하나**다: git 도 안 만지고 빌드도 안 한다. 통합은 `.33` 이 `ax-review` 로 한다.
    """
    _tq_log(f"[notify] {work_id} 조각 전부 종결 — 요청자에 완료 공지", idx.root)
    _try_create_review_issue_async(idx, work_id)
    # 🔴 **사람에게도 민다** — 레드마인 노트는 당겨야 보인다(사용자 2026-09-05).
    with idx.lock:
        wmeta = idx.works.get(work_id) or {}
        rnd = int(wmeta.get("round", 1) or 1)
        tot = int(wmeta.get("total", 0))
        ver = int(wmeta.get("verified", 0))
        iss = wmeta.get("redmine_issue_id")
    threading.Thread(target=_push_desktop_notice, args=(
        idx, work_id,
        f"라운드 {rnd} 완료 — 조각 {ver}/{tot}"
        + (f" · 레드마인 #{iss}" if iss else "")
        + ". 이 PC 에서 ax-advance 로 라운드를 종결하세요."), daemon=True).start()
