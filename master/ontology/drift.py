"""드리프트 감사 — **트윈과 소스가 언제 어긋났나** (소 2.4.1).

## [중요] "기준 커밋이 다르다" 로는 아무것도 못 말한다

보호 항목에는 `protected_at`(그때의 트윈 커밋)이 적혀 있다. 그런데 커밋 하나만 지나도
전부 다르므로, 그것만으로 깃발을 꽂으면 **240건이 한꺼번에 뜨고 아무도 안 본다.**

그래서 좁힌다 — *"그 사이에 **그 도메인이 근거로 삼은 파일이 실제로 바뀌었는가**"*.
bare 저장소에서 `git diff --name-only <기준> <현재>` 로 잰다(읽기 전용, `sg gitea`).

    protected_at ≠ 현재  그리고  그 도메인 파일이 그 사이 바뀌었다   → [중요] 의심
    protected_at ≠ 현재  인데    그 파일들은 그대로다                → 조용히 넘어간다

## [중요] 감사는 지우지 않는다 — 보고만 한다

`sync` 가 사라진 클래스를 지우지 않는 것과 같은 이유다: **삭제됐는지 그래프가 낡았는지
여기선 모른다.** 판단은 사람이 하고, 수단은 이미 있다(`edit` · `remove(force)` · 보호 해제 후
`refresh`).

## 무엇을 모으나 — 이미 있는 결정적 검사들이다

    verify        유령 호출 (사실 게이트)          ← 보호와 무관하게 돈다
    sync          경로 어긋남 · 그래프에서 사라진 클래스
    stale         컨텍스트 MD 기준으로 낡은 도메인
    protected_at  이 모듈이 더하는 유일한 새 신호

[중요] **설계 규칙 서술은 여전히 자동으로 못 잡는다.** *"디테일 패널은 함수맵으로 라우팅된다"*
같은 문장은 호출 표기가 없어 사실 게이트를 통과한다. `protected_at` + 파일 변경이 그것에
대해 우리가 가진 **유일한 단서**다 — 그래서 이 모듈이 있다.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths

GIT_TIMEOUT = 30


@dataclass
class DomainDrift:
    domain: str
    protected: int = 0
    stale_since: str = ""          # 그 도메인 보호분의 기준 커밋 (섞여 있으면 가장 오래된 것)
    changed_files: list = field(default_factory=list)   # 그 사이 바뀐, 이 도메인의 파일
    ghosts: list = field(default_factory=list)          # verify 실패 사유
    missing: list = field(default_factory=list)         # 그래프에서 사라진 클래스
    path_fixes: int = 0

    @property
    def suspect(self) -> bool:
        """[중요] **의심의 정의** — 근거가 바뀐 채 보호돼 있거나, 검사에 걸렸다."""
        return bool(self.changed_files or self.ghosts or self.missing)

    @property
    def line(self) -> str:
        if not self.suspect:
            return f"  [완료] {self.domain}: 어긋남 없음 (보호 {self.protected})"
        s = f"  [중요] {self.domain}: 보호 {self.protected}"
        if self.changed_files:
            s += (f" · 기준 {self.stale_since[:8]} 이후 **소스 {len(self.changed_files)}개 변경**"
                  f" ({', '.join(f.rsplit('/', 1)[-1] for f in self.changed_files[:3])}…)")
        if self.ghosts:
            s += f" · 유령 {len(self.ghosts)}"
        if self.missing:
            s += f" · 그래프에 없는 클래스 {len(self.missing)}"
        if self.path_fixes:
            s += f" · 경로 어긋남 {self.path_fixes}"
        return s


@dataclass
class Report:
    head: str = ""                 # 현재 트윈 기준 커밋
    domains: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    @property
    def suspects(self) -> list:
        return [d for d in self.domains if d.suspect]

    def render(self) -> str:
        out = [f"드리프트 감사 · 트윈 기준 {self.head[:8] or '미상'} · "
               f"도메인 {len(self.domains)} · [중요] 의심 {len(self.suspects)}", ""]
        out += [d.line for d in self.domains]
        if self.notes:
            out += [""] + [f"  [주의] {n}" for n in self.notes]
        out += ["",
                "[중요] **감사는 지우지 않는다.** 판단은 사람이 한다 — 고치면 `edit`, 빼면 "
                "`remove(force)`, 다시 만들면 보호를 풀고 `refresh --model claude`.",
                "[주의] 설계 규칙 서술(호출 표기 없는 문장)은 자동으로 못 잡는다. 위 '소스 변경' "
                "이 그것에 대한 유일한 단서다."]
        return "\n".join(out)


def _changed_between(paths: ProjectPaths, old: str, new: str) -> list:
    """`git diff --name-only`. **읽기 전용**이고 bare 는 `gitea` 그룹으로 읽는다(§8.5).

    [중요] **`sg` 는 필요할 때만** (`#336` ②) — 판정은 `gitea_group` 한 곳이 한다. 종전에는
    무조건 감쌌고, 그러면 서비스 컨텍스트(`NoNewPrivileges=true`)에서 조용히 빈 목록을
    돌려준다. 이 함수는 실패를 `return []` 로 삼키므로 **드리프트가 0건으로 보였을 것이다.**
    """
    from ..projects.config import ProjectConfig
    from .. import gitea_group
    bare = (ProjectConfig.load(paths.config).bare_path or "").strip()
    if not bare or not old or not new or old == new:
        return []
    cmd = f"git --git-dir={bare} diff --name-only {old} {new}"
    try:
        p = subprocess.run(gitea_group.wrap_shell(cmd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        return []
    if p.returncode != 0:
        return []
    return [ln.strip() for ln in (p.stdout or "").splitlines() if ln.strip()]


def audit(paths: ProjectPaths, *, domain: str = "") -> Report:
    """트윈과 소스의 어긋남을 훑는다. **읽기 전용.**"""
    from . import edit as oe, sync as osync, verify_facts as vf
    from ..work import twin_base

    rep = Report()
    try:
        rep.head = twin_base.twin_commit(paths)
    except Exception as e:                                # noqa: BLE001
        rep.notes.append(f"트윈 기준 커밋을 모른다 ({e}) — 소스 변경 대조를 건너뛴다")

    prot = oe.protected_items(paths, domain)
    by_domain: dict = {}
    for r in prot:
        d = by_domain.setdefault(r["domain"], DomainDrift(domain=r["domain"]))
        d.protected += 1
        at = r.get("at") or ""
        if at and (not d.stale_since or at < d.stale_since):
            d.stale_since = at

    # 보호가 없는 도메인도 검사 대상이다 — 없다고 건강한 게 아니다
    root = paths.ontology / "domains"
    if root.is_dir():
        for p in sorted(x for x in root.iterdir() if x.is_dir()):
            if domain and p.name != domain:
                continue
            by_domain.setdefault(p.name, DomainDrift(domain=p.name))

    for name, d in by_domain.items():
        # ① 근거가 바뀌었나 — [중요] 커밋 차이가 아니라 **파일 변경**으로 좁힌다
        if rep.head and d.stale_since and d.stale_since != rep.head:
            changed = set(_changed_between(paths, d.stale_since, rep.head))
            if changed:
                st = osync.sync_domain(paths, name, apply=False)
                mine = {f for f in changed}
                files = set()
                for obj in (osync._object_files(paths, name)):
                    from . import yaml_io
                    it = yaml_io.read(obj) or {}
                    if it.get("file"):
                        files.add(str(it["file"]))
                d.changed_files = sorted(mine & files) if files else []
                d.path_fixes = len(st.path_fixed)
                d.missing = list(st.missing)
        else:
            st = osync.sync_domain(paths, name, apply=False)
            d.path_fixes = len(st.path_fixed)
            d.missing = list(st.missing)

        # ② 사실 게이트 — 보호 여부와 무관하다
        try:
            res = vf.verify_domain(paths, name)
            d.ghosts = [str(x) for x in (res.findings or [])]
            if res.skipped_reason:
                rep.notes.append(f"{name}: 사실 게이트를 못 돌렸다 — {res.skipped_reason}")
        except Exception:                                 # noqa: BLE001
            pass
        rep.domains.append(d)

    rep.domains.sort(key=lambda x: (not x.suspect, x.domain))
    return rep
