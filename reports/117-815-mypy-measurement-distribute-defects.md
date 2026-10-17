# #815 ② — mypy 오탐 측정, 그리고 측정이 찾은 `distribute register` 결함 둘

2026-10-17 21:35 ~ · Claude · 마스터 담당 `codex`·워커 모드 `codex`는 바꾸지 않았다.

## mypy 오탐 측정 (코드 변경 없음)

pyflakes 때와 같은 방식으로 쟀다. 저장소 전체에 한 번 돌려 오탐 규모를 본다.

- mypy 1.11.2는 scratchpad의 별도 venv에 설치했다. 서비스가 쓰는 `.venv`에는 손대지 않았다.
- 실행 옵션은 `--python-executable .venv/bin/python --explicit-package-bases`, 대상은 테스트를 뺀 `master/` 209모듈이다.

| 모드 | 오류 | 파일 | 시간 | `call-arg` |
|---|---|---|---|---|
| 기본 | 309 | 79 | 48초 | 1 |
| `--check-untyped-defs` | 351 | — | 49초 | 1 |

- 오류 대부분은 추론이 만든 잡음이다.
  - 값 종류가 섞인 dict 리터럴을 `dict[str, object]`로 추론해 `object + int`·`object.append`로 걸린다(`session_usage` 19건 등).
  - Optional을 좁히지 못한다.
  - 같은 변수를 다른 타입으로 다시 쓴다(`cleanup.py`의 `plan`).
  - `**{"rework": True}`의 키를 추적하지 못한다.
  - 스텁의 한계(`codecs.escape_decode`)도 있다.
- ②가 노리는 종류인 `call-arg`는 저장소 전체에서 **오탐 0 · 실결함 1**이었다. 막는 대상을 `call-arg`로 좁히면 잡음 없이 쓸 수 있다.
  다른 종류까지 막으려면 pyflakes 때처럼 「골조 원본보다 늘어난 것만」 막는 방식이 필요하다.
- 결과를 #815 노트로 남겼다.

## 측정이 찾은 결함 — 같은 CLI 경로에 둘

`python -m master.work.distribute register …`가 쓰는 `stage_register`(`distribute.py:146`)에 결함이 둘 있다.
둘 다 #348(`53fc90f`)에서 매니페스트 기계장치를 걷을 때 남은 잔재다. 테스트가 없어서 지금까지 드러나지 않았다.

1. **`searcher=` 인자**(`call-arg`): `register_work`는 이 매개변수를 일부러 지웠는데, 호출하는 쪽에만 남았다.
   그래서 부르면 항상 TypeError가 난다.
2. **`t.manifest_degraded`**(`attr-defined`): `register.TaskResult`에는 `stem`·`task_id`·`error`만 있다.
   그래서 조각이 하나라도 등록되면 AttributeError가 난다.
   - 🔴 이 결함은 내 첫 측정 출력(`attr-defined` 50건)에 들어 있었는데, 분류하면서 놓쳤다.
     첫째를 고친 서브 에이전트가 다시 돌린 mypy에서 짚었다.

처리 방침은 사용자가 정했다: 「distribute 결함 고치고 로컬 서브에이전트로 진행해」, 둘째도 「함께 고치고 한 커밋」.

- 방향은 **되살리는 것이 아니라 남은 것을 지우는 것**이다. `searcher`를 `register_work`에 다시 넣지 않는다.
- 첫째 수정은 마스터가 대조했다.
  - diff는 2줄이다.
  - 새 `master/test_distribute.py`가 실물 `register_work` 시그니처에 `bind`해 인자를 검사한다. 새 코드에서 7/7, 옛 코드에서 1/5.
  - 전수 171파일 실패 0, mypy `call-arg` 0.
- 둘째 수정도 마스터가 대조했다. 루프 줄에서 `manifest_degraded` 부분만 지웠다.
  - 테스트에 실물 `TaskResult` 두 건(성공 `t-1` · 실패 `거절됨`)을 넣었다. 두 줄이 다 찍히고 `st.ok is False`인지 본다.
  - 결과: 새 코드에서 10/10. 둘째 수정만 되돌리면 3/5(AttributeError)로 실패한다.
  - 전수 171파일 실패 0, mypy의 `distribute.py` `call-arg`·`attr-defined` 0.
- 커밋 `f53a360`(코드 한 커밋).

## 남은 것

- 재기동은 하지 않았다. `distribute.py`는 CLI 진입점이라 상주 서비스가 불러오지 않는다.
- #815: mypy 도입 여부와 위치(층1 / ⑦), 막는 대상(`call-arg`만?) — 사용자 결정. 그 밖에 ① · ④ · ⑤ · ⑥ ·
  `logic.py` 재수출 · `test_runner` 간헐 실패.
- 이전 보고서의 남은 것은 그대로다.
