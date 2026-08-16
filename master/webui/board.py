"""도메인 게시판 — 생성·채팅·갱신·활성화 ([중요] **원전 그대로 복각**, 사용자 지시 2026-08-13).

> *"생성·삭제·채팅까지 원전대로 살려"*

원전 `domain_viewer_routes.py`(555줄)의 mutation 경로다. 처음엔 내가 *"우리 온톨로지 편집 규칙과
충돌한다"* 며 읽기 전용으로 뺐는데, **사용자가 감안하고 살리라고 결정했다.**

## [중요] 게시판은 온톨로지 패키지가 **아니다** — 이걸 헷갈리면 안 된다

    /api/v1/domains          → `context/_domains/*.md`      사람이 읽고 쓰는 **도메인 문서**
                                (frontmatter `status: draft|active` · source_documents · tags)
    /api/v1/ontology/domains → `ontology/domains/*/domain.yaml`  기계가 쓰는 **온톨로지 패키지**

우리 `domain.yaml` 이 주석에 *"사람 편집 위치 = `_domains/<D>.md`"* 라고 적어 둔 그 관계다.
즉 게시판이 쓰는 것은 **MD 초안**이고, 온톨로지 YAML 은 건드리지 않는다.

[중요] **그래서 편집 잠금 규칙과 부딪히지 않는다.** `protected`/`verified` 는 온톨로지 항목의
속성이고, 게시판은 그 위층의 사람 문서를 만진다. (내가 처음에 이 구분을 못 하고 통째로 막았다.)

## [주의] 원전과 다른 것 — 우리 인프라라서

    LLM 호출     원전 `_call_llm_for_chat` → 우리 레인(`agy` → `claude` 폴백, `layer2_verify`)
    관련 문서 검색 원전은 Chroma 직접 query → 우리 `ContextSearch`(벡터+BM25 융합)
    활성화 색인   원전은 서버가 색인을 들고 upsert → [중요] 우리 색인기는 **별도 프로세스**다.
                 파일을 쓰면 `ax-indexer.path`(inotify)가 알아서 집어간다 — 웹이 색인을
                 직접 만지지 않는다. 응답의 `indexed` 는 *"색인기에 맡겼다"* 는 뜻이다

## [중요] 쓰기 안전장치 (원전에 없던 것 — 우리 규칙)

- **이름 검사 + 경로 이중 확인**: 구분자·`..`·제어문자를 막고, 만든 경로가 디렉토리 안인지
  `resolve().relative_to()` 로 다시 본다. [주의] **한글 이름은 허용한다** — 원전이 그랬고, 막아야
  하는 것은 경로 이탈이지 문자 종류가 아니다
- `_` 로 시작하는 파일은 **손대지 않는다** — `_overview.md`·`_unassigned.md` 같은 관리 문서다
- [중요] **원자적 쓰기**(tmp → replace). 반쯤 쓰인 문서를 색인기가 집어가면 안 된다
- [중요] **온톨로지 디렉토리는 절대 쓰지 않는다** — 이 모듈은 `context/_domains/` 밖으로 나가지 않는다
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

# [중요] **한글 이름을 허용한다** — 원전은 경로 위험문자(`\/:*?"<>|`)만 걸렀고 한글 파일명을 그대로
#    썼다. 내가 `[A-Za-z0-9_-]` 로 좁혔더니 **한글 도메인명이 통째로 날아가** 파일명이 `domain`
#    이 됐다(실측 2026-08-13). 리눅스에서 한글 파일명은 문제가 아니다.
#    막아야 하는 것은 **경로 이탈**이므로 그것만 막는다(구분자·`..`·제어문자·앞뒤 공백/점).
_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _name_ok(name: str) -> bool:
    n = (name or "").strip()
    if not n or len(n) > 80 or n != name:
        return False
    if n.startswith("_") or n.startswith(".") or n.endswith("."):
        return False
    if ".." in n or _BAD_CHARS.search(n):
        return False
    return True


CHAT_DIR = ".chat"
FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class BoardError(RuntimeError):
    """게시판 요청을 처리할 수 없다. [중요] 사유를 화면에 그대로 보인다."""


# ── 경로 ────────────────────────────────────────────────────────────────────────

def domains_dir(paths) -> Path:
    return paths.context / "_domains"


def chat_dir(paths) -> Path:
    d = domains_dir(paths) / CHAT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def md_path(paths, name: str) -> Path:
    """[중요] 이름을 검사하고 나서만 경로를 만든다. `_` 시작은 관리 문서라 거부."""
    if not _name_ok(name):
        raise BoardError(f"쓸 수 없는 도메인 이름이다: {name!r} "
                         f"(경로 구분자·`..`·제어문자 금지, `_`/`.` 로 시작 금지 — 관리 문서 보호)")
    d = domains_dir(paths)
    p = (d / f"{name}.md")
    # [중요] 이중 방어 — 이름 검사를 통과해도 실제 경로가 디렉토리 밖이면 거부한다
    try:
        p.resolve().relative_to(d.resolve())
    except ValueError:
        raise BoardError(f"디렉토리 밖을 가리킨다: {name!r}") from None
    return p


def _atomic_write(p: Path, text: str) -> None:
    """[중요] 원자적. 색인기(inotify)가 반쯤 쓰인 문서를 집어가면 안 된다."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


# ── frontmatter (원전 `_parse_frontmatter` 등가 — 우리 문서 형식 그대로) ──────────

def parse_front(content: str) -> dict:
    """`---` 블록 → dict. [중요] 우리 문서의 실제 형식만 읽는다(리스트 두 표기 모두)."""
    m = FRONT.match(content or "")
    if not m:
        return {}
    out: dict = {}
    key = None
    for raw in m.group(1).splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("  - ") and key:
            item = line[4:].strip()
            if item.startswith("#"):
                continue
            # `- Name: path` (related_classes) 도 있다 — 앞쪽만 쓴다
            out.setdefault(key, []).append(item)
            continue
        m2 = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not m2:
            continue
        key, val = m2.group(1), m2.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            out[key] = [x.strip() for x in inner.split(",") if x.strip()]
        elif val:
            out[key] = val
        else:
            out[key] = []
    return out


def extract_body(content: str) -> str:
    m = FRONT.match(content or "")
    return (content or "")[m.end():] if m else (content or "")


# ── 목록 · 상세 (원전 모양 그대로) ───────────────────────────────────────────────

def list_board(paths) -> dict:
    d = domains_dir(paths)
    if not d.is_dir():
        return {"domains": [], "counts": {"draft": 0, "active": 0}}
    domains: list = []
    counts = {"draft": 0, "active": 0}
    for f in sorted(d.glob("*.md")):
        if f.name.startswith("_"):
            continue                              # 관리 문서는 게시판에 올리지 않는다
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta = parse_front(content)
        status = str(meta.get("status") or "active")
        counts[status] = counts.get(status, 0) + 1
        body = extract_body(content)
        m = re.search(r"## 시스템 개요\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
        domains.append({
            "name": f.stem,
            "file": f"_domains/{f.name}",
            "status": status,
            "category": meta.get("category", ""),
            "tags": meta.get("tags", []),
            "source_documents": meta.get("source_documents", []),
            "summary": (m.group(1).strip()[:200] if m else ""),
            "created": meta.get("created", ""),
        })
    return {"domains": domains, "counts": counts}


def get_board_domain(paths, name: str) -> dict | None:
    p = md_path(paths, name)
    if not p.is_file():
        return None
    content = p.read_text(encoding="utf-8", errors="replace")
    meta = parse_front(content)
    srcs: list = []
    for src in meta.get("source_documents", []):
        sp = paths.context / str(src)
        if sp.is_file():
            try:
                srcs.append({"file": src, "content": sp.read_text(encoding="utf-8",
                                                                  errors="replace")})
            except OSError:
                srcs.append({"file": src, "content": "(읽기 실패)"})
        else:
            srcs.append({"file": src, "content": "(파일 없음)"})
    return {"name": name, "status": meta.get("status", "active"), "content": content,
            "source_documents": srcs, "chat_history": load_chat(paths, name)}


# ── 채팅 히스토리 ───────────────────────────────────────────────────────────────

def load_chat(paths, name: str) -> list:
    p = chat_dir(paths) / f"{name}.json"
    if not p.is_file():
        return []
    try:
        got = json.loads(p.read_text(encoding="utf-8"))
        return got if isinstance(got, list) else []
    except (ValueError, OSError):
        return []


def save_chat(paths, name: str, history: list) -> None:
    p = chat_dir(paths) / f"{name}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def clear_chat(paths, name: str) -> dict:
    d = chat_dir(paths)
    for suffix in (".json", "_analysis.md"):
        (d / f"{name}{suffix}").unlink(missing_ok=True)
    return {"status": "cleared", "domain_name": name}


# ── LLM (우리 레인) ─────────────────────────────────────────────────────────────

def call_llm(prompt: str, *, timeout: int = 300) -> str | None:
    """[중요] 우리 레인을 쓴다 — `agy` → `claude` 폴백(`layer2_verify` 의 호출부 재사용).

    원전 `_call_llm_for_chat` 등가. 실패는 `None` — 호출자가 사유를 화면에 보인다.
    """
    from .. import layer2_verify as L2
    for fn in (L2.call_agy, L2.call_claude):
        out = fn(prompt, timeout=timeout)
        if out and out.strip():
            return out
    return None


def related_docs(paths, topic: str, limit: int = 10) -> list:
    """관련 컨텍스트 문서. 원전은 Chroma 직접 query, 우리는 융합 검색을 쓴다."""
    try:
        from ..context_search import ContextSearch
        return [h.file_id for h in ContextSearch(paths).search(topic, limit=limit)]
    except Exception:                                        # noqa: BLE001
        return []


# ── 생성 (원전 4단계 그대로) ────────────────────────────────────────────────────

def create_domain(paths, topic: str) -> dict:
    topic = (topic or "").strip()
    if not topic:
        raise BoardError("topic 이 비어 있습니다.")

    # 1) 관련 문서 찾기
    sources = related_docs(paths, topic)

    # 2) LLM 으로 도메인명 + 요약 (원전과 같은 프롬프트·JSON 계약)
    previews: list = []
    for sf in sources:
        sp = paths.context / sf
        if sp.is_file():
            try:
                previews.append(f"[{sf}]\n" + sp.read_text(encoding="utf-8",
                                                           errors="replace")[:500])
            except OSError:
                pass
    prompt = ("사용자가 다음 주제에 대한 도메인 문서를 만들려고 한다:\n"
              f"주제: {topic}\n\n"
              "이 주제에 적합한 도메인명(한글)을 제안하고,\n"
              "이 시스템/기능이 하는 일을 2~3문장으로 요약해줘.\n\n"
              "반드시 아래 JSON 형식으로만 응답해줘:\n"
              '{"domain_name": "도메인명", "summary": "요약 2~3문장"}\n')
    if previews:
        prompt += "\n=== 관련 문서 ===\n\n" + "\n\n---\n\n".join(previews)

    display = topic[:20]
    summary = ""
    raw = call_llm(prompt)
    if raw:
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if m:
            try:
                got = json.loads(m.group())
                display = str(got.get("domain_name") or display)
                summary = str(got.get("summary") or "")
            except ValueError:
                pass
        if not summary:
            m2 = re.search(r'"summary"\s*:\s*"([^"]+)"', raw)
            if m2:
                summary = m2.group(1)

    # [중요] 파일명은 우리 화이트리스트를 통과해야 한다 — 한글 도메인명은 파일명으로 못 쓴다.
    # [중요] 원전처럼 **표시명을 그대로 파일명에** 쓴다(한글 유지). 경로 위험문자만 치환한다.
    safe = _BAD_CHARS.sub("_", display).strip(" ._") or "domain"
    name, n = safe, 2
    while (domains_dir(paths) / f"{name}.md").exists():
        name, n = f"{safe}_{n}", n + 1
    out = md_path(paths, name)

    # 3) 드래프트 (원전 형식 그대로 + 표시명 보존)
    src_list = "\n".join(f"  - {s}" for s in sources) if sources else "  # (없음)"
    content = ("---\n"
               "tags: []\n"
               f"category: 도메인/{display}\n"
               "type: domain\n"
               "status: draft\n"
               f"source_documents:\n{src_list}\n"
               f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
               "---\n\n"
               "## 시스템 개요\n\n"
               f"{summary}\n")
    _atomic_write(out, content)

    # 4) 안내 메시지만 저장 (분석은 채팅 때 lazy — 원전과 같다)
    ts = datetime.now().isoformat()
    src_text = "\n".join(f"  - {s}" for s in sources) if sources else "  (없음)"
    guide = (f"'{display}' 도메인이 생성되었습니다.\n\n"
             f"[요약]\n{summary}\n\n"
             f"[관련 소스 문서 — {len(sources)}개]\n{src_text}\n\n"
             "위 내용을 확인하고, 분석 전에 보정할 사항이 있으면 알려주세요.\n"
             "(예: 특정 모듈의 빌드 제외 여부, 참조용 코드, 중점 분석 대상 등)\n\n"
             "바로 분석하려면 '분석 시작'을, 보정 사항과 함께 분석하려면 내용을 입력해 주세요.")
    save_chat(paths, name, [
        {"role": "user", "content": topic, "timestamp": ts},
        {"role": "assistant", "content": guide, "timestamp": ts}])
    if not raw:
        # [주의] LLM 없이 만들어졌다는 사실을 숨기지 않는다
        return {"status": "created", "domain_name": name, "display_name": display,
                "source_documents": sources, "summary": summary,
                "note": "[주의] LLM 을 못 불러 이름·요약이 비었다 (초안은 만들어졌다)"}
    return {"status": "created", "domain_name": name, "display_name": display,
            "source_documents": sources, "summary": summary}


# ── 채팅 (원전: 소스 코드까지 실어 LLM 에 준다) ─────────────────────────────────

def chat(paths, name: str, message: str) -> dict:
    p = md_path(paths, name)
    if not p.is_file():
        raise BoardError("도메인 없음")
    message = (message or "").strip()
    if not message:
        raise BoardError("message 가 비었다")

    content = p.read_text(encoding="utf-8", errors="replace")
    meta = parse_front(content)
    history = load_chat(paths, name)

    src_blocks: list = []
    used = 0
    for src in meta.get("source_documents", [])[:10]:
        sp = paths.context / str(src)
        if not sp.is_file() or used > 15000:
            continue
        try:
            txt = sp.read_text(encoding="utf-8", errors="replace")[:2000]
        except OSError:
            continue
        src_blocks.append(f"[{src}]\n{txt}")
        used += len(txt)

    convo = "\n\n".join(f"{h.get('role')}: {h.get('content')}" for h in history[-8:])
    prompt = ("너는 UE5 프로젝트의 도메인 문서를 사람과 함께 다듬는 조수다.\n"
              "아래 도메인 문서와 관련 컨텍스트 문서를 근거로 사용자의 요청에 답한다.\n"
              "[중요] 근거가 없는 것은 지어내지 말고 모른다고 말한다.\n\n"
              f"=== 도메인 문서 ({name}) ===\n{content}\n\n")
    if src_blocks:
        prompt += "=== 관련 컨텍스트 문서 ===\n\n" + "\n\n---\n\n".join(src_blocks) + "\n\n"
    if convo:
        prompt += f"=== 지금까지의 대화 ===\n{convo}\n\n"
    prompt += f"=== 사용자 ===\n{message}\n"

    raw = call_llm(prompt)
    if not raw:
        raise BoardError("LLM 을 부르지 못했다 (agy·claude 둘 다 실패) — 마스터에서 CLI 확인 필요")
    ts = datetime.now().isoformat()
    history.append({"role": "user", "content": message, "timestamp": ts})
    history.append({"role": "assistant", "content": raw.strip(), "timestamp": ts})
    save_chat(paths, name, history)
    return {"role": "assistant", "content": raw.strip(), "timestamp": ts}


# ── 갱신 · 활성화 · 삭제 ────────────────────────────────────────────────────────

def update_domain(paths, name: str, content: str) -> dict:
    p = md_path(paths, name)
    if not p.is_file():
        raise BoardError("도메인 없음")
    if not (content or "").strip():
        raise BoardError("빈 내용으로 덮지 않는다")
    _atomic_write(p, content)
    return {"status": "updated", "domain_name": name}


def activate_domain(paths, name: str, content: str) -> dict:
    """draft → active. [중요] 태그를 소스 문서에서 상속하고, **색인은 색인기에 맡긴다.**"""
    p = md_path(paths, name)
    if not p.is_file():
        raise BoardError("도메인 없음")
    content = content or p.read_text(encoding="utf-8", errors="replace")
    if "status: draft" in content:
        content = content.replace("status: draft", "status: active", 1)
    elif "status:" not in content:
        content = content.replace("type: domain", "type: domain\nstatus: active", 1)

    meta = parse_front(content)
    if not meta.get("tags"):
        counter: dict = {}
        for src in meta.get("source_documents", []):
            sp = paths.context / str(src)
            if not sp.is_file():
                continue
            try:
                sm = parse_front(sp.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            for t in sm.get("tags", []):
                counter[t] = counter.get(t, 0) + 1
        if counter:
            top = sorted(counter, key=lambda k: -counter[k])[:15]
            content = content.replace("tags: []", "tags: [" + ", ".join(top) + "]", 1)

    _atomic_write(p, content)
    # [중요] 원전은 서버가 벡터 컬렉션에 직접 upsert 했다. 우리 색인기는 **별도 프로세스**이고
    #    `ax-indexer.path`(inotify)가 파일 변경을 잡는다 — 웹이 색인을 직접 만지지 않는다.
    return {"status": "activated", "domain_name": name, "indexed": False,
            "note": "색인은 `ax-indexer`(inotify)가 이 파일 변경을 잡아 처리한다"}


def delete_domain(paths, name: str) -> dict:
    """[중요] 지우지 않고 `_archive/` 로 옮긴다.

    원전은 파일을 지웠다. 우리 규칙은 *"되돌릴 수 있게 둔다"* 이고 `_domains/_archive/` 가
    이미 그 자리로 쓰이고 있다 — 웹 버튼 한 번으로 사람이 쓴 문서를 잃지 않는다.
    """
    p = md_path(paths, name)
    if not p.is_file():
        raise BoardError("도메인 없음")
    arch = domains_dir(paths) / "_archive"
    arch.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = arch / f"{name}.{stamp}.md"
    p.replace(dest)
    clear_chat(paths, name)
    return {"status": "archived", "domain_name": name, "moved_to": str(dest),
            "note": "[중요] 지우지 않고 `_domains/_archive/` 로 옮겼다 — 되돌릴 수 있다"}
