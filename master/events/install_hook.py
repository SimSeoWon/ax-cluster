"""Gitea `post-receive` 훅 설치 — root 가 필요하다 (PLAN §5.4.5-a).

    .venv/bin/python -m master.events.install_hook --check
    .venv/bin/python -m master.events.install_hook --apply

[중요] **`pkexec` 로 마스터가 직접 처리한다.** 사용자에게 명령을 떠넘기지 않는다는 것이
이 저장소의 규약이다.

하는 일 세 가지:

1. **스풀 권한** — `~/ax-spool/{tmp,incoming,claimed,rejected}` 를 `sim:gitea` + **2775**
   (setgid)로 맞춘다. 훅은 `gitea` 로 돌고 소비자는 `sim` 으로 도는데, setgid 가 없으면
   훅이 만든 파일의 그룹이 `gitea` 가 아니게 되어 **소비자가 지우지 못한다.**
2. **`ax-project-id`** — 저장소별 표시용 project_id 를 훅 옆에 둔다. 경로에서 유추하지
   않는 이유는 Gitea 가 표시 이름과 디스크 이름을 따로 쓰기 때문이다(§5.5.4-④).
3. **훅 복사** — `post_receive_hook.py` 를 `hooks/post-receive.d/ax-index` 로.

[주의] **Gitea 의 기본 `post-receive` 훅을 건드리지 않는다.** `post-receive.d/` 는 Gitea 가
여러 훅을 나란히 두라고 만든 자리다. 기본 `gitea` 훅을 덮으면 PR·웹훅이 죽는다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..projects.config import Registry
from .spool import DEFAULT_SPOOL, _SUBDIRS

GITEA_ROOT = Path("/var/lib/gitea/gitea-repositories")
HOOK_NAME = "ax-index"
SOURCE = Path(__file__).resolve().parent / "post_receive_hook.py"


@dataclass
class Target:
    project: str
    project_id: str          # 표시용 — 'Sim/ModularStage'
    repo_dir: Path           # bare 저장소 — 디스크는 소문자다

    @property
    def hook_dir(self) -> Path:
        return self.repo_dir / "hooks" / "post-receive.d"

    @property
    def hook_path(self) -> Path:
        return self.hook_dir / HOOK_NAME

    @property
    def id_path(self) -> Path:
        return self.hook_dir / "ax-project-id"


def _run(cmd: list[str], *, root: bool = False) -> tuple[int, str]:
    full = (["pkexec"] + cmd) if root else cmd
    p = subprocess.run(full, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def targets(registry: Registry | None = None) -> list[Target]:
    """등록된 프로젝트 → 훅 대상. **디스크 경로는 소문자**다 (§5.5.4-④)."""
    from ..projects.config import ProjectConfig, project_id_disk_path

    reg = registry or Registry.load()
    out = []
    for name in reg.names:
        cfg = ProjectConfig.load(reg.dir_of(name) / "config.yaml")
        pid = (cfg.project_id or "").strip()
        if not pid:
            continue
        # [중요] 표시용(`Sim/ModularStage`)과 디스크(`sim/modularstage`)를 갈라 쓴다 (§5.5.4-④).
        #    훅에 넣는 것은 표시용, 경로를 만드는 것은 디스크용이다.
        # [주의] bare 저장소는 `<이름>.git` 이다. `project_id_disk_path` 는 접미사를 안 붙이므로
        #    여기서 붙인다 — 빼먹으면 존재하지 않는 경로를 점검하고 "미설치" 로 보고한다.
        out.append(Target(project=name, project_id=pid,
                          repo_dir=GITEA_ROOT / (project_id_disk_path(pid) + ".git")))
    return out


def check(targets_: list[Target] | None = None) -> list[str]:
    """설치 상태를 **읽기만** 해서 보고한다. 고치지 않는다."""
    lines = []
    spool = Path(os.environ.get("AX_EVENT_SPOOL") or DEFAULT_SPOOL)
    lines.append(f"스풀 {spool}")
    for d in _SUBDIRS:
        p = spool / d
        if not p.is_dir():
            lines.append(f"  [실패] {d}/ 없음")
            continue
        st = p.stat()
        import grp
        gname = grp.getgrgid(st.st_gid).gr_name
        mode = oct(st.st_mode & 0o7777)
        ok = gname == "gitea" and (st.st_mode & 0o2070) == 0o2070
        lines.append(f"  {'OK' if ok else 'FAIL'} {d}/ group={gname} mode={mode}"
                     + ("" if ok else "  ← sim:gitea 2775 여야 한다"))
    for t in (targets_ if targets_ is not None else targets()):
        rc, out = _run(["test", "-e", str(t.hook_path)], root=True)
        installed = rc == 0
        lines.append(f"{t.project} ({t.project_id})")
        lines.append(f"  {'OK' if installed else 'FAIL'} 훅 {t.hook_path}")
        rc2, _ = _run(["test", "-e", str(t.id_path)], root=True)
        lines.append(f"  {'OK' if rc2 == 0 else 'FAIL'} ax-project-id")
    return lines


def apply(targets_: list[Target] | None = None, *, progress=None) -> int:
    """설치한다. root 가 필요한 부분만 `pkexec` 로 올린다."""
    def say(m):
        if progress:
            progress(m)

    spool = Path(os.environ.get("AX_EVENT_SPOOL") or DEFAULT_SPOOL)
    for d in _SUBDIRS:
        (spool / d).mkdir(parents=True, exist_ok=True)
    # setgid 를 붙여야 훅(gitea)이 만든 파일의 그룹이 gitea 로 유지되고,
    # gitea 그룹에 속한 sim(소비자)이 읽고 지울 수 있다.
    rc, out = _run(["chgrp", "-R", "gitea", str(spool)], root=True)
    if rc != 0:
        raise SystemExit(f"스풀 그룹 변경 실패: {out}")
    rc, out = _run(["chmod", "-R", "2775", str(spool)], root=True)
    if rc != 0:
        raise SystemExit(f"스풀 권한 변경 실패: {out}")
    say(f"스풀 권한 설정: {spool} → sim:gitea 2775")

    n = 0
    for t in (targets_ if targets_ is not None else targets()):
        rc, out = _run(["test", "-d", str(t.repo_dir)], root=True)
        if rc != 0:
            say(f"[주의]  {t.project}: bare 저장소가 없다 — 건너뜀 ({t.repo_dir})")
            continue
        _run(["mkdir", "-p", str(t.hook_dir)], root=True)
        rc, out = _run(["install", "-o", "gitea", "-g", "gitea", "-m", "755",
                        str(SOURCE), str(t.hook_path)], root=True)
        if rc != 0:
            raise SystemExit(f"{t.project}: 훅 복사 실패 — {out}")
        # project_id 는 파일로. 셸 인용을 피하려고 tee 대신 python 으로 쓴다.
        rc, out = _run(["python3", "-c",
                        "import sys,pathlib;p=pathlib.Path(sys.argv[1]);"
                        "p.write_text(sys.argv[2]+chr(10),encoding='utf-8');"
                        "import os;os.chmod(p,0o644)",
                        str(t.id_path), t.project_id], root=True)
        if rc != 0:
            raise SystemExit(f"{t.project}: ax-project-id 기록 실패 — {out}")
        _run(["chown", "gitea:gitea", str(t.id_path)], root=True)
        say(f"[완료] {t.project} ({t.project_id}) → {t.hook_path}")
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Gitea post-receive 훅 설치 (root 필요)")
    ap.add_argument("--apply", action="store_true", help="실제로 설치한다 (기본은 점검)")
    args = ap.parse_args(argv)

    if args.apply:
        n = apply(progress=lambda m: print(f"  {m}"))
        print(f"\n훅 {n}개 설치 완료. 점검:")
    for line in check():
        print(line if line.startswith(" ") else f"\n{line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
