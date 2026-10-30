# 130 — `.2` 보드 교체 복구 · `setup-host` 진입점 · Ollama 복구 · 35B 목록 정리

날짜: 2026-10-30 · 마스터 담당 Claude · 레드마인 [#843](http://192.168.0.57:8080/issues/843)(완료)

## 사건

`.2` 메인보드가 고장 나서 교체했다. 사용자가 임시 IP `.45` 를 `.2` 로 복구했다. 새 보드는 SATA
슬롯이 부족해서 **프로젝트 SSD(E:)를 뺐다.** 사용자 제안: *"신규 워커 설치시 레포를 다운로드 받고
초기화하는 로직을 파이썬으로 스킬을 만들고 검증하면 어떨까"*.

## 착수 전 실측

| 대상 | 상태 |
|---|---|
| 접속 | `janus@.2` SSH 정상 · 호스트명 `DESKTOP-HV0I6DL` 그대로 · ICMP 는 원래 막혀 있다 |
| 드라이브 | C 1.5TB 여유 · E 없음 · `C:\trunk` 없음 |
| 등록부 | `.2` 경로 4개(ModularStage·NS·MotionForge·AXCluster)가 전부 `E:\trunk\…` |
| 상주 과제 | `AxConductor_AXCluster/NS/MotionForge` · `AxWorker_MotionForge` — 전부 E 를 가리킨다 |
| Gitea | `.2` 에서 `ls-remote` 정상 (키가 C 에 남아 있다) |
| UE 5.8 | `C:\Program Files\UE_5.8` 에 있다(`Build.bat`·`UnrealEditor.exe`). 사용자가 5.8.1 → 5.8.4 업데이트를 진행했다 |

[주의] 처음 「UE58-MISSING」으로 보고한 것은 **내 cmd 따옴표 오류**였다. PowerShell 로 다시 재서 정정했다.

## 이미 있던 것 — 새로 만든 것은 순서뿐

클론(`bundle.bootstrap_checkout`, `#254` — 소유권·Codex ACL·LFS 포함), 상주·지휘자 등록
(`client/init/residency`, `#255`·`#401`), 배달·대조(`cmd_deliver`·`cmd_check`)가 이미 있었다.
없던 것은 **「기계 한 대」 단위의 진입점**과 **옛 경로를 가리키는 상주 해제**다.

사용자 결정: 루트 `C:\trunk` · 클론은 마운트된 AXCluster 만 · 마스터 로컬에서 직접 구현.

## 구현 — `0941944`

- `master/client/setup_host.py`: 단계 순서는 등록부 경로 이전(나머지 필드 보존) → 옛 경로를
  **실제로 가리키는** 과제만 해제 → 마운트 프로젝트 `deliver` → `check`. 기본은 계획만 내고,
  단계가 실패하면 그 자리에서 멈춘다. 신규 기계는 `--user` 가 있어야 하고 계정을 추측하지 않는다.
- `python -m master.client setup-host --host= --root= [--user=] [--confirm]`
- `master/test_setup_host.py` 22건
- `master/skills/ax-worker-setup/SKILL.md` + 홈 링크(`~/.claude/skills` · `~/.agents/skills`)
- 검사: 전수 rc≠0 파일 0개 · 공식 통합 181/181

## 실증 — `.2`

- 등록부 4개를 `C:\trunk\…` 로 옮겼다.
- 낡은 상주 4개를 해제했다. 등록이 없는 이름은 「등록 없음」으로 두고 건드리지 않았다.
- `C:\trunk\AXCluster` 에 `0941944` 로 클론했다(LFS 실물) → 배달 → `check` OK.
- 직접 재확인:
  - 지휘자 과제는 Interactive 이고 C 를 가리킨다.
  - 클론은 clean 이다.
  - `.git` 소유자는 `janus` 다.
  - `worker_mode_readiness('codex')` 3/3 통과
- 이어서 `update`(마운트 프로젝트) 3/3 OK.

## Ollama 복구

| 단계 | 결과 |
|---|---|
| 원인 | 모델 경로 `E:\Ollama` 가 **두 곳**에 있었다 — 사용자 환경변수 `OLLAMA_MODELS`, 그리고 **앱 자체 설정** `%LOCALAPPDATA%\Ollama\db.sqlite`. 서버가 1초마다 `exit 1` 로 죽었다 |
| 환경변수 | 원격으로 `C:\Ollama` 로 바꿨다. **효과 없음** — 앱 설정이 우선한다 |
| 원격 재기동 ① | `Register-ScheduledTask` 거절 `0x80070534`. 계정을 `$env:USERDOMAIN\$env:USERNAME` 로 조합한 탓으로 추정한다 |
| 원격 재기동 ② | `schtasks /create /it /ru DESKTOP-HV0I6DL\janus` 생성·실행·삭제 모두 rc 0 이었는데 앱이 뜨지 않았다. **원인 미확정** — 12초 뒤 과제를 지워서 Last Result 를 못 남겼다 |
| 해결 | 사용자가 앱을 직접 실행하고 Settings → Model location 을 `C:\Ollama` 로 바꿨다 |
| 모델 | `gemma4:e4b` 6.6GB · `qwen2.5-coder:14b` 9.0GB · `qwen3:8b` 5.2GB — 약 7분 |
| 확인 | `/api/ps` 상주 e4b · 브로커 rtx3060 healthy, pin=resident=e4b · `master.provision` [완료] |

[주의] **Ollama 앱은 환경변수보다 자기 설정을 우선한다.** 경로를 옮길 때는 앱 설정을 바꿔야 한다.
환경변수만 바꾸면 조용히 옛 경로를 계속 쓴다.

## 35B 목록 정리 — `cd803a4` · `206a3dc`

- `provision.py`:
  - bc250 `want` 에서 35B(`DRIVER`)를 뺐다. 상주 해제(2026-08-17, `#105`) 뒤에도 남아 매번 「없음」으로 보고됐다.
  - 노드 설명을 실제 핀에 맞췄다: bc250 「e4b 핀」, .2 「e4b 핀 · 14b 보유」.
  - 브로커의 `DRIVER` 상수는 라우팅 회귀 방지용이라 그대로 뒀다.
- 첫 `update` 가 **실패**했다. 추적되지 않은 `.mypy_cache/`(17:04:58 생성)가 트리를 dirty 로 만들었다.
  `.gitignore` 에 추가한 뒤 3/3 OK 가 됐다.
- **생성 주체를 확정했다 — 리뷰 큐의 agy 리뷰 에이전트다** (같은 날 추적):
  - `ax-review-queue.service` 의 `WorkingDirectory` 는 `~/ax-cluster` 다. 17:02:07 에 내 커밋 `0941944` 를 꺼냈고, 17:02:33 부터 agy 퇴고를 돌렸다.
  - agy 기록(`~/.gemini/antigravity-cli/brain/c9ff11a8-…/logs/transcript.jsonl`):
    17:04:42 `.venv/bin/mypy master/client/setup_host.py` · 17:04:46 `.venv/bin/mypy -m master.client.setup_host`.
    캐시 경로를 지정하지 않아 17:04:58 에 작업 폴더에 `.mypy_cache` 를 만들었다.
  - 캐시 모듈(`master/client`·`client/init/*`·`bundle.py` 의 import)이 `setup_host.py` 의 의존 범위와 맞는다.
  - 배제한 것: 이 세션(17:04:02~17:11 도구 호출 0) · `pystatic`(임시 `--cache-dir` 를 쓴다) ·
    VS Code(2023 이후 실행 기록 없음) · 그 시각 저널의 다른 유닛.
  - 원인: `review_runner.agy_only` 가 `call_agy_why` 를 workdir 없이 부른다. 그래서 에이전트가 **마스터 라이브 트리**에서 명령을 실행한다.
  - 사용자 결정: 격리 트리에서 돌린다 → [#844](http://192.168.0.57:8080/issues/844)

## 리뷰 큐 격리 — #844 · `f3e3d96`

사용자 결정: 격리 트리, 마스터 로컬에서 직접 구현.

- **새로 만들지 않았다.** 이미 있던 `pinned_tree.pinned_worktree`(`#825`)와 `call_agy_why(workdir=)` 를 썼다.
  같은 조합을 `dismissal_candidates` 가 이미 쓰고 있었다.
- `review_runner.agy_only(workdir=)` 를 추가했다. `run_once` 의 기본 퇴고는 리뷰 커밋을 저장소 밖에 detached
  worktree 로 펼치고 그곳에서 agy 를 돌린다. 트리를 못 만들면 `ok=False` 로 끝낸다. **라이브 트리로 되돌아가지 않는다.**
- 검사:
  - `test_review_runner` 78/78. 신규 ⑮ 가 보는 것: 저장소 밖, 커밋에 고정, 트리 제거, 원본 status 불변, 트리 안 쓰기 로그, 생성 실패 시 failed.
  - 전수 186파일 실패 0 · 통합 181/181
  - [주의] 내가 쓴 ⑮ 가 처음 1건 실패했다. 흉내 산출물을 빈 디렉터리로 만들어 `git status` 에 안 보였다. 파일을 쓰게 고쳤다.
- **실물** (리뷰 큐가 `f3e3d96` 을 3회 시도):
  - 3회 모두 `/tmp/ax-pinned-*/tree` 에서 agy 가 돌았고, 끝나면 정리됐다(남은 것 0).
  - 마스터 `git status --porcelain --ignored` 는 실행 전과 같다(두 번 대조).
  - → #844 **완료**
- [주의] **격리는 작업 폴더만 옮긴다.** agy 가 절대경로(`~/ax-cluster/.venv/bin/python`, `find /home/sim`)도 썼다.
  접근을 막는 것은 아니다(`pinned_tree` 주석과 같다). 이번 3회에서 라이브 트리 쓰기는 0건이었다.

### 리뷰 자체는 실패했다 → 별 일감 둘

| 시각 | 시도 | 결과 |
|---|---|---|
| 18:19 → 18:23:20 | 1/3 | agy **타임아웃 236초**(한도 240) |
| 18:23:20 | — | `gemini-3.8-flash-medium` 쿨다운 **기본 600초** 기록(`.ax/agy/models.json`, 만료 18:33:20) |
| 18:29:23 | 2/3 · 3/3 | 「model cooldown 237s」로 같은 초에 즉시 실패 → **포기** |

- **오탐 근거**: 쿨다운 조건은 `agy_models._limited(evidence)` 다(정규식 `429|RESOURCE_EXHAUSTED|quota|rate.?limit`).
  1회째 agy 기록에 `RESOURCE_EXHAUSTED` 는 0건이다. 걸린 것은 에이전트가 grep 한 저장소 파일명
  `reports/121-…-agy-quota.md` 의 `quota` 다. 「resets in」 문구가 없어 기본 600초가 쓰였고, 그것이 만료 시각과
  정확히 맞는다. agy 로그 원문은 대조하지 못했다 → [#845](http://192.168.0.57:8080/issues/845)
- **타임아웃**: 10-22 에도 같은 실패가 있었다. 17:06 리뷰는 210초가 걸렸다. 이번 agy 는 리뷰 형식 예시를 찾느라
  `find /home/sim …` 같은 넓은 검색을 반복했다. 트윈 `AXCluster/reviews/` 는 git 밖이라 고정 트리에 없어서
  탐색이 늘었다는 가설이 있다 → [#846](http://192.168.0.57:8080/issues/846)

## 작업 기록 누락 (사용자 지적)

이 세션은 레드마인 노트·리포트만 남기고 `log_history` 를 한 번도 부르지 않았다. 사용자 지적:
*"작업 히스토리 인프라 서버에 올리지 못한거구나?"*. 그 뒤 4건을 올렸다(setup-host · Ollama · 35B/mypy · #844,
트윈 `history/` 15 → 19). 레드마인=무엇, 리포트=세션 서술, history=왜 — 자리가 다르다.

## 남은 것

- 비마운트 3개(ModularStage·NS·MotionForge)는 `.2` 등록부만 C 로 바꿨다. 클론은 마운트를 전환할 때 한다.
- 실제 Codex 셸 읽기·apply_patch·결과 회수를 `.2` 새 경로에서 확인하는 일 — 다음 파견에서 본다.
- [완료] **`.2` 시스템 node v24.11.1 → v24.22.2** (같은 날, 사용자 지시) — 리포트 129 방식 그대로:
  `latest-v24.x` MSI → `SHASUMS256` 대조 → scp 후 `.2` 재해시 일치(`9231bf64…b6b6d`) →
  `msiexec /qn /norestart` exit 0 → `node -v` v24.22.2 · npm 11.19.1 · 설치 파일 삭제.
  실행 중이던 node 는 Codex 런타임 내장본(별 경로)이라 영향 없음
- [완료] **UE 5.8.4 확인** (같은 날) — `Build.version` 5.8.4 CL 58902052 · `UnrealEditor.exe` 같은 CL ·
  `Build.bat` 있음 · `probe` `ue5 OK`. [주의] 런처 `LauncherInstalled.dat` 는 아직 `5.8.1` 로 남았다 —
  우리 빌드 경로는 `Build.bat` 을 직접 불러 이 기록을 읽지 않는다
- [완료] `.mypy_cache/` 생성 주체 — 리뷰 큐 agy (위 절). 근본 조치는 [#844](http://192.168.0.57:8080/issues/844)
- `setup-host` 의 윈도우 낡은 상주 판정은 영문·한글 `schtasks /v` 출력의 경로 문자열에 기댄다.
  리눅스(cron)는 배달이 표식으로 다시 쓰므로 해제 단계가 없다.
- 포기된 `f3e3d96` 리뷰를 다시 큐에 넣을지 — 사용자 미결정. #845·#846 전이면 같은 실패가 반복될 수 있다
- [#845](http://192.168.0.57:8080/issues/845) agy 한도 오탐 · [#846](http://192.168.0.57:8080/issues/846) 리뷰 타임아웃 — 신규, 미착수
