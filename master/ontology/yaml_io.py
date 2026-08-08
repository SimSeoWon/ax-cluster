"""온톨로지 YAML 읽기·쓰기 (소 1.3.4) — **PyYAML 의존성 0**.

원본: `watcher/ontology_yaml_dump.py` 의 직렬화부 + `ontology_md_parse.py` 의 수제 리더.

## 왜 PyYAML 을 안 쓰나

원본 결정(η.2, 2026-05-23): *"stdlib only 수동 직렬화 — dist 배포 패키지 의존성 증가 회피,
**우리 산출물 형식만 지원**"*. 우리는 배포 zip 이 없지만 그 결정을 그대로 따른다:

- 🔴 **일반 YAML 파서가 아니다.** 외부 입력을 받는 곳이 아니라 **우리가 쓴 것을 우리가 읽는**
  닫힌 회로다. 여기에 완전한 파서를 두면 검증 범위가 무한히 넓어진다
- 이미 같은 판단을 한 곳이 있다 — `context_search/documents.py` 의 프론트매터 파서도
  정규식 기반이고, *"생성하는 쪽과 짝이 맞춰져 있으므로 '개선' 하면 오히려 어긋난다"* 고
  적어 뒀다. 같은 이유다

## 이 모듈이 지키는 것

`dump` → `load` 왕복이 **값을 보존**해야 한다. 그게 이 모듈의 유일한 계약이고, 테스트가
그것만 확인한다. 예쁜 YAML 을 만드는 것이 목적이 아니다.
"""
from __future__ import annotations

import re
from pathlib import Path

# 따옴표 없이 안전한 단일 라인 문자열. **원본 그대로** — 넓히면 우리가 쓴 것을 우리가 못 읽는다.
_PLAIN_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_./\-]*$")
_NEEDS_QUOTE = set(":#&*!|>%@`,{}[]'\"\\")
_RESERVED = {"null", "true", "false", "yes", "no", "on", "off", "~"}


def scalar(value) -> str:
    """단일 값 → YAML 스칼라. 멀티라인은 호출자(`dump`)가 블록으로 처리한다."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if not s:
        return "''"
    if "\n" in s:
        return ""
    reserved = s.lower() in _RESERVED
    if _PLAIN_SAFE.match(s) and not reserved:
        return s
    if reserved or any(c in _NEEDS_QUOTE for c in s) or s[0] in " -?:" or s[-1] == " ":
        return "'" + s.replace("'", "''") + "'"
    return s


def _block(s: str, indent: int) -> str:
    """멀티라인 → `|` 블록 스칼라. 줄바꿈을 보존한다(`|-` 가 아니라 `|`)."""
    prefix = " " * indent
    return "|\n" + "\n".join(prefix + ln for ln in s.split("\n"))


def dump(data, indent: int = 0) -> str:
    """dict/list/스칼라 → YAML 텍스트. **원본 구조 그대로.**"""
    sp = " " * indent
    if isinstance(data, dict):
        if not data:
            return "{}\n"
        out = []
        for k, v in data.items():
            key = scalar(k)
            if isinstance(v, dict):
                out.append(f"{sp}{key}: {{}}" if not v else f"{sp}{key}:")
                if v:
                    out.append(dump(v, indent + 2).rstrip("\n"))
            elif isinstance(v, list):
                out.append(f"{sp}{key}: []" if not v else f"{sp}{key}:")
                if v:
                    out.append(dump(v, indent + 2).rstrip("\n"))
            elif isinstance(v, str) and "\n" in v:
                out.append(f"{sp}{key}: {_block(v, indent + 2)}")
            else:
                out.append(f"{sp}{key}: {scalar(v)}")
        return "\n".join(out) + "\n"
    if isinstance(data, list):
        if not data:
            return f"{sp}[]\n"
        out = []
        for item in data:
            if isinstance(item, dict):
                lines = dump(item, indent + 2).rstrip("\n").splitlines()
                if not lines:
                    out.append(f"{sp}-")
                    continue
                out.append(f"{sp}- {lines[0].lstrip()}")
                out.extend(lines[1:])
            elif isinstance(item, list):
                out.append(f"{sp}-")
                out.append(dump(item, indent + 2).rstrip("\n"))
            elif isinstance(item, str) and "\n" in item:
                out.append(f"{sp}- {_block(item, indent + 2)}")
            else:
                out.append(f"{sp}- {scalar(item)}")
        return "\n".join(out) + "\n"
    if isinstance(data, str) and "\n" in data:
        return _block(data, indent) + "\n"
    return f"{scalar(data)}\n"


# ── 읽기 ──────────────────────────────────────────────────────────
# 🔴 **우리가 쓴 형식만 읽는다.** 앵커·태그·플로우 스타일·복수 문서는 지원하지 않는다 —
# 우리가 쓰지 않으므로 읽을 일이 없고, 지원하면 검증 범위만 넓어진다.

_KEY_RE = re.compile(r"^(\s*)([A-Za-z_][\w./\- ]*|'[^']*'):\s*(.*)$")
_ITEM_RE = re.compile(r"^(\s*)-\s?(.*)$")


def _unscalar(s: str):
    """스칼라 텍스트 → 파이썬 값. `dump` 가 쓴 것만 되돌린다."""
    s = s.strip()
    if s == "" or s == "null" or s == "~":
        return None if s else ""
    if s == "true":
        return True
    if s == "false":
        return False
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1].replace("''", "'")
    if s in ("[]", "{}"):
        return [] if s == "[]" else {}
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _parse(lines: list[str], i: int, indent: int):
    """`lines[i:]` 를 `indent` 수준에서 파싱해 (값, 다음 인덱스) 를 돌려준다."""
    # 리스트인지 매핑인지 첫 유효 줄로 판정한다.
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return None, i
    if _ITEM_RE.match(lines[i]) and len(lines[i]) - len(lines[i].lstrip()) >= indent:
        out_list = []
        while i < len(lines):
            ln = lines[i]
            if not ln.strip():
                i += 1
                continue
            cur = len(ln) - len(ln.lstrip())
            m = _ITEM_RE.match(ln)
            if not m or cur < indent:
                break
            rest = m.group(2)
            if not rest:
                val, i = _parse(lines, i + 1, indent + 2)
                out_list.append(val)
                continue
            km = _KEY_RE.match(rest)
            if km:                                   # `- key: value` — 매핑 항목
                sub = [(" " * (cur + 2)) + rest]
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= cur:
                        break
                    sub.append(nxt)
                    i += 1
                val, _ = _parse(sub, 0, cur + 2)
                out_list.append(val)
                continue
            out_list.append(_unscalar(rest))
            i += 1
        return out_list, i

    out: dict = {}
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        cur = len(ln) - len(ln.lstrip())
        if cur < indent:
            break
        m = _KEY_RE.match(ln)
        if not m:
            break
        key, rest = m.group(2).strip().strip("'"), m.group(3)
        if rest == "|":                              # 블록 스칼라
            i += 1
            body = []
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= cur:
                    break
                body.append(nxt[cur + 2:] if len(nxt) > cur + 2 else "")
                i += 1
            out[key] = "\n".join(body).rstrip("\n")
            continue
        if rest == "":                               # 중첩 (dict 또는 list)
            val, i = _parse(lines, i + 1, cur + 1)
            out[key] = val if val is not None else {}
            continue
        out[key] = _unscalar(rest)
        i += 1
    return out, i


def load(text: str):
    """YAML 텍스트 → 파이썬 값. **`dump` 가 쓴 것만** 되돌린다."""
    lines = [ln.rstrip("\n") for ln in (text or "").splitlines()
             if not ln.lstrip().startswith("#")]
    val, _ = _parse(lines, 0, 0)
    return val if val is not None else {}


def read(path: Path):
    """파일 → 값. 없거나 못 읽으면 `None` — 빈 dict 로 위장하지 않는다."""
    try:
        return load(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def write(path: Path, data) -> bool:
    """값 → 파일. **내용이 같으면 쓰지 않는다** (mtime 도 안 건드린다).

    원본의 `skip_unchanged` 와 같은 취지다 — 매 폴링마다 같은 것을 다시 써서 mtime 을
    흔들면 그걸 입력으로 삼는 dirty 판정이 영원히 재합성을 부른다.
    """
    text = dump(data)
    if path.is_file():
        try:
            if path.read_text(encoding="utf-8", errors="replace") == text:
                return False
        except OSError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)                    # 원자적 — 반쯤 쓰인 yaml 을 색인기가 읽지 않게
    return True
