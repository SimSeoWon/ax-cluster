"""소스 파일을 인코딩에 상관없이 읽는다.

[중요] **이 모듈이 있는 이유 — 실측 근거가 있다.**

`watcher-internals.md` 의 σ 계열 결정 로그가 기록해 둔 사고:

> 한국 스튜디오 .h/.cpp/.md 가 CP949(MS949) 저장인데 발췌 읽기 3곳이
> `read_text(utf-8, errors='ignore')` 고정 → CP949 한글 바이트를 조용히 *버려* mojibake.

**우리 저장소에서 재측정(2026-08-08)**: `ModularStage/repo/Source` 의 C++ 소스 **1,654개 중
723개(44%)가 유효한 UTF-8 이 아니고, 그 723개 전부 CP949 로 읽힌다.**

```
utf-8, errors=replace : '// ĳ���� ����â������ �����ִ� ������ ����'
cp949                 : '// 캐릭터 선택창에서만 보여주는 간단한 정보'
```

**무엇에 영향이 있고 없는지도 실측했다:**

- **클래스 그래프는 영향 없다** — 식별자가 ASCII 라 tree-sitter 파싱 결과가 동일하다
  (같은 파일을 두 방식으로 파싱해 클래스·부모·메서드 수가 일치함을 확인)
- [중요] **컨텍스트 MD 합성은 치명적이다** — 한글 주석이 그 코드의 *의도*를 담은 가장 밀도 높은
  신호인데, mojibake 를 LLM 에 넣으면 문서가 조용히 쓰레기가 된다. 에러는 안 난다

**폴백 순서**: UTF-8 strict → CP949 → UTF-8 `errors="replace"`.
마지막 단계는 **손실이 확정된 경로**라 `Decoded.degraded` 로 표시한다 — 호출자가 분모를
보고할 수 있게 한다(원본은 카나리 로그로 남겼고, 우리는 통계 객체로 들고 다닌다).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 시도 순서. CP949 가 UTF-8 뒤인 것이 중요하다 — 반대로 하면 UTF-8 한글이 CP949 로도
# 그럴듯하게 디코드돼(둘 다 바이트 상 유효할 수 있다) 조용히 다른 글자가 된다.
UTF8 = "utf-8"
CP949 = "cp949"
REPLACE = "utf-8/replace"


@dataclass(frozen=True)
class Decoded:
    text: str
    encoding: str          # UTF8 · CP949 · REPLACE

    @property
    def degraded(self) -> bool:
        """문자가 유실됐는가. [중요] True 면 LLM 에 넣기 전에 한 번 의심할 것."""
        return self.encoding == REPLACE

    @property
    def fallback(self) -> bool:
        """UTF-8 이 아니었는가. 유실은 없지만 저장소의 인코딩 혼용 신호다."""
        return self.encoding != UTF8


def decode(raw: bytes) -> Decoded:
    """바이트 → 텍스트. 파일 없이 테스트할 수 있게 분리했다."""
    for enc in (UTF8, CP949):
        try:
            return Decoded(raw.decode(enc), enc)
        except UnicodeDecodeError:
            continue
    return Decoded(raw.decode(UTF8, errors="replace"), REPLACE)


def read(path: Path) -> Decoded | None:
    """파일 → 텍스트. **읽을 수 없으면 `None`** — 빈 문자열로 위장하지 않는다.

    빈 문자열을 돌려주면 "내용이 없는 파일" 과 "못 읽은 파일" 이 구분되지 않고, 그게
    합성기에서 *빈 문서를 정상 산출물로* 만드는 경로가 된다.
    """
    try:
        return decode(path.read_bytes())
    except OSError:
        return None


@dataclass
class EncodingTally:
    """읽은 파일들의 인코딩 분포. 통계 객체에 얹어 분모를 함께 보고한다."""

    utf8: int = 0
    cp949: int = 0
    degraded: int = 0
    unreadable: int = 0

    def add(self, d: Decoded | None) -> Decoded | None:
        if d is None:
            self.unreadable += 1
        elif d.encoding == UTF8:
            self.utf8 += 1
        elif d.encoding == CP949:
            self.cp949 += 1
        else:
            self.degraded += 1
        return d

    @property
    def summary(self) -> str:
        parts = [f"utf-8 {self.utf8}"]
        if self.cp949:
            parts.append(f"cp949 {self.cp949}")
        if self.degraded:
            parts.append(f"[중요] 유실 {self.degraded}")
        if self.unreadable:
            parts.append(f"[중요] 못 읽음 {self.unreadable}")
        return " · ".join(parts)
