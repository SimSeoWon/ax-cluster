# worker

BC-250 추론 노드(#1, #2)의 설정/래퍼가 들어갈 자리.

> ⚠️ **이름 주의** — 이 디렉터리 이름은 "worker" 지만, AgentTest 코드의 `worker/`(윈도우에서 도는
> 작업자 하네스)와는 **다른 것**이다. 여기는 **추론 노드** 쪽이다. `../PLAN.md` §4.1 참조.

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

## BC-250 #2 — 미확인

도착/설치 여부 미확인. 확인 후 #1 과 동일 절차 적용 예정
(단 **CU 언락 안정 수치는 개체별 실리콘 편차**가 있어 재탐색 필요 — #1 은 38/40).

## 알려진 리스크

- **GPU 크래시 = 호스트 하드 행.** 단일 APU 라 드라이버가 GPU 를 리셋할 수 없어 원격 복구가 불가능하다.
  무인 운영 시 워치독 + 원격 전원 재투입 수단이 필요하다.
- **장시간 안정성 미검증** — 현재까지 수 분 단위 테스트만 했다. 클러스터에 물리기 전 필수 관문.
- prefill 이 구조적 약점 — 긴 컨텍스트 주입 설계("소스=정답")와 정면으로 부딪힌다.

상세 계획: `../PLAN.md`
