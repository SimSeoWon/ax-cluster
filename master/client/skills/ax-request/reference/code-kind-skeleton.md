# 3.6 🔴 `kind: code` 프로젝트 — `.py` 골조 (`#695`)

> `ax-request` SKILL.md 에서 옮긴 본문이다(`#890` T5 — 내용은 그대로, 제목 단계만 올렸다).


`.ax/config.json` 에 `tests` 가 있으면 그 프로젝트는 **`kind: code`** 다. 분산 작업은 **`.py` 만**
받는다 — 다른 확장자가 섞인 명세는 등재가 거절한다. 골조는 한 파일에 계약과 채울 자리를 같이 둔다:

    def compute(pose: dict, limit: float = 1.0) -> dict:
        # [DOC]    무엇을 왜 · 다른 조각과 어떻게 맞물리나      ← 보존
        # [PSEUDO] 여기를 채워라                              ← 휘발, 워커가 지운다
        raise NotImplementedError                            ← 문법상 유효해야 한다(게이트)

[중요] **이름·인자·기본값·반환 표기는 동결이다** — 워커가 바꾸면 층1 이 막는다. 새 비공개 함수는
워커가 추가해도 된다. 조각은 **파일 단위**다(`.h`/`.cpp` 짝이 없다).

[중요] **push 전에 골조 게이트를 돌린다 — UHT 자리의 Python 판이다.** 커밋한 **뒤** HEAD 를 잰다:

    py -3.12 -m axmaster.work.skeleton_gate --py webui/a.py webui/b.py     # 작업 디렉토리 = 체크아웃
    # 앞에 한 번: set PYTHONPATH=.ax\lib   (PowerShell: $env:PYTHONPATH=".ax\lib")

rc 0 이면 push 한다. rc 1 이면 **push 하지 말고 고친다** — 마스터도 파견 전에 **같은 판정을
강제로** 돌리고, 막히면 그 조각을 파견하지 않고 사유와 함께 종결한다(그러면 개선요청으로
다시 돌려야 한다). 보는 것: 구문 · `# [PSEUDO]` ≥1 · `[DOC]` ≥1 · `[FEEDBACK]` 0.
