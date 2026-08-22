"""stale 판정 — 어느 도메인을 재합성해야 하는가 (소 1.3.8). **LLM 0.**

원본: `watcher/ontology_refresh.compute_stale_domains` (Phase η.8).

## 원리 — 리비전 워터마크 두 개를 비교한다

    stored  = `class_ontology.source_commit`  ← **합성 시점**에 찍은 스냅샷
    latest  = 그 클래스의 컨텍스트 MD `source_commit`  ← **커밋 시점**에 갱신

하나라도 다르면 그 도메인은 stale 이다. 우리 `context_synth` 가 문서를 만들 때 `latest` 를
찍고(실측 확인), 재합성이 `stored` 를 `latest` 로 다시 찍으면 **자동으로 settle** 된다.

## [중요] 이 설계가 대체한 것 — dirty 플래그

Phase η.8 이 `domain_dirty` 테이블을 **없앴다.** 플래그는 누가 세우고 누가 지우는지가
갈려 있어 *"세워졌는데 안 지워짐"*·*"count=0 오인 폭주"* 가 났다. 워터마크는 **상태가
아니라 사실의 비교**라 그 실패 모드가 구조적으로 없다 — 재시작해도 같은 답이 나온다.

## [중요] `-1` 규약이 첫 배포 폭주를 막는다

값을 못 가져오면 양쪽 다 `-1` 이다. `-1 == -1` 이므로 **not stale** — 레거시 문서나
커밋이 아직 없는 상태에서 전체 재합성이 터지지 않는다. 실제 커밋이 올라와 문서가
재생성될 때 비로소 실 리비전을 얻고, 그때만 stale 이 된다.

**commit-hash 축 밖의 변경**(도메인 MD 편집·신규 도메인)은 여기서 안 잡힌다 —
eventually-consistent 다. 다음 코드 변경 사이클이나 강제 재합성이 반영한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..context_search.paths import ProjectPaths
from ..context_synth import md as md_mod
from . import yaml_io

MISSING = "-1"


def context_doc_for(paths: ProjectPaths, source_file: str) -> Path:
    """소스 파일 → 그 파일의 컨텍스트 MD. **합성기의 그룹 규칙과 같아야 한다**
    (`parent/stem`) — 다르면 워터마크를 영영 못 찾아 전부 stale 로 보인다."""
    p = Path(source_file)
    return paths.context / f"{p.parent / p.stem}.md"


def latest_commit(paths: ProjectPaths, source_file: str) -> str:
    """그 소스의 컨텍스트 MD 에 찍힌 리비전. 없으면 `-1`."""
    if not source_file:
        return MISSING
    doc = context_doc_for(paths, source_file)
    try:
        return md_mod.read_source_commit(doc.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return MISSING


@dataclass
class DomainStale:
    domain: str
    changed: int = 0
    total: int = 0
    members: list = field(default_factory=list)     # (클래스, stored, latest) — 바뀐 것만
    # [중요] **「모른다」를 「최신이다」와 가른다** (`#275`, 사용자 결정 2026-08-23).
    #    양쪽 `source_commit` 이 모두 없으면 `s == l` 이라 종전에는 **조용히 통과**했다.
    #    실측 2026-08-23: 도메인 멤버 112건 중 **92건(82%)이 그 상태**였다 — 판정이 실제로
    #    보고 있던 것은 20건뿐이다. 판정이 안 되는 것을 통과로 접는 것은 거짓 보고다.
    unknown: int = 0
    unknown_members: list = field(default_factory=list)   # (클래스, stored, latest)

    @property
    def stale(self) -> bool:
        # [주의] **판정 불가를 stale 로 만들지 않는다.** 그러면 92건이 재합성 대상이 되고,
        #    그것은 `~/CLAUDE.md`·M2 가 금지한 **1,055건 일괄 재생성**이다(로컬 모델이 받아온
        #    스냅샷보다 나쁘게 측정됐다). 시끄럽게 **보고**하는 것이 이 일감의 완료 조건이다.
        return self.changed > 0

    @property
    def undecidable(self) -> bool:
        return self.unknown > 0

    @property
    def reason(self) -> str:
        out = f"stale={self.changed}/{self.total}"
        if self.unknown:
            out += f" · 판정불가={self.unknown}"
        return out


def _members(paths: ProjectPaths, domain: str) -> dict:
    """도메인 멤버 → `{클래스: 소스파일}`.

    두 곳을 합친다 — **manifest 가 가리키는 object yaml**(우리 정본)과 **`class_ontology`
    분류 행**. 원본도 "MD 선언 ∪ 분류됨" 으로 합집합을 쓴다: 한쪽에만 있는 멤버를 놓치면
    그 클래스의 변경이 영영 stale 을 못 만든다.
    """
    out: dict = {}
    root = paths.ontology / "domains" / domain
    manifest = yaml_io.read(root / "domain.yaml") or {}
    from . import hierarchy
    for rel in manifest.get("objects") or []:
        obj = yaml_io.read(root / str(rel)) or {}
        name = obj.get("name")
        # [중요] 하위 문서 참조는 클래스가 아니다 — 워터마크(소스 커밋)가 없다.
        if name and not hierarchy.is_domain_ref(obj):
            out[name] = obj.get("file") or ""
    try:
        from ..graph import db as gdb
        if gdb.exists(paths):
            conn = gdb.connect(paths)
            try:
                rows = conn.execute(
                    "SELECT o.class_name, c.file FROM class_ontology o "
                    "LEFT JOIN classes c ON c.name = o.class_name "
                    "WHERE o.ontology_domain = ?", (domain,)).fetchall()
            finally:
                conn.close()
            for r in rows:
                out.setdefault(r["class_name"], r["file"] or "")
    except Exception:                                   # noqa: BLE001
        # [중요] **DB 접근이 실패하면 빈 dict 다** — 그것이 맞다. 여기 근거가 둘 있다:
        #
        #   ① 이 질의의 대상 `class_ontology` 는 **일부러 비어 있다**(소속의 SSOT 는
        #      `ontology/*.yaml` — `context_search/infer.py` 머리말, 소 3.1.2 실측 0행).
        #      즉 정상 경로에서도 이 함수는 사실상 `{}` 를 돌려준다.
        #   ② stale 판정은 **못 읽으면 stale 로 기울어야** 안전하다 — 빈 dict 는 "비교할 근거가
        #      없다" 가 되어 재합성 쪽으로 간다. 반대로 기울면 낡은 트윈이 조용히 남는다.
        #
        # [주의] σ.2 감사(2026-08-14)가 이 자리를 *"의도가 안 적힌 silent fallback"* 으로 잡았고,
        # 판정은 **「유지 + 의도 명시」**다(원전이 6건 중 4건을 그렇게 처리했다).
        pass
    return out


def _stored(paths: ProjectPaths, domain: str, names: list) -> dict:
    """클래스별 **저장된** 워터마크. 없으면 `-1`.

    [중요] **신호원이 원본과 다르다 — 우리 SSOT 는 오브젝트 yaml 이다.** 원본은
    `class_ontology.source_commit` 을 정본으로 쓰지만, 우리 그 표는 **0행이고 쓰는 코드가
    0건**이다(의도 — 소속의 SSOT 는 yaml, `#189`). 원본 `upsert_class_source_commit` 은
    *"행이 없으면 no-op"* 이라 그 경로를 그대로 옮겨도 **아무것도 안 찍힌다.**

    실측 2026-08-15: 오브젝트 yaml 112개 중 **16개가 실 리비전을 갖고 있는데**(원본이
    스냅샷을 내보내기 전에 찍은 것) DB 만 보던 이 함수는 그것을 **한 번도 안 읽었다** —
    즉 이미 정합인 클래스도 전부 stale 로 셌다. 마일스톤 4 함정 *"기제는 옮기고 신호원은
    다시 고른다"* 가 여기에도 걸린다(σ.9.0 의 `mtime`→git 과 같은 자리).

    DB 는 **폴백으로 남긴다** — 언젠가 그 표를 쓰게 되면 그때도 맞아야 한다.
    """
    out = {n: MISSING for n in names}
    # ① 오브젝트 yaml — 우리 정본
    root = paths.ontology / "domains" / domain
    manifest = yaml_io.read(root / "domain.yaml") or {}
    for rel in manifest.get("objects") or []:
        obj = yaml_io.read(root / str(rel))
        if not isinstance(obj, dict):
            continue
        name, mark = obj.get("name"), obj.get("source_commit")
        if name in out and mark:
            out[name] = str(mark)
    if all(v != MISSING for v in out.values()):
        return out
    # ② DB — 원본 경로. yaml 이 말하지 않은 것만 채운다
    try:
        from ..graph import db as gdb
        if not gdb.exists(paths) or not names:
            return out
        conn = gdb.connect(paths)
        try:
            marks = ",".join("?" * len(names))
            for r in conn.execute(
                    f"SELECT class_name, source_commit FROM class_ontology "
                    f"WHERE class_name IN ({marks})", tuple(names)):
                if out.get(r["class_name"], MISSING) == MISSING:
                    out[r["class_name"]] = r["source_commit"] or MISSING
        finally:
            conn.close()
    except Exception:                                   # noqa: BLE001
        pass
    return out


def active_domains(paths: ProjectPaths) -> list:
    """`status: active` 인 도메인. manifest 에 status 가 없으면 **active 로 본다** —
    받아온 스냅샷이 그 키를 안 쓴다(실측). draft 를 걸러내는 것이 목적이지 없는 키로
    전부 제외하는 것이 아니다."""
    root = paths.ontology / "domains"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        m = yaml_io.read(d / "domain.yaml") or {}
        if str(m.get("status", "active")).lower() == "active":
            out.append(d.name)
    return out


def compute(paths: ProjectPaths, domains: list | None = None) -> list:
    """재합성이 필요한 도메인들. **stale 인 것만** 돌려준다."""
    out = []
    for domain in (domains if domains is not None else active_domains(paths)):
        members = _members(paths, domain)
        if not members:
            continue
        stored = _stored(paths, domain, list(members))
        st = DomainStale(domain=domain, total=len(members))
        for name, src in sorted(members.items()):
            s, l = stored.get(name, MISSING), latest_commit(paths, src)
            if s == MISSING and l == MISSING:
                # [중요] 양쪽이 없다 = **비교할 근거가 없다.** 종전에는 `s == l` 이라 최신으로
                #    접혔다. [주의] 한쪽만 없는 것은 여기 오지 않는다 — 그것은 아래에서
                #    `changed` 가 되고, 재합성이 스탬프를 박아 **스스로 판정 가능해진다**
                #    (실측 5건, 자기 치유).
                st.unknown += 1
                st.unknown_members.append((name, s, l))
            elif s != l:
                st.changed += 1
                st.members.append((name, s, l))
        # [중요] 판정 불가만 있는 도메인도 **결과에 나와야 한다** — 안 나오면 그것이 침묵이다.
        #    소비자는 `r.stale` 로 재합성을 거르므로(`synth.py`) 이 행이 재합성을 부르지 않는다.
        if st.stale or st.undecidable:
            out.append(st)
    return out


def settle(paths: ProjectPaths, domain: str, classes=None) -> int:
    """재합성을 마친 클래스의 워터마크를 **현재 값으로 올린다.** 반환 = 갱신한 오브젝트 수.

    원본: `ontology_synthesizer.synthesize_domain` 의 스탬프 절(Phase η.7.2 제안 2) —
    *"합성이 `source_commit` 을 재스탬프 → self-settling, 재시작 idempotent"*.

    ## [중요] 이 절반이 없으면 stale 은 영원히 안 가라앉는다

    비교의 한쪽(`stored`)을 아무도 안 올리면 같은 클래스가 **재합성을 몇 번 돌려도 계속
    stale** 이고, 매 사이클 LLM 을 같은 대상에 태운다. 실측 2026-08-15: 우리 저장소에
    `class_ontology` 를 쓰는 코드가 0건이라 그 상태였다.

    ## [중요] 원본과 다르게 둔 것 — **필드 하나만** 갱신한다

    원본은 objects 를 통째로 다시 쓰면서 스탬프를 얹는다. 그래도 되는 이유는 **원본의
    잠금이 `actions`/`invariants` 전용**이기 때문이다(`load_locked_items(subdir)`).
    우리는 받아온 스냅샷 오브젝트 112개가 **전부 `protected`** 라, 통째로 쓰면
    `merge_preserve_locked` 가 새 값을 버려 **스탬프가 영영 안 들어간다.**

    그래서 워터마크 필드만 제자리에서 올린다. 잠금의 목적은 **본문**(설명·근거·별칭)이
    재생성으로 얕아지지 않게 하는 것이지, 기계가 찍는 리비전 표식을 얼리는 것이 아니다 —
    얼리면 그 도메인은 영원히 재합성 대상으로 남아 **보호가 의도하지 않은 비용**을 만든다.
    (`package.HUMAN_FIELDS` 의 정확한 거울이다: 사람 필드는 이월하고, 기계 표식은 갱신한다.)

    ## 안 옮긴 것 — DB 쪽 절반

    원본은 `class_graph.upsert_class_source_commit` 으로 DB 에도 찍는다. 우리 그 표는
    **행이 0** 이고 원본 함수 자신이 *"행이 없으면 no-op"* 이라 **옮겨도 아무 일도 일어나지
    않는다.** 게다가 `#189` 가 그 표에 쓰는 경로를 *"우리가 없앤 이중 소스 드리프트를
    되살린다"* 로 판정했다. [중요] **재범위는 닫지 않는다** — 그 표를 쓰게 되는 날 같이 본다.
    """
    root = paths.ontology / "domains" / domain
    manifest = yaml_io.read(root / "domain.yaml") or {}
    from . import hierarchy
    n = 0
    for rel in manifest.get("objects") or []:
        p = root / str(rel)
        obj = yaml_io.read(p)
        if not isinstance(obj, dict) or hierarchy.is_domain_ref(obj):
            continue
        name = obj.get("name")
        if not name or (classes is not None and name not in set(classes)):
            continue
        latest = latest_commit(paths, obj.get("file") or "")
        # [중요] **`-1` 도 찍는다** (원본 그대로 — `o["source_commit"] = rev` 는 무조건이고
        # `rev != "-1"` 은 카나리 집계용일 뿐이다). 처음엔 *"모르는 값으로 아는 값을 덮는
        # 퇴행"* 이라 보고 건너뛰게 짰는데, **그러면 수렴하지 않는다** — 실측 2026-08-15:
        # `GlobalEventSystem` 의 5개는 오브젝트에 실 리비전이 있고 그 **컨텍스트 문서가
        # 리비전을 잃은** 상태(리포트 16 §12.7 의 물려받은 σ.7 손상)라, 건너뛰면 그 도메인이
        # **매 사이클 재합성 대상**으로 영원히 남는다.
        #
        # 이 필드의 뜻이 *"우리가 아는 가장 좋은 리비전"* 이 아니라 **"이 합성이 반영한
        # 문서가 그때 말한 값"** 이기 때문이다. 문서가 모른다고 말하면 `-1` 이 사실이다.
        # [주의] 문서 손상 자체는 여기서 알릴 일이 아니다 — `context_audit` 의
        # `recent_but_empty` 가 그 자리다(이미 이식돼 있다).
        if str(obj.get("source_commit") or "") == latest:
            continue
        obj["source_commit"] = latest
        if yaml_io.write(p, obj):
            n += 1
    return n


def summary(results: list) -> str:
    """[중요] **「전부 최신」과 「판정 불가가 있다」를 가른다** (`#275`).

    종전 문구 *"stale 도메인 없음 — 재합성할 것이 없다"* 는 판정 불가가 있을 때 **거짓**이다:
    재합성할 것이 없는 이유가 「최신이라서」가 아니라 「알 수 없어서」일 수 있다.
    """
    if not results:
        return "stale 도메인 없음 — 재합성할 것이 없다"
    stale_rows = [r for r in results if r.stale]
    unk = sum(r.unknown for r in results)
    head = " · ".join(f"{r.domain}({r.reason})" for r in results)
    if not stale_rows and unk:
        return (f"{head}\n[중요] **재합성 대상은 없지만 판정 불가 {unk}건이 있다** — "
                f"「최신이다」가 아니라 「알 수 없다」다(`source_commit` 부재, `#275`). "
                f"소스가 바뀌어 재합성되면 그때 스탬프가 붙어 판정 가능해진다")
    if unk:
        return f"{head}\n[주의] 그중 판정 불가 {unk}건 — 「최신」이 아니라 「알 수 없음」이다"
    return head
