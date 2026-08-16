"""도메인 MD 필드 편집 (#189) 계약 테스트.

재는 것 다섯:
    ① 필드 단위     제공 인자만 바뀐다 — frontmatter 스칼라 교체/추가/제거 · 섹션 교체/신설
    ② 두 갈래       parent/tags/collab → manifest 직접 패치 + 인덱스 · summary/status → MD-only
    ③ 지점 7        [중요] tags 통째 치환으로 사라지는 **한글 태그를 크게 보고** (#194 판정)
    ④ 지점 5        parent_domain 이름은 조용히 정규화하지 않고 **거부** (한글 허용·위험문자 거부)
    ⑤ 방어          not_found · frontmatter 없음 · noop · 인덱스 실패 fail-soft

실행: .venv/bin/python master/test_edit_field.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.ontology.edit_field import edit_domain_field          # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class P:
    def __init__(self, root: Path):
        self.root = root
        self.ontology = root / "ontology"


MD = """---
tags: [MissionSystem, 미션, 태스크, TaskSystem]
category: 도메인/D1
type: domain
status: active
source_documents:
  - Source/M/A.md
---

## 시스템 개요

원래 개요.

## 협력 도메인
- OldPartner

## 설계 패턴

싱글턴.
"""

MANIFEST = """domain: D1
tier: 3
summary: '요약'
objects:
  - L1/objects/UA.yaml
"""


def fixture(with_manifest=True):
    p = P(Path(tempfile.mkdtemp(prefix="ax-ef-")))
    d = p.root / "context" / "_domains"
    d.mkdir(parents=True)
    (d / "D1.md").write_text(MD, encoding="utf-8")
    if with_manifest:
        m = p.ontology / "domains" / "D1"
        m.mkdir(parents=True)
        (m / "domain.yaml").write_text(MANIFEST, encoding="utf-8")
    return p


def md_text(p):
    return (p.root / "context" / "_domains" / "D1.md").read_text(encoding="utf-8")


def manifest_text(p):
    return (p.ontology / "domains" / "D1" / "domain.yaml").read_text(encoding="utf-8")


# ── ① 필드 단위 + ② 두 갈래 ─────────────────────────────────

def test_field_edits_and_two_lanes():
    p = fixture()
    synced = []
    r = edit_domain_field(p, "D1", parent_domain="MissionRuntime",
                          collaborates_with=["MissionRuntime", "UiManagement"],
                          indexer=lambda paths: synced.append(1))
    check("[중요] 제공 인자만 바뀐다", r["status"] == "ok"
          and sorted(r["changed"]) == ["collaborates_with", "parent_domain"], str(r))
    t = md_text(p)
    check("parent_domain 이 frontmatter 에 추가된다", "parent_domain: MissionRuntime" in t)
    check("협력 도메인 섹션이 교체된다", "- UiManagement" in t and "- OldPartner" not in t)
    check("다른 섹션은 그대로 (## 설계 패턴)", "싱글턴." in t and "원래 개요." in t)
    m = manifest_text(p)
    check("[중요] 패스스루 메타는 manifest 직접 패치 (domain: 직후 삽입)",
          "parent_domain: MissionRuntime" in m and "collaborates_with:" in m
          and "- UiManagement" in m, m[:200])
    check("[중요] 인덱스 재빌드가 불린다 (LLM 0)", synced == [1]
          and sorted(r["manifest_patched"]) == ["collaborates_with", "parent_domain"])

    r2 = edit_domain_field(p, "D1", summary="새 개요다.", status="draft",
                           indexer=lambda paths: synced.append(2))
    t2 = md_text(p)
    check("summary → ## 시스템 개요 교체", "새 개요다." in t2 and "원래 개요." not in t2)
    check("status 교체", "status: draft" in t2)
    check("[중요] MD-only 갈래 — manifest 안 만지고 인덱스 안 부른다 (eventually-consistent)",
          r2["manifest_patched"] == [] and synced == [1] and "note" in r2, str(r2))

    r3 = edit_domain_field(p, "D1", parent_domain="", indexer=lambda paths: None)
    check("parent_domain 빈값 = 라인 제거", "parent_domain" not in md_text(p)
          and r3["status"] == "ok")


# ── ③ 지점 7 — 한글 태그 소실 보고 ───────────────────────────

def test_kr_tag_loss_reported():
    p = fixture()
    warned = []
    r = edit_domain_field(p, "D1", tags=["MissionSystem", "TaskSystem", "미션"],
                          indexer=lambda paths: None, logf=warned.append)
    check("[중요] 치환으로 사라진 한글 태그를 크게 보고 (태스크)",
          r.get("kr_tags_removed") == ["태스크"] and "[중요]" in r.get("warning", ""),
          str(r.get("kr_tags_removed")))
    check("로그로도 말한다", warned and "태스크" in warned[0])
    check("영문 태그 소실은 이 채널이 아니다 (한글만 — 가중치 3.0 층)",
          "MissionSystem" not in str(r.get("kr_tags_removed")))
    check("manifest 의 tags 블록도 패치", "tags:" in manifest_text(p)
          and "- 미션" in manifest_text(p))

    r2 = edit_domain_field(p, "D1", tags=["미션", "새태그"], indexer=lambda paths: None)
    check("남긴 한글 태그는 보고 대상이 아니다", "kr_tags_removed" not in r2, str(r2))


# ── ④ 지점 5 — 이름 거부 ─────────────────────────────────────

def test_parent_name_rules():
    p = fixture()
    r = edit_domain_field(p, "D1", parent_domain="미션런타임", indexer=lambda paths: None)
    check("[중요] 한글 부모 도메인명 허용 (ⓐ)", r["status"] == "ok"
          and "parent_domain: 미션런타임" in md_text(p), str(r))
    r2 = edit_domain_field(p, "D1", parent_domain="a/b", indexer=lambda paths: None)
    check("[중요] 위험문자는 조용히 정규화하지 않고 거부 (원전은 _ 치환 — 우리 원칙이 이긴다)",
          r2["status"] == "error" and "위험문자" in r2["reason"], str(r2))
    check("거부 시 MD 는 안 바뀐다", "parent_domain: 미션런타임" in md_text(p))


# ── ⑤ 방어 ───────────────────────────────────────────────────

def test_defenses():
    p = fixture()
    check("없는 도메인은 not_found",
          edit_domain_field(p, "없는것")["status"] == "not_found")
    check("인자 없으면 noop", edit_domain_field(p, "D1")["status"] == "noop")

    (p.root / "context" / "_domains" / "D2.md").write_text("# frontmatter 없음\n",
                                                           encoding="utf-8")
    check("frontmatter 없으면 error",
          edit_domain_field(p, "D2", status="x")["status"] == "error")

    p2 = fixture(with_manifest=False)
    r = edit_domain_field(p2, "D1", tags=["a"], indexer=lambda paths: None)
    check("manifest 부재 — MD 만 반영, 패치 0 (원전 계약 그대로)", r["status"] == "ok"
          and r["manifest_patched"] == [], str(r))

    def boom(paths):
        raise RuntimeError("인덱스 죽음")

    p3 = fixture()
    r3 = edit_domain_field(p3, "D1", tags=["a"], indexer=boom)
    check("[중요] 인덱스 실패는 fail-soft + 말한다 (편집 자체는 성립)",
          r3["status"] == "ok" and "인덱스 재빌드 실패" in r3.get("index_note", ""), str(r3))


def main() -> int:
    for fn in (test_field_edits_and_two_lanes, test_kr_tag_loss_reported,
               test_parent_name_rules, test_defenses):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_edit_field: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
