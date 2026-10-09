> 작성: Gemini (agy 1.3.2) · 실행: `master.work.gemini_report` · 2026-10-09 14:40 · 프로젝트 AXCluster
> 자료: src/master/work/lanes.py
> 검증: 인용 5개 내용 대조 (Claude, 2026-10-09) — 일치 5 · 불일치 0 · 범위 검사(자동): 인용 23개 — 범위 안 23 · 범위 밖 0 · 파일 없음 0
> 소요 102초 · 토큰 입력 56675 / 출력 14166 / 캐시읽기 12218
> [주의] agy status=ERROR: API error (attempt 1): UNAVAILABLE (code 503): No capacity available for model gemini-3.6-flash-high on the server — 본문이 불완전할 수 있다 (절 5개 온전 확인 · 경고 처리 도입 전 실행이라 사후 기재)
> [주의] 인용 링크가 위임 당시 스크래치 절대 경로(`file:///tmp/…`)를 가리킨다 — 열리지 않는다. 인용 텍스트 `src/…:줄` 은 저장소 `master/…` 와 같은 상대 경로다

# 작성 레인 체인 동작 정리

## 요약

1. 작성 레인은 `codex` → `agy` → `로컬` 순으로 동작하며, 클로드 한도를 마스터 작업에 온존하기 위한 자원 배분 정책에 기반합니다.
2. `run_chain`은 레인 실행 실패 또는 파일 기록 실패 시 다음 레인으로 넘어가며, 첫 레인 성공 시 또는 모든 레인 소진 시 종료합니다.
3. `run_one`은 프롬프트 생성을 못 하거나, 텍스트 생성 중 예외 발생, 파일 블록 형식 미준수, 요구 파일 일부 누락 시 실패로 판정합니다.

## 1. 기본 레인 순서 및 결정 근거

- **기본 레인 순서**: `codex` → `agy` → `qwen2.5-coder:14b`(로컬) 순서로 지정되어 있습니다 ([src/master/work/lanes.py:73](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L73)).
- **순서 결정 근거 (자원 배분)**:
  - 마스터 서버 수정 작업에 클로드 한도를 남겨두기 위해 1순위로 코덱스를 사용합니다 ([src/master/work/lanes.py:18-20](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L18-L20), [src/master/work/lanes.py:67-68](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L67-L68)).
  - 코덱스 소진 시 안티그래비티(`agy`)를 사용하며 ([src/master/work/lanes.py:19](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L19)), 코덱스 구독 한도 소진 시를 대비해 마지막 순서로 로컬 모델을 배치했습니다 ([src/master/work/lanes.py:68-69](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L68-L69)).
  - `claude`는 한도가 이 세션 및 마스터와 공용 자원이라 429 한도 초과 발생 시 여러 조각이 동시 중단되는 문제가 있어 체인에서 제외했습니다 ([src/master/work/lanes.py:5-7](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L5-L7), [src/master/work/lanes.py:21-22](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L21-L22)).

## 2. `run_chain` 전환 및 종료 조건

- **다음 레인 전환 조건**:
  - `run_one` 실행 결과 `r.ok`가 `False`인 경우 ([src/master/work/lanes.py:288-290](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L288-L290)).
  - `run_one`은 성공했으나 `write_back`을 통한 워커 디스크 쓰기에 실패하여 `bad` 목록이 발생하는 경우 `r.ok = False`로 변경 후 이동합니다 ([src/master/work/lanes.py:291-296](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L291-L296)).
- **체인 종료 조건**:
  - 특정 레인의 `run_one` 및 `write_back`이 모두 성공하여 `r.ok`가 `True`로 유지되면 성공 결과 `(r, tried)`를 반환하고 즉시 종료합니다 ([src/master/work/lanes.py:297-298](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L297-L298)).
  - 모든 레인이 실패하면 `(None, tried)`를 반환하며 종료합니다 ([src/master/work/lanes.py:299](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L299)).

## 3. `run_one` 실패 판정 케이스

1. **프롬프트 생성 실패**: 골조(`skeleton`)가 비어 있거나([src/master/work/lanes.py:169-170](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L169-L170)), `.py`와 다른 언어 파일이 한 조각에 섞여 `LaneError`가 발생하는 경우 ([src/master/work/lanes.py:120-123](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L120-L123), [src/master/work/lanes.py:214-217](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L214-L217)).
2. **생성 도중 예외 발생**: `generator`, `U.call`, 또는 `synth.generate` 호출 중 예외 및 CLI 오류가 발생하는 경우 ([src/master/work/lanes.py:229-240](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L229-L240)).
3. **출력 형식 미준수**: 응답 텍스트에서 `=== FILE:` 블록을 읽지 못해 `r.files` 파싱 결과가 빈 경우 ([src/master/work/lanes.py:244-246](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L244-L246)).
4. **일부 파일 누락**: 골조에서 요구한 파일 중 생성되지 않은 파일이 있어 `r.missing` 목록이 존재하는 경우 ([src/master/work/lanes.py:247-249](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L247-L249)).

## 확인 불가·한계

- `bundle._remote_write` 내부의 원격 써넣기 및 sha256 대조 검증 과정 ([src/master/work/lanes.py:37-38](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L37-L38), [src/master/work/lanes.py:257-258](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L257-L258)): 「확인 불가」 (`lanes.py` 밖 외부 모듈)
- `synth.generate` 브로커(8102) 연결 및 모델 상주 노드 간 통신 세부 메커니즘 ([src/master/work/lanes.py:13](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L13), [src/master/work/lanes.py:235-236](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L235-L236)): 「확인 불가」 (`lanes.py` 밖 외부 모듈)
- `wcommit` 및 층1 검사의 세부 판정 규정 ([src/master/work/lanes.py:40](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L40), [src/master/work/lanes.py:259](file:///tmp/claude-1000/-home-sim/3fdf52f0-b678-4ef0-bc1b-fd122c42901c/scratchpad/ax-gemini-lanes/src/master/work/lanes.py#L259)): 「확인 불가」 (`lanes.py` 밖 외부 모듈)
