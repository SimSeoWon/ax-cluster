"""프로젝트 프로필 — **사람만 아는 것**을 받아 적립하는 자리 (사용자 결정 2026-09-20).

## 왜 이것이 필요한가 — 오염이 공백보다 비쌌다

2026-09-20: `.33` 의 NS 콘솔이 자기 프로젝트 문서로 *"This project is a multiplayer game …
**Listen Server** …"* 를 읽고 있었다. **NS 는 Third Person 템플릿 기반**이고 그 문장은 거짓이다
(출처는 ModularStage 문서가 통째로 배달된 것 — `#649`). 지휘자인 나도 그것을 NS 의 사실로 읽었다.

[중요] **비어 있는 것보다 오염된 것이 더 나쁘다.** 그리고 공백일 때 나는 **다른 문서에서
추론한다** — 그 문서가 남의 프로젝트 것이면 조용히 틀린다. 그러니 답은 「비워 두기」가 아니라
**사람에게 받아서 채우기**다.

## 두 부류를 섞지 않는다 — 이게 이 모듈의 설계 전부다

    A. 기계가 재는 것   엔진 association · 모듈 · 타깃 · 소스 확장자 분포
                        → `measure()`. **사실로만 싣고 규약으로 굳히지 않는다**
    B. 사람만 아는 것   엔진이 확정인가 · 용도 · 언어 정책 · 장르 · 왜 존재하는가
                        → `REQUIRED`. 파일에 없고 측정으로도 안 나온다

🔴 [중요] **A 를 B 자리에 적립하지 않는다.** `#294` 가 그 값을 이미 치렀다 — NS 의 규약 절에
*"한글 주석 0개 → 주석은 영문이다"* 가 **측정으로** 적립됐고(main 이 에픽 템플릿이니 당연했다)
그것이 워커 매니페스트로 가서 **골조 계약(한국어 주석)과 정면으로 충돌**했다.
*"규약은 결정이지 측정이 아니다."* 그래서 `measure()` 의 결과는 **질문할 때 근거로 보여 줄 뿐**
저장되지 않는다.

## 적립처가 git 관리인 이유

`<트윈>/` 은 **gitignore** 다(`.gitignore:17` `/NS/`). 거기 두면 이 결정이 **이력 없이** 산다.
프로필은 사람의 결정이므로 리뷰·되돌리기가 가능해야 한다 → `master/client/payload/profile/<P>.yaml`.

[주의] **이건 원전에 없던 단계다.** 원전은 프로젝트가 하나였고 팀이 자기 `CLAUDE.md` 를 들고
있었다. 우리는 다중 프로젝트이고 **워커가 그 문서를 계약으로 받으므로** 필요해졌다 —
이식이 아니라 우리 고유 추가이고, 근거는 사용자 결정(2026-09-20)이다.
"""
from __future__ import annotations

from pathlib import Path

import yaml

# [중요] **집행되는 자리는 `blockers()` 하나다.** 목록을 늘리려면 여기만 고친다 —
#    두 곳에 적으면 판정기와 게이트가 갈린다(`hook_entry` 가 치른 값과 같은 부류).
PURPOSES = ("game", "tool", "rnd", "demo")

# 🔴 [중요] **프로젝트 타입** (`#693`, 사용자 결정 2026-09-28) — 파이프라인이 어디까지 받는가.
#    unreal       정본 7단계 전부 (골조 UHT · 조각별 UE5 빌드 · 상주)
#    index_only   색인·검색·요청자 콘솔까지. **분산 작업은 받지 않는다** — 골조 계약·게이트가
#                 UE5 전제라 등재하면 엉뚱한 자리에서 실패한다(`KimodoMotion_WebUI` 실측)
#    code         UE 가 아닌 소스 프로젝트에 **분산 작업을 연다** (`#695`, 사용자 결정 2026-09-30
#                 D1). 받는 파일은 프로필 `work_exts` 가 정한다 — 1단계는 `.py` 만. 그 밖의
#                 대상은 등재를 **거절**한다(`target_violations`). C++ 는 `work_exts` 를 늘려 연다
#    [주의] **측정으로 추론하지 않는다** — `.uproject` 유무로 가르면 「엔진 미확정 UE」와 「엔진
#    없는 유틸」이 섞인다. 사람이 적는 칸이고, 없으면 등재를 **거절**한다(fail-closed).
KINDS = ("unreal", "index_only", "code")
# 🔴 [중요] **「UE 가 아니다」와 「분산 작업이 없다」는 다른 질문이다** (`#695`). `#693` 때는 둘이
#    같은 값(index_only)이라 호출부가 섞여 있었다 — 합성 사실 게이트·배달 축소는 앞의 질문이고
#    (`is_non_unreal`), 자동 리뷰 제외는 `is_index_only`, 등재 거절은 `blockers`다.
NON_UNREAL_KINDS = ("index_only", "code")
# `code` 가 받을 수 있는 확장자. [주의] 목록에 없는 값은 **저장을 거절**한다 — 게이트가 모르는
#    언어를 열어 두면 층1·골조 게이트가 그 파일을 C++ 로 읽는다.
WORK_EXTS = (".py",)

# 사람이 답해야 채워지는 칸. `genre` 는 `purpose == "game"` 일 때만 필수다.
# [주의] 엔진 세 칸은 `kind == unreal` 일 때만 필수다 — 엔진이 없는 프로젝트에 엔진을 묻지 않는다.
# [주의] `work_exts` 는 `kind == code` 일 때만 필수다.
REQUIRED = ("kind", "engine_decided", "engine", "engine_version", "language", "purpose", "overview")
ENGINE_FIELDS = ("engine_decided", "engine", "engine_version")

OVERVIEW_MIN = 40          # 한 문단. [주의] 길이는 품질이 아니지만 **한 단어 회피**는 막는다


def profile_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "client" / "payload" / "profile"


def profile_path(project: str) -> Path:
    return profile_dir() / f"{project}.yaml"


def load(project: str) -> dict:
    """적립된 프로필. 없으면 빈 dict — **없다는 것을 0 으로 위장하지 않는다.**"""
    p = profile_path(project)
    if not p.is_file():
        return {}
    try:
        got = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:                                           # noqa: BLE001
        return {}
    return got if isinstance(got, dict) else {}


def measure(project: str) -> dict:
    """A — 소스 트리에서 재는 값. **저장하지 않는다**, 질문할 때 근거로 보여 준다.

    [주의] 실패를 빈 값으로 위장하지 않는다 — `why` 에 사유를 싣는다(`#285`·`#309` 축).
    """
    out = {"uproject": "", "engine_association": "", "targets": [], "modules": [],
           "sources": {}, "twin_engine": "", "why": ""}
    try:
        from ..client.bundle import _uproject_facts               # noqa: PLC0415
        f = _uproject_facts(project)
        out["uproject"], out["targets"], out["modules"] = f["uproject"], f["targets"], f["modules"]
        out["why"] = f.get("why") or ""
    except Exception as e:                                        # noqa: BLE001
        out["why"] = f"소스 실측 실패 — {type(e).__name__}: {e}"
    try:
        from ..context_search.paths import resolve                # noqa: PLC0415
        repo = resolve(project).repo
        if out["uproject"]:
            import json                                           # noqa: PLC0415
            up = repo / out["uproject"]
            if up.is_file():
                out["engine_association"] = str(
                    (json.loads(up.read_text(encoding="utf-8")) or {}).get("EngineAssociation") or "")
        src = repo / "Source"
        if src.is_dir():
            for ext in ("cpp", "h", "cs", "py"):
                out["sources"][ext] = sum(1 for _ in src.rglob(f"*.{ext}"))
    except Exception as e:                                        # noqa: BLE001
        out["why"] = (out["why"] + " · " if out["why"] else "") + \
            f"트리 실측 실패 — {type(e).__name__}: {e}"
    try:
        from .config import Registry                              # noqa: PLC0415
        out["twin_engine"] = Registry.load().config_of(project).engine or ""
    except Exception:                                             # noqa: BLE001
        pass
    return out


def missing(project: str) -> list:
    """**안 채워진 칸**의 이름들. 빈 목록이면 사람이 전부 답했다는 뜻이다."""
    got = load(project)
    need = REQUIRED if kind_of(project) not in NON_UNREAL_KINDS else \
        tuple(k for k in REQUIRED if k not in ENGINE_FIELDS)
    out = [k for k in need
           if got.get(k) is None or (isinstance(got.get(k), str) and not got[k].strip())]
    if str(got.get("purpose") or "") == "game" and not str(got.get("genre") or "").strip():
        out.append("genre")
    if kind_of(project) == "code":
        if not work_exts(project):
            out.append("work_exts")
        # ⑦ 통합 검사가 돌릴 테스트 — 없으면 전진 게이트가 「무엇을 돌릴지 모른다」로 막힌다
        for k in ("test_start_dir", "test_pattern"):
            if not str(got.get(k) or "").strip():
                out.append(k)
    return out


def blockers(project: str) -> list:
    """🔴 **집행이 읽는 목록.** 비어 있지 않으면 그 프로젝트에 분산 작업을 등재하지 않는다.

    [중요] `missing` 과 다르다 — 답을 **받았는데도** 막아야 하는 경우가 있다:
    `engine_decided: false` 는 정상적으로 기록된 답이지만, 엔진이 안 정해졌는데 워커에게
    소스 작업을 계약으로 내보내는 것은 순서가 거꾸로다.
    """
    miss = missing(project)
    out = [f"프로필 미수집: {', '.join(miss)}"] if miss else []
    got = load(project)
    if got.get("kind") == "index_only":
        out.append("색인 전용 프로젝트다 (`kind: index_only`, `#693`) — 분산 작업은 받지 않는다. "
                   "골조 계약·UHT·조각별 UE5 빌드가 UE5 전제라 등재하면 엉뚱한 자리에서 실패한다")
    elif got.get("kind") == "code":
        pass                    # 받을 확장자는 `target_violations` 가 조각마다 본다
    elif got and got.get("engine_decided") is False:
        out.append("엔진이 아직 확정되지 않았다 (`engine_decided: false`) — "
                   "엔진이 정해져야 소스 작업을 계약으로 내보낼 수 있다")
    return out


def kind_of(project: str) -> str:
    """프로젝트 타입. **없거나 모르는 값이면 빈 문자열** — 호출자가 그것을 unreal 로 읽지 않는다.

    [주의] 빈 값의 뜻은 자리마다 다르다: 등재는 `missing` 으로 **거절**하고, 배달·상주처럼
    종전 동작이 곧 unreal 인 자리는 종전 동작을 유지한다(기존 두 프로젝트를 깨지 않는다).
    """
    k = str(load(project).get("kind") or "").strip()
    return k if k in KINDS else ""


def is_index_only(project: str) -> bool:
    """**분산 작업을 받지 않는** 타입인가. 「UE 가 아닌가」는 `is_non_unreal` 이다."""
    return kind_of(project) == "index_only"


def is_non_unreal(project: str) -> bool:
    """**UE 가 아닌** 타입인가 (`index_only`·`code`). 모르는 값은 False — 종전(unreal) 동작."""
    return kind_of(project) in NON_UNREAL_KINDS


def work_exts(project: str) -> tuple:
    """`code` 가 받는 확장자. **적립된 값 중 `WORK_EXTS` 안의 것만** — 모르는 값은 버리지 않고
    `save` 가 애초에 거절한다. 소문자·점 포함으로 맞춘다."""
    raw = load(project).get("work_exts") or []
    if isinstance(raw, str):
        raw = [raw]
    out = []
    for e in raw:
        e = str(e).strip().lower()
        e = e if e.startswith(".") else "." + e
        if e in WORK_EXTS and e not in out:
            out.append(e)
    return tuple(out)


def target_violations(project: str, files) -> list:
    """🔴 등재·개선요청이 읽는 **확장자 게이트** (`#695`). 비어 있지 않으면 거절한다.

    `unreal` 은 `.py` 만 막는다(`#771` A0) — 그 밖은 종전 그대로다. `code` 는 `work_exts` 밖의 파일을 막는다 —
    1단계에서 C++ 가 섞여 들어오면 층1·골조 게이트가 `.py` 판으로 그 파일을 읽는다.
    [주의] 빈 이름은 무시한다(스펙의 선택 칸). 파일이 **하나도 없는** 조각은 여기서 막지 않는다 —
    그건 `_prepare_specs` 의 몫이다.
    """
    kind = kind_of(project)
    if kind == "unreal":
        # 🔴 `#771` A0 (사용자 결정 2026-10-09) — `.py` 만 막고 나머지 확장자는 종전 그대로 받는다.
        #    층2 grounding·⑦ 통합 검사가 C++ 판 하나뿐이라 `.py` 조각을 판정할 자리가 없다(A 보류).
        #    [주의] `.py`+C++ 를 섞은 work 도 이 판정으로 거절된다. `code` 는 섞일 수 없다 —
        #    `work_exts` 가 `.py` 만 열려 있어 C++ 가 위 확장자 게이트에서 먼저 막힌다.
        py = sorted({str(f) for f in (files or [])
                     if str(f or "").strip() and Path(str(f)).suffix.lower() == ".py"})
        if not py:
            return []
        return [f"`{project}` 는 `kind: unreal` 이다 — `.py` 조각은 층2·⑦ 이 언어별 판정을 갖출 "
                f"때까지 받지 않는다 (`#771` A 보류) — 대상: {', '.join(py)}"]
    if kind != "code":
        return []
    allow = work_exts(project)
    bad = sorted({str(f) for f in (files or [])
                  if str(f or "").strip() and Path(str(f)).suffix.lower() not in allow})
    if not bad:
        return []
    return [f"`{project}` 는 `kind: code` 이고 받는 확장자는 {', '.join(allow) or '(없음)'} 뿐이다 "
            f"(`#695` 1단계) — 대상 밖: {', '.join(bad)}"]


def questions(project: str) -> list:
    """사람에게 **그대로 물을 문장들**. 표면이 문구를 지어내지 않게 여기서 준다.

    [중요] **모델의 제안을 답으로 적립하지 않는다** — 골조 `questions` 와 같은 규약이다.
    초안을 보여 주는 것은 되지만, 저장되는 문장은 사람이 확정한 것이어야 한다.
    """
    m = measure(project)
    ext = " · ".join(f"{k} {v}" for k, v in (m.get("sources") or {}).items() if v) or "(못 셌다)"
    ev = (f"[실측] `.uproject`={m['uproject'] or '없음'} · "
          f"EngineAssociation={m['engine_association'] or '없음'} · "
          f"트윈 engine={m['twin_engine'] or '없음'} · 소스 {ext}")
    miss = set(missing(project))
    ask = [
        ("kind", f"프로젝트 타입은 무엇입니까? ({' / '.join(KINDS)}) — "
                 "index_only 는 색인·검색까지만 받고 분산 작업은 받지 않습니다 · "
                 "code 는 UE 가 아닌 소스에 분산 작업을 받습니다"),
        ("work_exts", f"(code 일 때) 분산 작업을 받을 확장자는 무엇입니까? "
                      f"(지금 열린 것: {' / '.join(WORK_EXTS)})"),
        ("test_start_dir", "(code 일 때) 통합 검사로 돌릴 테스트 디렉토리는 어디입니까? "
                           "(저장소 루트 기준, 예: webui/tests)"),
        ("test_pattern", "(code 일 때) 테스트 파일 이름 패턴은 무엇입니까? (예: *_test.py)"),
        ("engine_decided", "사용할 게임 엔진이 **확정**됐습니까? (예/아니오)"),
        ("engine", "엔진 이름은 무엇입니까? (예: Unreal Engine)"),
        ("engine_version", "엔진 버전은 무엇입니까? "
                           "[주의] association 과 설치 버전이 다를 수 있습니다"),
        ("language", "주 언어·정책은 무엇입니까? (예: C++ 중심 · 블루프린트는 조립만)"),
        ("purpose", f"무슨 용도입니까? ({' / '.join(PURPOSES)})"),
        ("genre", "게임이라면 장르는 무엇입니까?"),
        ("overview", "이 프로젝트가 **왜 존재하는지** 한 문단으로 적어 주세요 "
                     "(핵심 시스템·설계 의도)."),
    ]
    return [ev] + [f"- ({k}) {q}" for k, q in ask if k in miss or not miss]


def save(project: str, **fields) -> dict:
    """사람의 답을 적립한다. 돌려주는 것: `{"ok", "path", "missing", "blockers"}`.

    [중요] **부분 저장을 허용한다** — 한 번에 다 못 받을 수 있고, 받은 것을 버리면 사람이
    같은 말을 두 번 한다. 대신 **미완은 미완이라고 계속 말한다**(`missing`).
    [중요] 검증은 fail-closed 다 — 모르는 칸·모르는 용도는 **거절**한다. 조용히 무시하면
    사람은 적립됐다고 믿는다.
    """
    known = set(REQUIRED) | {"genre", "notes", "work_exts", "test_start_dir", "test_pattern"}
    bad = sorted(set(fields) - known)
    if bad:
        raise ValueError(f"모르는 칸: {', '.join(bad)} (가능: {', '.join(sorted(known))})")
    if "purpose" in fields and str(fields["purpose"]) not in PURPOSES:
        raise ValueError(f"purpose 는 {PURPOSES} 중 하나다 — 받은 값: {fields['purpose']!r}")
    if "overview" in fields and len(str(fields["overview"]).strip()) < OVERVIEW_MIN:
        raise ValueError(f"overview 가 너무 짧다({len(str(fields['overview']).strip())}자) — "
                         f"{OVERVIEW_MIN}자 이상으로 적는다. 한 단어는 서술이 아니다")
    if "kind" in fields and str(fields["kind"]) not in KINDS:
        raise ValueError(f"kind 는 {KINDS} 중 하나다 — 받은 값: {fields['kind']!r}")
    if "engine_decided" in fields and not isinstance(fields["engine_decided"], bool):
        raise ValueError("engine_decided 는 true/false 다 (문자열이 아니다)")
    if "work_exts" in fields:
        we = fields["work_exts"]
        if not isinstance(we, (list, tuple)) or not we:
            raise ValueError(f"work_exts 는 확장자 목록이다 (예: ['.py']) — 받은 값: {we!r}")
        unknown = [e for e in we if str(e).strip().lower() not in WORK_EXTS]
        if unknown:
            raise ValueError(f"work_exts 는 {WORK_EXTS} 안에서만 고른다 — 게이트가 모르는 언어: "
                             f"{unknown} (`#695`: 새 언어는 게이트를 먼저 연다)")
        fields = {**fields, "work_exts": [str(e).strip().lower() for e in we]}

    got = load(project)
    got.update(fields)
    d = profile_dir()
    d.mkdir(parents=True, exist_ok=True)
    p = profile_path(project)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(got, allow_unicode=True, sort_keys=True), encoding="utf-8")
    tmp.replace(p)
    return {"ok": True, "path": str(p), "missing": missing(project),
            "blockers": blockers(project)}


def project_line(project: str) -> str:
    """생성 본문의 **첫 문단**. 프로필이 없으면 「비어 있다」를 그대로 말한다.

    [중요] 여기서 지어내지 않는다 — `claude_md_body` ③ 의 규약(*"지어내지 않고 「비어 있다」고
    적는다"*)을 그대로 따른다. 다만 **채우는 길**을 한 줄로 가리킨다.
    """
    g = load(project)
    if missing(project):
        return (f"`{project}` — [주의] **프로젝트 서술이 비어 있다.** 이것은 사실이고, "
                f"추측으로 채우지 않는다. 사람이 `set_project_profile` 로 답하면 이 문단이 "
                f"채워진다 (안 채워진 칸: {', '.join(missing(project))}).")
    kind = {"game": "게임", "tool": "툴", "rnd": "R&D", "demo": "데모"}.get(g.get("purpose"), g.get("purpose"))
    genre = f" · 장르 **{g['genre']}**" if g.get("genre") else ""
    if g.get("kind") == "index_only":
        return (f"`{project}` — **색인 전용** {kind} 프로젝트 (UE5 아님 · 분산 작업 없음). "
                f"주 언어·정책: {g['language']}.\n\n{str(g['overview']).strip()}")
    if g.get("kind") == "code":
        return (f"`{project}` — **UE 가 아닌** {kind} 프로젝트 · 분산 작업은 "
                f"{', '.join(work_exts(project))} 만 받는다. "
                f"주 언어·정책: {g['language']}.\n\n{str(g['overview']).strip()}")
    return (f"`{project}` — **{g['engine']} {g['engine_version']}** {kind} 프로젝트{genre}. "
            f"주 언어·정책: {g['language']}.\n\n{str(g['overview']).strip()}")
