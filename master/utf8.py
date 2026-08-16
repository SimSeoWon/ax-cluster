"""콘솔 출력 UTF-8 강제 — 원전 이식 (소 3.5.5 · `#181`).

원전이 고친 것: **한글 윈도우 콘솔(CP949)** 에서 em-dash·박스드로잉·이모지를 `print` 하면
`UnicodeEncodeError` 로 **로그 한 줄 없이 프로세스가 즉사**한다.

## [주의] 이 칸을 한 번 「해당 없음」으로 미뤘다 — 그 판단이 틀렸다

2026-08-14 에 *"마스터는 systemd 아래 stdout=utf-8 이고 이모지가 이미 정상 출력된다 →
리눅스에 넣는 것은 카고 컬트"* 로 보류했다. [중요] **규칙을 거꾸로 적용한 것이다.** 마일스톤
최우선 규칙은 *"원전에 있는 장치는 **재지 않고 옮긴다** — 원전은 이미 값을 치렀다"* 인데,
나는 *"우리에게 지금 그 실패가 있는가"* 를 재고 있었다(그건 **새로 만들 때**의 규칙이다).

그리고 전제도 바뀌었다 — **2026-08-16 에 `.33`(한글 윈도우)로 파이썬 페이로드를 배달했다**
(`#137`). 우리 코드가 CP949 콘솔에서 도는 자리가 실제로 생겼고, 그 코드의 메시지에는
[중요]·[주의]·em-dash 가 가득하다.

## [중요] 비용이 0에 가깝다는 것이 판단의 절반이다

    리눅스   이미 UTF-8 이라 **아무 일도 일어나지 않는다** (no-op)
    윈도우   즉사를 막는다

*"우리에게 그 실패가 없다"* 가 *"넣지 말라"* 는 뜻이 되려면 넣는 비용이 있어야 하는데,
여기서는 없다. [주의] 그리고 없는 실패를 막는 가드와 **카고 컬트는 다르다** — 카고 컬트는
*"왜 있는지 모르고 베끼는 것"* 이고, 여기는 이유가 한 줄로 설명된다.

## 쓰는 법 — [중요] 임포트 부작용으로 만들지 않는다

`enforce()` 를 **진입점에서 부른다.** 임포트만으로 전역 스트림을 바꾸면, 이 모듈을 우연히
끌어온 다른 코드의 출력까지 조용히 바뀐다.
"""
from __future__ import annotations

import sys

TARGET = "utf-8"


def _needs(stream) -> bool:
    """이미 UTF-8 이면 건드리지 않는다. [중요] 판정 못 하면 **건드리지 않는다**(보수적)."""
    enc = (getattr(stream, "encoding", "") or "").lower().replace("_", "-")
    return bool(enc) and enc not in ("utf-8", "utf8")


def enforce(*, streams=None) -> list:
    """`stdout`/`stderr` 를 UTF-8 로 맞춘다. **바꾼 스트림 이름 목록**을 돌려준다.

    [중요] **실패해도 예외를 올리지 않는다** — 인코딩을 고치다 프로그램을 죽이면 본말전도다.
    다만 조용히 넘기지도 않는다: 못 바꾼 것은 목록에 안 들어가므로 호출자가 셀 수 있다.

    [주의] `errors` 를 `replace` 로 두지 않는다. 치환은 **깨진 글자를 성공처럼** 보이게 만들고,
    그건 이 저장소가 가장 경계하는 「조용히 틀리는 것」이다(`#180` 에서 같은 이유로 치환을
    거부했다). 인코딩이 맞으면 치환할 일이 없다.
    """
    changed = []
    for name in (streams or ("stdout", "stderr")):
        st = getattr(sys, name, None)
        if st is None or not _needs(st):
            continue
        recfg = getattr(st, "reconfigure", None)
        if recfg is None:
            continue                      # 파이썬 3.7 미만·감싼 스트림 — 건드리지 않는다
        try:
            recfg(encoding=TARGET)
            changed.append(name)
        except (OSError, ValueError):
            continue                      # 못 바꿨다 — 목록에 안 넣는다(호출자가 안다)
    return changed
