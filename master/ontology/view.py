"""도메인 뷰어 — **자립형 HTML 한 장** (소 2.4.2).

## 🔴 서비스를 하나 더 띄우지 않는다

마일스톤이 *"읽기 전용이면 yaml 파싱만으로 가능"* 이라 적어 뒀고, 실제로 그렇다. 서비스를
늘리면 포트·베어러 토큰·ufw 규칙이 따라붙는데(§9.5.6) **읽기 전용 뷰어에 그 공격면을 늘릴
이유가 없다.** 파일 한 장이면 어디서든 열리고, 잃어도 다시 만들면 된다.

⚠️ 이 문서는 **비공개 게임 구조**를 담는다 — 외부에 올리지 않는다. 산출물은 로컬 파일이다.

## 🔴 외부 자원을 쓰지 않는다

CSS·JS 를 인라인한다. CDN 을 물면 **인터넷 없는 자리에서 빈 화면**이 되고, 이 클러스터는
LAN 안에서 도는 것이 전제다.

## 무엇을 보여주나 — 숫자가 아니라 **판단에 필요한 것**

    도메인      요약 · 협력 도메인 · tier
    항목        objects / actions / invariants (본문까지)
    🔒 보호      무엇이 왜 언제 기준으로 (드리프트를 볼 근거)
    ⚠️ 결손      `## 도메인 경계` 가 없는 도메인은 그렇게 표시한다

경계 절이 없으면 합성이 다른 도메인의 클래스를 끌어온다(실측: 7개 중 6개에 없다). 뷰어가
그걸 **눈에 보이게** 하는 것이 숫자를 예쁘게 보여주는 것보다 값이 크다.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths
from . import yaml_io

OUT_NAME = "domains.html"


@dataclass
class Item:
    kind: str
    name: str
    layer: str = ""
    text: str = ""
    file: str = ""
    protected: bool = False
    protected_at: str = ""
    protected_why: str = ""
    verified: bool = False
    aliases: list = field(default_factory=list)


@dataclass
class Domain:
    name: str
    orphans: list = field(default_factory=list)   # 🔴 파일은 있는데 manifest 목록에 없다
    summary: str = ""
    tier: str = ""
    collaborators: list = field(default_factory=list)
    items: list = field(default_factory=list)
    has_boundary: bool = False

    def of(self, kind: str) -> list:
        return [i for i in self.items if i.kind == kind]


def collect(paths: ProjectPaths) -> list:
    """패키지에서 읽는다. **읽기 전용.**"""
    root = paths.ontology / "domains"
    out: list = []
    if not root.is_dir():
        return out
    for d in sorted(x for x in root.iterdir() if x.is_dir()):
        man = yaml_io.read(d / "domain.yaml")
        if not isinstance(man, dict):
            continue
        dom = Domain(name=d.name, summary=str(man.get("summary") or ""),
                     tier=str(man.get("tier") or ""),
                     collaborators=[str(c) for c in (man.get("collaborates_with") or [])])
        # 🔴 경계 절 유무는 합성 품질을 좌우한다 — 눈에 보이게 한다
        dom.has_boundary = bool(man.get("boundary") or man.get("domain_boundary"))
        for kind in ("objects", "actions", "invariants"):
            # 🔴 **매니페스트를 믿지 않고 파일을 훑는다.** 실측 2026-08-10: 받아온 스냅샷의
            #    MissionEditor 에 목록에 없는 object yaml 이 하나 있었다. 색인 페이로드와
            #    `sync` 는 매니페스트를 근거로 삼으므로 그 클래스는 **검색에도 동기화에도
            #    빠져 있었다** — 매니페스트만 읽는 뷰어였다면 영영 안 보였을 것이다.
            key = "invariants_files" if kind == "invariants" else kind
            listed = {str(r).replace("\\", "/") for r in (man.get(key) or [])}
            for f in sorted((d).rglob(f"*/{kind}/*.yaml")):
                rel = str(f.relative_to(d)).replace("\\", "/")
                if rel not in listed:
                    dom.orphans.append(rel)
                it = yaml_io.read(f)
                if not isinstance(it, dict):
                    continue
                out_item = Item(
                    kind=kind, name=str(it.get("name") or f.stem),
                    layer=f.parent.parent.name,
                    text=str(it.get("text") or it.get("description") or ""),
                    file=str(it.get("file") or ""),
                    protected=it.get("protected") is True,
                    protected_at=str(it.get("protected_at") or ""),
                    protected_why=str(it.get("protected_reason") or ""),
                    verified=it.get("verified_by_user") is True,
                    aliases=[str(a) for a in (it.get("aliases") or [])])
                dom.items.append(out_item)
        out.append(dom)
    return out


_CSS = """
:root{--bg:#fff;--fg:#1a1a1a;--dim:#666;--line:#e2e2e2;--card:#fafafa;--warn:#b23;--ok:#276}
@media(prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e6e6e6;--dim:#9aa;--line:#2c3036;--card:#1c1f24;--warn:#f77;--ok:#7cc}}
*{box-sizing:border-box}
body{margin:0;padding:1.5rem;background:var(--bg);color:var(--fg);
 font:15px/1.65 -apple-system,'Noto Sans KR',Segoe UI,sans-serif}
h1{font-size:1.4rem;margin:0 0 .2rem}
.sub{color:var(--dim);font-size:.86rem;margin-bottom:1rem}
input{width:100%;padding:.6rem .8rem;font-size:1rem;border:1px solid var(--line);
 border-radius:8px;background:var(--card);color:var(--fg);margin-bottom:1rem}
details{border:1px solid var(--line);border-radius:10px;margin:.55rem 0;background:var(--card)}
summary{padding:.7rem .9rem;cursor:pointer;font-weight:600}
.body{padding:0 .9rem .8rem}
.meta{color:var(--dim);font-size:.82rem}
.item{border-top:1px solid var(--line);padding:.55rem 0}
.nm{font-family:ui-monospace,Menlo,monospace;font-weight:600}
.tag{font-size:.72rem;padding:.1rem .4rem;border-radius:5px;border:1px solid var(--line);
 color:var(--dim);margin-left:.35rem;white-space:nowrap}
.warn{color:var(--warn);font-weight:600}
.ok{color:var(--ok)}
.txt{white-space:pre-wrap;margin-top:.2rem}
.hide{display:none}
"""

_JS = """
const q=document.getElementById('q');
q.addEventListener('input',()=>{
  const s=q.value.trim().toLowerCase();
  document.querySelectorAll('details[data-d]').forEach(d=>{
    let any=!s;
    d.querySelectorAll('.item').forEach(it=>{
      const hit=!s||it.dataset.k.includes(s);
      it.classList.toggle('hide',!hit); if(hit)any=true;
    });
    d.classList.toggle('hide',!any);
    if(s&&any)d.open=true; if(!s)d.open=false;
  });
});
"""


def render(paths: ProjectPaths, domains: list, *, head: str = "") -> str:
    """자립형 HTML. 🔴 **외부 자원을 쓰지 않는다.**"""
    e = html.escape
    tot = {k: sum(len(d.of(k)) for d in domains) for k in ("objects", "actions", "invariants")}
    prot = sum(1 for d in domains for i in d.items if i.protected)
    no_boundary = [d.name for d in domains if not d.has_boundary]
    orphans = [(d.name, o) for d in domains for o in d.orphans]

    parts = [f"<h1>{e(paths.name)} · 도메인 뷰어</h1>",
             f'<div class="sub">도메인 {len(domains)} · objects {tot["objects"]} · '
             f'actions {tot["actions"]} · invariants {tot["invariants"]} · 🔒 보호 {prot}'
             + (f' · 트윈 기준 <code>{e(head[:8])}</code>' if head else '') + '</div>']
    if no_boundary:
        # 🔴 이게 뷰어의 첫 화면에 있어야 하는 이유: 경계가 없으면 합성이 남의 클래스를 끌어온다
        parts.append(f'<div class="sub warn">⚠️ <b>도메인 경계 절이 없는 도메인 '
                     f'{len(no_boundary)}개</b> — 합성이 다른 도메인의 클래스를 끌어올 수 '
                     f'있다: {e(", ".join(no_boundary))}</div>')
    if orphans:
        # 🔴 매니페스트에 없는 파일 = 검색·동기화에서 빠진 항목이다
        parts.append(f'<div class="sub warn">🔴 <b>manifest 에 없는 항목 파일 '
                     f'{len(orphans)}개</b> — 색인·sync 는 manifest 를 근거로 삼으므로 '
                     f'이것들은 <b>검색에도 동기화에도 빠져 있다</b>: '
                     + e("; ".join(f"{d}/{o}" for d, o in orphans[:3])) + '</div>')
    parts.append('<input id="q" placeholder="클래스·액션·invariant 이름이나 본문으로 거르기…">')

    for d in domains:
        counts = (f'obj {len(d.of("objects"))} · act {len(d.of("actions"))} · '
                  f'inv {len(d.of("invariants"))}')
        b = ('<span class="tag ok">경계 있음</span>' if d.has_boundary
             else '<span class="tag warn">경계 없음</span>')
        parts.append(f'<details data-d="{e(d.name)}"><summary>{e(d.name)} '
                     f'<span class="tag">{counts}</span>{b}</summary><div class="body">')
        if d.summary:
            parts.append(f'<div class="txt meta">{e(d.summary[:600])}</div>')
        if d.collaborators:
            parts.append(f'<div class="meta">협력: {e(", ".join(c[:60] for c in d.collaborators[:4]))}</div>')
        for kind, label in (("objects", "오브젝트"), ("actions", "액션"),
                            ("invariants", "invariants")):
            items = d.of(kind)
            if not items:
                continue
            parts.append(f'<div class="meta" style="margin-top:.6rem">{label} {len(items)}</div>')
            for i in items:
                key = e((i.name + " " + i.text + " " + " ".join(i.aliases)).lower())
                tags = f'<span class="tag">{e(i.layer)}</span>'
                if i.protected:
                    at = f' {i.protected_at[:8]}' if i.protected_at else ''
                    tags += f'<span class="tag" title="{e(i.protected_why[:200])}">🔒 보호{e(at)}</span>'
                if i.verified:
                    tags += '<span class="tag ok">✔ 검수</span>'
                if i.aliases:
                    tags += f'<span class="tag">별칭 {e(", ".join(i.aliases[:3]))}</span>'
                body = f'<div class="txt">{e(i.text[:700])}</div>' if i.text else ''
                fl = f'<div class="meta">{e(i.file)}</div>' if i.file else ''
                parts.append(f'<div class="item" data-k="{key}">'
                             f'<span class="nm">{e(i.name)}</span>{tags}{body}{fl}</div>')
        parts.append("</div></details>")

    return ("<!doctype html><html lang=ko><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(paths.name)} 도메인</title><style>{_CSS}</style></head><body>"
            + "\n".join(parts) + f"<script>{_JS}</script></body></html>")


def write(paths: ProjectPaths, *, out=None) -> tuple:
    """HTML 을 쓴다. `(경로, 바이트)`. 🔴 **온톨로지는 건드리지 않는다.**"""
    head = ""
    try:
        from ..work import twin_base
        head = twin_base.twin_commit(paths)
    except Exception:                                     # noqa: BLE001
        head = ""
    doms = collect(paths)
    if not doms:
        raise RuntimeError("도메인 패키지가 없다 — 볼 것이 없다")
    p = out or (paths.root / OUT_NAME)
    text = render(paths, doms, head=head)
    p.write_text(text, encoding="utf-8")
    return p, len(text.encode("utf-8"))
