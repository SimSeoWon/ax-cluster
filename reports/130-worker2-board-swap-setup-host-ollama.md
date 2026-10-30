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
  1회째 agy 기록에 `RESOURCE_EXHAUSTED` 는 0건이다. 「resets in」 문구가 없어 기본 600초가 쓰였고, 그것이 만료
  시각과 정확히 맞는다 → [#845](http://192.168.0.57:8080/issues/845).
  [정정] 이 자리에 처음 적은 원인(「에이전트가 grep 한 저장소 파일명의 `quota`」)은 **틀렸다**. 그것은 대화
  기록(transcript)이었다. 쿨다운이 읽는 것은 agy CLI `--log-file` 이다. 아래 #845 절에서 바로잡았다.
- **타임아웃**: 10-22 에도 같은 실패가 있었다. 17:06 리뷰는 210초가 걸렸다. 이번 agy 는 리뷰 형식 예시를 찾느라
  `find /home/sim …` 같은 넓은 검색을 반복했다. 트윈 `AXCluster/reviews/` 는 git 밖이라 고정 트리에 없어서
  탐색이 늘었다는 가설이 있다 → [#846](http://192.168.0.57:8080/issues/846)

## agy 한도 오탐 — #845 · `faa2306`

사용자 결정: 범위는 판정식만, 마스터 로컬에서 직접 구현. 쿨다운 중 재시도 소진은 별 일감([#847](http://192.168.0.57:8080/issues/847))으로 뺐다.

- **진짜 원인** (CLI 로그를 직접 열어 확인):
  - agy CLI 정상 로그에 `quota` 가 **매번 3줄** 있다(`quota_manager.go` · `doRefreshQuota` · `quotaProject=`).
    10-30 실행 7회 모두 그랬고 `429`·`RESOURCE_EXHAUSTED` 는 0줄이었다.
  - glog 스레드 번호 열도 `\b429\b` 에 걸린다(`W1018 00:26:24.627900     429 cache.go`).
  - 그래서 **어떤 실패든**(타임아웃·빈 출력) 600초 쿨다운이 걸렸다. 저널 10-17~10-25 에도 「타임아웃 → model cooldown」 반복이 있다.
- 실제 소진 문구(10-18): `RESOURCE_EXHAUSTED (code 429): Individual quota reached. … Resets in 150h53m7s.`
- **변경**: `_limited` → `_LIMIT_RE`. 잡는 것은 `RESOURCE_EXHAUSTED`, `code|status|http 429`, `429 too many requests`,
  `quota reached|exceeded|exhausted`, `rate limited|limit exceeded|limit reached`, `too many requests` 다.
  맨 단어 `quota` 와 맨 숫자 `429` 는 뺐다.
- **실측 대조**: 기존 로그 248개 중 판정에 걸리는 로그가 **247 → 17** 이 됐고, 17개는 전부 10-18 실소진이다. 바꾸기 전에 돌려 봤다.
- 검사:
  - `test_agy_models` 19/19. 신규 3건: 정상 로그는 한도가 아니다 · 타임아웃+정상 로그에 쿨다운 없음 · 실소진 줄이면 쿨다운, 해제 150h53m7s.
  - 기존 픽스처 `"429 quota"` 5곳은 실측 형식이 아니라서 실측 문구로 바꿨다. **합성 문자열이 오탐을 가렸다.**
  - 전수 186파일 실패 0 · 통합 181/181
- [주의] 서비스에서 agy 실패 뒤 쿨다운이 안 걸리는 장면은 아직 못 봤다. 근거는 실측 로그 대조와 유닛이다.

## 리뷰 퇴고 타임아웃 — #846 · `674dfb4`

사용자 결정: 방향 A(프롬프트 규칙만, 한도 상향은 효과를 잰 뒤 판단), 마스터 로컬에서 직접 구현.

- **측정이 방향을 정했다**:
  - 10-01 이후 퇴고 260회: 성공 186 · **타임아웃 63(24%)** · 쿨다운 11. 성공 소요는 중앙값 48초 · 90% 지점 169초 · 최대 239초.
  - 10-11 이후 agy 기록 90건:

    | 소요 | 건수 | 평균 도구 호출 | 테스트 실행 |
    |---|---|---|---|
    | 200초 이상 | 37 | **25.5** | **23/37** |
    | 120초 미만 | 34 | 6.0 | 7/34 |

  - 프롬프트에는 이미 골격·예시·diff·선언부가 실려 있었다. 도구 사용 범위에 대한 지시만 없었다.
- **변경**: `review_gen._SCOPE_RULES` 를 규칙 목록에 넣었다. 내용: 근거는 DIFF·실측·파일 목록, 열람은 변경 파일·직접 호출부만,
  테스트·린트·빌드·전체 검색 금지, 다른 리뷰·예시를 찾지 않고 바로 출력.
- **해시 고정을 일부러 깼다**: `#815` 의 「intent=False 프롬프트는 바이트 단위로 같다」 해시 넷(`bp-*`)을 갱신했다.
  그 전에 「새 프롬프트에서 규칙 한 덩이만 빼면 옛 해시와 같다」를 넷 다 증명했다. `ex-*` 는 그대로다.
- 검사: `test_review_gen` 104/104(신규 `test_scope_rules`) · `test_review_runner` 78/78 · 전수 186파일 실패 0 · 통합 181/181
- **첫 적용 회차**(`674dfb4`, 19:23): 성공. 퇴고 **43초**, 도구 호출 5회(전부 `read_file`), 테스트·find 0회.
  [주의] **1건이다.** 분포 재측정은 다음 세션에 한다(사용자 결정: 지금 닫는다). 한도 상향(B)은 그 뒤에 판단한다 → #846 완료
- 같은 회차들에서 #845 도 확인했다: `faa2306` 리뷰가 19:00 에 56초로 성공했고, 쿨다운 기록은 없었다.

### 범위 밖에서 발견 → [#848](http://192.168.0.57:8080/issues/848)

19:08·19:11 의 agy 실행 두 건은 리뷰 큐가 아니라 **색인기 컨텍스트 합성**이었다(`[synth] … — agy · 입력 140405 토큰 · 186초`).
`context_synth/synth.py:586` 과 `ontology/synth.py:317` 이 agy 를 workdir 없이 부른다. `ax-indexer` 의 작업 폴더는
`~/ax-cluster` 라서 에이전트가 **라이브 트리에서** `.venv/bin/python -c …` · `unittest` · `test_verify_gate.py` 를 돌렸다.
이번에는 트리가 기준선과 같았다. #844 가 리뷰 큐만 고쳤고 같은 부류가 합성 경로에 남았다. 범위 규칙도 없다.

## 쿨다운 중 재시도 소진 — #847 · `6e94591`

사용자 결정: 분류 규칙은 리뷰 큐에만 둔다((가) — 공용 마커는 그대로), 마스터 로컬에서 직접 구현.

- **원인**: 리뷰 큐에는 한도 갈래(`QUOTA` — 시도 미소비·재큐)가 **이미 있었다.** 그런데 agy 쿨다운 문구
  `<모델>: model cooldown Ns` 에 한도 마커가 없어 `TRANSIENT` 로 떨어졌다. `drain` 은 같은 회차에서 곧바로 다시 집었다.
  → 18:29:23 에 2/3·3/3 이 같은 초에 소진돼 포기됐다.
- **변경**:
  - `review_queue.classify` 에 「model cooldown」→ `QUOTA` 를 로컬 규칙으로 넣었다. 같은 함수의 「실행파일 없음」이 선례다.
    공용 `revise.QUOTA_MARKERS` 에 넣으면 레인 전환(`llm_policy`)·작업 조각(`workmodel`)도 바뀌어 범위가 커진다.
  - `review_runner.drain` 은 한도 실패에서 그 회차를 멈춘다(`[리뷰큐] 한도 — 회차 중단`). 쿨다운은 모델 단위라 다음 항목도 같이 막히기 때문이다.
- 검사:
  - `test_review_queue` 51/51(실측 사유 → `QUOTA`)
  - `test_review_runner` 83/83. 신규 ⑯: 1건 처리 후 멈춤 · 시도 0 그대로 · 다음 항목 미접촉 · 로그 · 일반 실패는 종전대로 넘어감.
  - 전수 186파일 실패 0 · 통합 181/181
- [주의] **실서비스 실증은 하지 않았다.** 진짜 소진에서만 일어나는 경로다. 쿨다운을 일부러 걸면 그동안 실제 리뷰가 막힌다.
- 사용자 질문 *"지금 토큰 널널한데 왜 안된다는거야?"* (agy 화면: 주간 96.6% · 5시간 90.8% 남음):
  18:29 실패는 진짜 소진이 아니라 #845 의 오탐이었다. #845 뒤 리뷰 두 건(19:00·19:23)은 정상으로 성공했다. #847 은 앞으로 올 진짜 소진을 대비한 것이다.
  [주의] 내 보고가 「한도 문제」로 읽히게 썼다 — 오탐과 실소진을 처음부터 갈라 말했어야 했다.

## 작업 기록 누락 (사용자 지적)

이 세션은 레드마인 노트·리포트만 남기고 `log_history` 를 한 번도 부르지 않았다. 사용자 지적:
*"작업 히스토리 인프라 서버에 올리지 못한거구나?"*. 그 뒤 4건을 올렸다(setup-host · Ollama · 35B/mypy · #844,
트윈 `history/` 15 → 19 · #845 뒤 20 · #846 뒤 21 · #847 뒤 22). 레드마인=무엇, 리포트=세션 서술, history=왜 — 자리가 다르다.

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
- 포기된 `f3e3d96` 리뷰를 다시 큐에 넣을지 — 사용자 미결정(#846 반영 뒤라 다시 넣으면 새 규칙으로 돈다)
- [완료] [#845](http://192.168.0.57:8080/issues/845) agy 한도 오탐 (`faa2306`)
- [완료] [#846](http://192.168.0.57:8080/issues/846) 리뷰 타임아웃 (`674dfb4`) — 분포 재측정은 다음 세션
- [완료] [#847](http://192.168.0.57:8080/issues/847) 쿨다운 중 재시도 소진 (`6e94591`)
- [#848](http://192.168.0.57:8080/issues/848) 합성 경로 agy 격리·범위 규칙 — 신규, 미착수
