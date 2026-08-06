# worker

BC-250 추론 노드(#1, #2)의 설정/래퍼가 들어갈 자리.

> ⚠️ **이름 주의** — 이 디렉터리 이름은 "worker" 지만, AgentTest 코드의 `worker/`(윈도우에서 도는
> 작업자 하네스)와는 **다른 것**이다. 여기는 **추론 노드** 쪽이다. `../PLAN.md` §4.1 참조.

## 여기 두지 않는 것 — 마스터/워커 경계

노드는 **순수 추론 엔드포인트**로 유지한다. 상태도 판단 로직도 갖지 않는다.

| 여기(worker/) | 마스터(master/) |
|---|---|
| Ollama + Vulkan 구동, 모델 적재 | 생존 감시·페일오버·라우팅 |
| 노드 OS/드라이버/메모리 튜닝 | 요청 정규화·응답 후처리·검증 |
| — | 컨텍스트 매니페스트 조립 |

**추론 클라이언트 래퍼는 마스터 몫이다**(`../master/README.md`). 노드에 에이전트 코드를 심으면
일회용성이 깨지고, 검증에 필요한 태스크 컨텍스트가 여기 없다.
생존 신호도 노드가 따로 보내지 않는다 — `stream:true` 의 토큰 청크가 그대로 하트비트다(`../PLAN.md` §6.2).

## BC-250 #1 — ✅ 가동 중 (192.168.0.43)

2026-08-06 기준 실측 검증 완료. 상세 이력은
`~/bc250-backup-staging/reports/24-ttm-gtt-tuning-headless-cluster-link.md`(인프라·속도),
`25-model-quality-comparison-14b-vs-35b.md`(모델 품질).

**환경**

| 항목 | 값 |
|---|---|
| OS | Fedora 43, **헤드리스**(`multi-user.target`) |
| 커널 / Mesa | 6.17.1-300 / 25.3.6 (`AMD BC-250 (RADV GFX1013)`) |
| GPU / CPU | **38/40 CU** · **8c/16t** · SMU OC 3500MHz |
| 메모리 | 시스템 14 GiB, VRAM carve-out 0.5 GiB, **GTT 15.10 GiB** |
| Ollama | 0.32.5, `OLLAMA_VULKAN=1` + `OLLAMA_IGPU_ENABLE=1`, 가용 15.6 GiB |

**핵심 설정 (재현 시 필수)**

- `UMA_SIZE=512` — BIOS UMA 는 상한이 아니라 **하한**이라 작게 잡아야 GTT 가 커진다.
  [`fanoush/bc250_memcfg`](https://github.com/fanoush/bc250_memcfg) 로 리눅스에서 CMOS 직접 변경(BIOS 플래시 불요)
- 커널 파라미터 `ttm.pages_limit=3959290 ttm.page_pool_size=3959290`
- `RADV_DEBUG=nohiz` (안정화), `OLLAMA_HOST=0.0.0.0:11434`
- ROCm 은 gfx1013 미지원이라 자동 드롭됨 — **Vulkan 전용이 정상**

**네트워크**

- `11434/tcp` 는 방화벽에서 **192.168.0.57(마스터)에서만** 허용. 다른 클라이언트 추가 시 rich rule 필요.
- API 는 stateless 로 호출한다 — Ollama `/api/generate` 의 `context` 필드를 재사용하지 않는다.
- **`35B-A3B` 호출 시 `"think": false` 필수** — 없으면 사고 과정을 출력해 토큰을 낭비한다.

**모델**

| 용도 | 모델 | 비고 |
|---|---|---|
| 코드 생성 | `qwen2.5-coder:14b` | 8.9GB, 49/49 레이어 GPU |
| 컨텍스트 쿠킹 | `hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M` | 13GB, 42/42 레이어 GPU |

동시 상주 불가(`MAX_LOADED_MODELS=1`, 8.9+13GB > 15.6GB) — 전환 비용 36초.

## BC-250 #2 — 미구성 (의도적 순차 진행)

**#1 을 완성한 뒤 그 결과를 복제해 구성·연결한다** (사용자 확정 2026-08-07).
"도착/설치 여부 미확인"이 아니라 **순서상 나중**이다.

- 셋업 가이드: `sim@192.168.0.43:~/bc250-backup-staging/reports/18-second-board-setup-guide.md`
- #1 에서 확정된 설정을 그대로 적용한다 — 헤드리스 · UMA 512MB · TTM `pages_limit=3959290` ·
  거버너 `min=350` · Ollama+Vulkan(`RADV_DEBUG=nohiz`) · 방화벽 `192.168.0.57` 한정 ·
  `/etc/sudoers.d/bc250-power`
- 구성 후 **모델을 보드별로 고정 배정**한다: `#1 = qwen2.5-coder:14b(생성)` / `#2 = 35B-A3B(쿠킹)`
  — 전환 비용 36초를 없애기 위함(`../PLAN.md` §4.4)

⚠️ **그때까지 `../PLAN.md` §4.5 의 "노드 수만큼 병렬"은 실효가 없다** — 보드 1대라 직렬이다.

## 알려진 리스크

- **GPU 크래시 = 호스트 하드 행.** 단일 APU 라 드라이버가 GPU 를 리셋할 수 없어 원격 복구가 불가능하다.
  무인 운영 시 워치독 + 원격 전원 재투입 수단이 필요하다.
- **장시간 안정성 미검증** — 단기(30분/65사이클)는 통과했다(성공률 100%, tok/s 26.57±0.27,
  커널 오류 0, GTT 고정). 다만 시스템 `MemAvailable` 이 -620MB 단조 감소한 관찰이 남아 있어
  **수 시간 이상 재검증 전에는 무인 상시가동을 판단하지 말 것**. 상세 = 리포트 24 부록 B.
- prefill 이 구조적 약점 — 긴 컨텍스트 주입 설계("소스=정답")와 정면으로 부딪힌다.
- **절전모드 복귀 불가**(SMU 한계) — "켜짐 아니면 꺼짐"뿐이라 유휴 80W 가 대기 비용으로 고정된다.

상세 계획: `../PLAN.md`
