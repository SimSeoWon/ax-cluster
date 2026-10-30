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
  `.gitignore` 에 추가한 뒤 3/3 OK 가 됐다. **누가 만들었는지는 확정하지 못했다.** 저장소에서 mypy 를
  쓰는 곳은 `master/pystatic` 이고, 그 시각에 내가 저장소에서 돌린 것은 없다.

## 남은 것

- 비마운트 3개(ModularStage·NS·MotionForge)는 `.2` 등록부만 C 로 바꿨다. 클론은 마운트를 전환할 때 한다.
- 실제 Codex 셸 읽기·apply_patch·결과 회수를 `.2` 새 경로에서 확인하는 일 — 다음 파견에서 본다.
- [완료] **`.2` 시스템 node v24.11.1 → v24.22.2** (같은 날, 사용자 지시) — 리포트 129 방식 그대로:
  `latest-v24.x` MSI → `SHASUMS256` 대조 → scp 후 `.2` 재해시 일치(`9231bf64…b6b6d`) →
  `msiexec /qn /norestart` exit 0 → `node -v` v24.22.2 · npm 11.19.1 · 설치 파일 삭제.
  실행 중이던 node 는 Codex 런타임 내장본(별 경로)이라 영향 없음
- UE 5.8.4 업데이트 완료 확인(`probe` 로 `Build.version` 재측정)
- `.mypy_cache/` 생성 주체
- `setup-host` 의 윈도우 낡은 상주 판정은 영문·한글 `schtasks /v` 출력의 경로 문자열에 기댄다.
  리눅스(cron)는 배달이 표식으로 다시 쓰므로 해제 단계가 없다.
