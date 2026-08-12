"""도메인 패키지 로더 — 🔴 **원전 그대로 복각** (`AgentTest/mcp/context_search/ontology_route_loaders.py`).

사용자 지시 2026-08-13: *"그대로 복각하라고"*. 원전 온톨로지 뷰어(3,700줄)를 우리 스택에 올린다.

## 🔴 왜 거의 그대로 옮겼나 — **데이터 레이아웃이 같다**

    원전   <base>/.claude/ontology/domains/<도메인>/domain.yaml + L{1,2,3}/{objects,actions,invariants}/*.yaml
    우리   <프로젝트>/ontology/domains/<도메인>/domain.yaml      + L{1,2,3}/{objects,actions,invariants}/*.yaml

같은 구조다(우리 트윈이 원전 스냅샷을 이어받았으므로). 그래서 **바꾼 것은 경로 두 곳과 YAML
파서 import 뿐**이고 로직은 손대지 않았다 — 응답 모양이 조금이라도 달라지면 원전 프론트엔드
(`domain.html` 1,056줄)가 그대로 못 돈다.

⚠️ **이 파일을 "정리" 하지 말 것.** 원전과 diff 가 나는 만큼 프론트엔드가 깨진다.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..ontology import yaml_io


def parse_domain_yaml(yaml_path: Path) -> Optional[dict]:
    """🔴 원전 `domain_index.parse_domain_yaml` 대체 — 우리 YAML 리더를 쓴다.

    우리는 PyYAML 의존 0 으로 **우리가 쓴 것만** 읽는 파서를 갖고 있다(`ontology/yaml_io.py`).
    ⚠️ `yaml_io.load` 는 **텍스트**를 받고 `yaml_io.read` 가 경로를 받는다 — 실측 2026-08-13 에
    경로를 `load` 에 넘겨 **필드가 전부 비어 나왔다**(예외도 안 났다: 경로 문자열을 YAML 로
    파싱해 `{}` 를 돌려줬다). 조용히 빈 값을 주는 실패라 화면이 "데이터 없음" 처럼 보였다.

    실패를 `None` 으로 접는 것은 원전과 같은 계약이다 — 뷰어가 항목 하나 때문에 죽지 않는다.
    """
    try:
        return yaml_io.read(yaml_path)
    except Exception:                                     # noqa: BLE001
        return None


def _domains_root(base_dir: Path) -> Path:
    """🔴 우리 경로. `base_dir` 는 `ProjectPaths.root`(트윈 데이터 디렉토리)다."""
    return base_dir / "ontology" / "domains"


def _file_freshness(path: Path) -> dict:
    """Phase η.12.1 — 항목 파일 mtime 기반 신선도 (레거시 폴백).

    stat 실패(권한·경합) 시 조용히 None 필드로 — 신선도 부재가 항목 자체의 부재로
    오인되면 안 되므로 예외를 삼키고 값만 비운다.

    Phase η.12.14 (2026-07-12) 이후 invariants/actions 는 `_item_freshness` 를 우선
    쓴다 — mtime 은 git 체크아웃/클론 시 리셋되는 신뢰도 낮은 신호라서, 파일 내용에
    직접 찍힌 `synthesized_at` 이 있으면 그쪽이 우선이다. 이 함수는 그 필드가 아직
    없는 구버전 파일(재합성 전)·objects·domain manifest 용 폴백으로 남는다.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"updated_at": None, "days_ago": None}
    updated = datetime.fromtimestamp(mtime)
    days_ago = max(0, (datetime.now() - updated).days)
    return {"updated_at": updated.strftime("%Y-%m-%d"), "days_ago": days_ago}


def _item_freshness(data: dict, path: Path) -> dict:
    """Phase η.12.14 (2026-07-12) — invariant/action 항목의 신선도.

    합성 시점에 YAML 내용 자체에 찍히는 `synthesized_at`(`YYYY-MM-DD HH:MM`, 사용자
    결정 — 해시 비교 없이 합성 때마다 단순 갱신)을 우선 사용한다. mtime 과 달리
    파일이 복사·재체크아웃돼도 내용에 실려있어 값이 보존된다. 아직 재합성 전이라
    이 필드가 없는 구버전 파일은 `_file_freshness`(mtime) 로 폴백.
    """
    stamped = data.get("synthesized_at") if isinstance(data, dict) else None
    if stamped:
        parsed_dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed_dt = datetime.strptime(stamped, fmt)
                break
            except (ValueError, TypeError):
                continue
        if parsed_dt is not None:
            days_ago = max(0, (datetime.now() - parsed_dt).days)
            return {"updated_at": stamped, "days_ago": days_ago}
    return _file_freshness(path)


def _class_graph_db_path(base_dir: Path) -> Path:
    """🔴 우리 경로 — 그래프 wrapper 시각화가 이 DB 의 `parent` 를 읽는다."""
    return base_dir / "class_graph.db"


def _load_parents(base_dir: Path, class_names: list[str]) -> dict:
    """class_graph.db 에서 주어진 클래스들의 직접 부모 1단 조회.

    Returns:
        {class_name: parent_name or ""} — DB 부재나 미분류 시 빈 dict / 빈 문자열.
    """
    db = _class_graph_db_path(base_dir)
    if not db.exists() or not class_names:
        return {}
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except Exception:
        return {}
    out: dict = {}
    try:
        # IN 절 batch 조회 — 도메인 1개 객체 수 보통 10~30
        placeholders = ",".join("?" for _ in class_names)
        try:
            rows = conn.execute(
                f"SELECT name, parent FROM classes WHERE name IN ({placeholders})",
                class_names,
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        for name, parent in rows:
            out[name] = parent or ""
    finally:
        conn.close()
    return out


def list_domains(base_dir: Path) -> list[dict]:
    """모든 도메인 패키지 walk → 요약 list (게시판용)."""
    root = _domains_root(base_dir)
    out: list[dict] = []
    if not root.exists():
        return out
    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir():
            continue
        manifest_path = pkg / "domain.yaml"
        if not manifest_path.exists():
            continue
        data = parse_domain_yaml(manifest_path) or {}
        summary = str(data.get("summary") or "")
        summary_head = summary.split("\n")[0][:120] if summary else ""
        # ⚠️ **원전과 다른 유일한 로직** (실측 2026-08-13): 원전은 여기서 평면 `pkg/objects` 만
        #    글로브해서, L-dir 레이아웃(`L1/objects/…`)에서는 **모든 도메인이 0개로 보인다.**
        #    같은 파일이 이미 `_glob_object_yamls`(L-dir 지원)를 갖고 있으므로 그것을 쓴다 —
        #    원전의 버그를 그대로 복각하면 게시판이 전부 "objects 0" 이 된다.
        objs = _glob_object_yamls(pkg)
        acts = _glob_action_yamls(pkg)
        out.append({
            "name": pkg.name,
            "tier": data.get("tier"),
            "summary_head": summary_head,
            "objects_count": len(objs),
            "actions_count": len(acts),
            "tags": data.get("tags") or [],
            "parent_domain": str(data.get("parent_domain") or ""),
        })
    return out


def domain_link_info(base_dir: Path, domain_name: str) -> dict:
    """도메인 간 링크 정보 (2026-06-03 뷰어 계층/연관 링크).

    모든 도메인 manifest 의 parent_domain 을 walk 해 (a) 이 도메인의 자식 목록,
    (b) 이 도메인의 부모, (c) 전체 도메인명 set (협력 도메인 linkify 판정용) 산출.

    Returns:
        {"sub_domains": [str], "parent_domain": str, "known_domains": [str],
         "collaborated_by": [str]}  # 역참조 — 이 도메인을 협력으로 지정한 다른 도메인
    """
    root = _domains_root(base_dir)
    known: list[str] = []
    sub_domains: list[str] = []
    collaborated_by: list[str] = []
    parent = ""
    if not root.exists():
        return {"sub_domains": [], "parent_domain": "", "known_domains": [], "collaborated_by": []}
    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir():
            continue
        manifest = pkg / "domain.yaml"
        if not manifest.exists():
            continue
        known.append(pkg.name)
        data = parse_domain_yaml(manifest) or {}
        p = str(data.get("parent_domain") or "")
        if p == domain_name:
            sub_domains.append(pkg.name)
        if pkg.name == domain_name and p:
            parent = p
        # 역참조 — 다른 도메인의 collaborates_with 항목 선행 토큰이 이 도메인이면 수집.
        # (collaborates_with 는 "DomainName — 설명" prose, viewer linkify 와 동일 선행 식별자 규칙.)
        # 단방향 선언이라도 양쪽 페이지에서 상호 탐색 가능하게 (parent_domain→sub_domains 와 동일 정신).
        if pkg.name != domain_name:
            for entry in (data.get("collaborates_with") or []):
                m = re.match(r"\s*([A-Za-z0-9_]+)", str(entry))
                if m and m.group(1) == domain_name:
                    collaborated_by.append(pkg.name)
                    break
    return {
        "sub_domains": sorted(sub_domains),
        "parent_domain": parent,
        "known_domains": sorted(known),
        "collaborated_by": sorted(set(collaborated_by)),
    }


# Phase η.6.2 — L-dir glob 헬퍼. 평면 `pkg/objects` 폴백 (옛 패키지 호환, drift 잔재).
_LAYER_DIRS = ("L1", "L2", "L3")


def _glob_object_yamls(pkg: Path) -> list[Path]:
    """패키지 안 모든 object yaml (L1/L2/L3 + 옛 평면)."""
    out: list[Path] = []
    for L in _LAYER_DIRS:
        d = pkg / L / "objects"
        if d.exists():
            out.extend(sorted(d.glob("*.yaml")))
    # 옛 평면 잔재 호환 (마이그레이션 사이 일시 깨짐 회피)
    flat = pkg / "objects"
    if flat.exists():
        out.extend(sorted(flat.glob("*.yaml")))
    return out


def _glob_action_yamls(pkg: Path) -> list[Path]:
    out: list[Path] = []
    for L in _LAYER_DIRS:
        d = pkg / L / "actions"
        if d.exists():
            out.extend(sorted(d.glob("*.yaml")))
    flat = pkg / "actions"
    if flat.exists():
        out.extend(sorted(flat.glob("*.yaml")))
    return out


def _glob_invariant_yamls(pkg: Path) -> list[Path]:
    """Phase η.7.1 — L{n}/invariants/*.yaml glob (옛 평면 폴백 없음 — 옛 manifest 배열은 별경로)."""
    out: list[Path] = []
    for L in _LAYER_DIRS:
        d = pkg / L / "invariants"
        if d.exists():
            out.extend(sorted(d.glob("*.yaml")))
    return out


# Phase η.7.4 — layer 책임 서술 (description.md, markdown + frontmatter)
_DESC_FILENAME = "description.md"
_DESC_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)
_DESC_COMMENT_RE = re.compile(r"<!--.*?-->\s*", re.S)


def load_layer_description(
    base_dir: Path, domain_name: str, layer: str
) -> Optional[dict]:
    """Phase η.7.4 — 도메인 특정 layer 의 책임 서술 (L{n}/description.md) 로드.

    description.md 는 markdown + frontmatter (verified_by_user/layer/created). 자동 생성
    주석(`<!-- ... -->`)은 본문에서 제거. PyYAML 의존성 0 — 경량 frontmatter 파싱.

    Returns:
        {"domain", "layer" ('L1'/'L2'/'L3'), "verified_by_user" (bool), "created", "body"}
        도메인/layer/파일 부재 시 None.
    """
    L = str(layer).strip().upper()
    if L not in _LAYER_DIRS:
        return None
    p = _domains_root(base_dir) / domain_name / L / _DESC_FILENAME
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return None
    m = _DESC_FM_RE.match(text)
    fm_text, body = (m.group(1), m.group(2)) if m else ("", text)
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    verified = str(fm.get("verified_by_user", "")).strip().lower() in ("true", "1", "yes", "on")
    body = _DESC_COMMENT_RE.sub("", body).strip()
    return {
        "domain": domain_name,
        "layer": L,
        "verified_by_user": verified,
        "created": fm.get("created", ""),
        "body": body,
    }


def load_all_layer_descriptions(base_dir: Path, domain_name: str) -> dict:
    """도메인의 L1/L2/L3 description 일괄 로드 → {"L1": {...}, ...} (있는 것만)."""
    out: dict = {}
    for L in _LAYER_DIRS:
        d = load_layer_description(base_dir, domain_name, L)
        if d:
            out[L] = d
    return out


def _find_object_yaml(pkg: Path, safe_name: str) -> Optional[Path]:
    """L*/objects/<name>.yaml 우선, 옛 평면 폴백."""
    for L in _LAYER_DIRS:
        p = pkg / L / "objects" / f"{safe_name}.yaml"
        if p.exists():
            return p
    p = pkg / "objects" / f"{safe_name}.yaml"
    return p if p.exists() else None


def _find_action_yaml(pkg: Path, safe_name: str) -> Optional[Path]:
    for L in _LAYER_DIRS:
        p = pkg / L / "actions" / f"{safe_name}.yaml"
        if p.exists():
            return p
    p = pkg / "actions" / f"{safe_name}.yaml"
    return p if p.exists() else None


def load_domain_package(base_dir: Path, domain_name: str) -> Optional[dict]:
    """단일 도메인 패키지 전체 로드 — manifest + objects + actions (L-dir glob, η.6.2)."""
    root = _domains_root(base_dir)
    pkg = root / domain_name
    if not pkg.is_dir():
        return None
    manifest_path = pkg / "domain.yaml"
    if not manifest_path.exists():
        return None
    manifest = parse_domain_yaml(manifest_path) or {}

    objects: list[dict] = []
    for yaml_path in _glob_object_yamls(pkg):
        data = parse_domain_yaml(yaml_path)
        if data:
            objects.append(data)

    # objects 의 parent 정보 보강 — class_graph.db 조회 (compound nodes wrapper 시각화용)
    if objects:
        class_names = [str(o.get("name", "")) for o in objects if o.get("name")]
        parents = _load_parents(base_dir, class_names)
        for obj in objects:
            name = obj.get("name")
            if name and name in parents:
                obj["parent"] = parents[name]

    actions: list[dict] = []
    for yaml_path in _glob_action_yamls(pkg):
        data = parse_domain_yaml(yaml_path)
        if data:
            actions.append(data)

    invariants: list[dict] = []
    for yaml_path in _glob_invariant_yamls(pkg):
        data = parse_domain_yaml(yaml_path)
        if data:
            invariants.append(data)

    return {
        "name": domain_name,
        "manifest": manifest,
        "objects": objects,
        "actions": actions,
        "invariants": invariants,
        # Phase η.7.4 — layer별 책임 서술 (viewer 사이드바 박스용). 있는 layer 만.
        "layer_descriptions": load_all_layer_descriptions(base_dir, domain_name),
    }


def load_object(base_dir: Path, domain_name: str, class_name: str) -> Optional[dict]:
    """단일 오브젝트 yaml 로드 (L-dir glob, η.6.2)."""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", class_name)
    p = _find_object_yaml(_domains_root(base_dir) / domain_name, safe_name)
    return parse_domain_yaml(p) if p else None


def load_action(base_dir: Path, domain_name: str, action_name: str) -> Optional[dict]:
    """단일 액션 yaml 로드 (L-dir glob, η.6.2)."""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", action_name)
    p = _find_action_yaml(_domains_root(base_dir) / domain_name, safe_name)
    return parse_domain_yaml(p) if p else None


# ─────────────────────────────────────────────────────────────────
# 소비용 ontology 조회 헬퍼 (2026-05-25 회사 환경 Claude 제안)
# ─────────────────────────────────────────────────────────────────

def find_class_domain(base_dir: Path, class_name: str) -> Optional[str]:
    """클래스명 → 소속 도메인 (class_ontology DB lookup).

    매핑 없거나 NULL (archive) 시 None.
    """
    db = _class_graph_db_path(base_dir)
    if not db.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except Exception:
        return None
    try:
        try:
            row = conn.execute(
                "SELECT ontology_domain FROM class_ontology WHERE class_name = ?",
                (class_name,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row and row[0]:
            return row[0]
        return None
    finally:
        conn.close()


def load_domain_manifest_only(base_dir: Path, domain_name: str) -> Optional[dict]:
    """단일 도메인 manifest 만 (objects/actions yaml 제외 — 가볍게).

    Returns:
        {summary, core_responsibilities, boundary, invariants, invariants_candidates,
         collaborates_with, tags, tier, ...}
        도메인 부재 시 None.
    """
    manifest_path = _domains_root(base_dir) / domain_name / "domain.yaml"
    if not manifest_path.exists():
        return None
    data = parse_domain_yaml(manifest_path)
    if data is None:
        return None
    # name 명시 (manifest 에 domain 키 있지만 일관성)
    data["name"] = domain_name
    # 도메인 계층·연관 (2026-06-03) — 소비 측 네비게이션. layer 가 깊이라면 이건 넓이:
    # 상위(parent_domain)·하위(sub_domains)·연관(collaborates_with/collaborated_by) 으로 이동.
    links = domain_link_info(base_dir, domain_name)
    data["sub_domains"] = links.get("sub_domains", [])
    data["collaborated_by"] = links.get("collaborated_by", [])
    data.setdefault("parent_domain", links.get("parent_domain", ""))
    data["freshness"] = _file_freshness(manifest_path)
    return data
