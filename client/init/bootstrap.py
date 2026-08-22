"""체크아웃 부트스트랩 — **레포가 없는 기계에 레포를 놓는다** (`#254`).

## [중요] 원전에 선례가 없다 — census 로 확인했다 (2026-08-22)

`#254` 가 *"착수 시 그 실물을 열어 확인한다(`~/AgentTest`, 인용만 보고 만들지 않는다)"* 라고
못박아서 실제로 열었다. 결과: **`packaging/`·`scripts/`·`tools/`·`watcher/` 에 `git clone`·
`git init` 이 0건**이다. 원전의 개발자는 **이미 체크아웃을 갖고 있었고**(그 안에서 작업했다)
zip 은 도구(`watch.exe` 등)만 그 체크아웃에 배달했다.

즉 이 단계는 **이식 대상이 아니라 우리 위상에서 새로 생긴 것**이다 — 중앙 마스터가 원격 기계에
프로젝트를 놓는 구조는 원전에 없었다. 그래서 설계 근거를 여기 적는다.

[주의] 원전에서 가져올 것이 하나 있다 — `build.bat:274` 의 *"Cleaning runtime leak from dist/
before zip … 이런 게 zip 에 섞이면 클라 PC 가 zip 풀 때 자기 설정이 덮어쓰기됨"*. **PC별 설정을
배포물에 넣지 않는다**는 규칙이고, 우리는 이미 그렇다(`config_for` 가 기계마다 생성한다).

## 클론 주체 — ⓐ 마스터가 SSH (사용자 확정, §12.5-d)

> *"레포 등록할때 서버에서 처리해야 하는 부분, 클라에서 처리하는 부분 모두 이 레포에 저장되고
> 이걸 ssh로 배포해야한다"*

[중요] **`probe` 의 「읽기 전용」 계약은 깨지 않는다** — 클론은 별 단계다. 재는 것과 바꾸는 것을
한 함수에 섞으면 실측이 부작용을 갖는다(`#254` [주의]).

## NS 라이브 런이 가르쳐 준 함정 셋 — 전부 여기서 처리한다 (리포트 31)

    ⓐ 윈도우 소유권   마스터의 SSH 세션이 관리자라 `git clone` 이 만든 `.git` 이
                      `BUILTIN\\Administrators` 소유가 된다 → 사람의 일반 세션에서 git 이 전부
                      거부한다(`fatal: detected dubious ownership`, rc=128). `.33`·`.2` 두 대에서
                      재현했다. [중요] `safe.directory` 로 덮지 않고 `icacls /setowner` 로
                      **맞춘다** — 정상 저장소와 구분되지 않아야 한다
    ⓑ 빈 저장소 브랜치 커밋 0개인 저장소를 클론하면 로컬 브랜치가 **로컬 git 기본값**(`master`)
                      으로 잡힌다. Gitea 기본과 우리 `config.yaml` 은 `main` 이라 그대로 커밋하면
                      설정과 실물이 어긋난다 → `git symbolic-ref HEAD refs/heads/<branch>`
    ⓒ LFS 는 역할별   빌드하는 기계는 에셋 실물이 필요하고(`.2` 134MB), 소스만 판단하는 기계는
                      포인터로 충분하다(`.43` 4MB · git-lfs 미설치). 마스터는 항상 포인터.
                      → `ue5` 능력으로 가른다(선언이 아니라 **probe 실측**이다)
"""
from __future__ import annotations

import shlex

# [중요] 클론 원본은 **Gitea SSH** 다 — `REQUIRE_SIGNIN_VIEW=true` 라 익명 HTTP 는 안 되고
#    (§8.5), 워커에는 셸 없는 git 전용 키가 등록돼 있다. 로컬 bare 경로는 그 기계에 없다.
CLONE_TIMEOUT = 3600            # LFS 실물이 오면 길다 (.2 실측 134MB)
OWNER_TIMEOUT = 600             # icacls /T /C — .2 실측 3,362 파일


def needs_bootstrap(facts) -> bool:
    """이 기계에 체크아웃을 놓아야 하는가. `probe` 의 실측을 그대로 믿는다."""
    return not facts.checkout_ok


def plan_lines(facts, cfg) -> list:
    """`plan` 이 찍을 줄. [중요] **배달 항목으로 나타나야 한다** (`#254` 완료 조건 1) —
    `errors` 에 사유만 실리고 계획에 안 보이면 미완이다."""
    if not needs_bootstrap(facts):
        return []
    lfs = "에셋 실물(LFS)" if wants_lfs(facts) else "LFS 포인터만"
    out = [f"   ⊕ {facts.path} — **체크아웃 없음 → 클론한다** "
           f"({cfg.clone_url or '(clone_url 없음!)'} · 브랜치 {cfg.branch or 'main'} · {lfs})"]
    if facts.windows:
        out.append(f"     · 클론 뒤 소유자를 `{facts.user}` 로 맞춘다 (icacls /setowner) — "
                   f"마스터 SSH 세션이 관리자라 그대로 두면 사람 세션에서 git 이 거부한다")
    out.append("     · 커밋 0개면 HEAD 를 `refs/heads/"
               f"{cfg.branch or 'main'}` 로 맞춘다 (빈 저장소는 `master` 로 잡힌다)")
    return out


def wants_lfs(facts) -> bool:
    """에셋 실물이 필요한가 — **빌드하는 기계만** (`ue5` 능력은 probe 실측이다).

    [주의] 선언으로 정하지 않는다. `.43` 은 git-lfs 가 아예 없고 UE5 도 없다 — 포인터가 맞다.
    """
    return bool(getattr(facts, "ue5", ""))


def _q(facts, path: str) -> str:
    return path if facts.windows else shlex.quote(path)


def commands(facts, cfg) -> list:
    """실행할 원격 명령들 `(라벨, 명령)`. **여기가 이 모듈의 계약이다** — 실행기는 이 목록을
    돌 뿐이라, 무엇이 남의 기계에서 도는지 한곳에서 읽힌다."""
    if not cfg.clone_url:
        raise ValueError(f"clone_url 이 비어 있다 — {cfg.name} 의 config.yaml 을 고칠 것 "
                         f"(bare 경로는 그 기계에 없다)")
    branch = cfg.branch or "main"
    env = "" if wants_lfs(facts) else ("set GIT_LFS_SKIP_SMUDGE=1 && " if facts.windows
                                       else "GIT_LFS_SKIP_SMUDGE=1 ")
    parent, name = _split(facts.path, facts.windows)
    out = []
    if facts.windows:
        out.append(("mkdir", f'if not exist "{parent}" mkdir "{parent}"'))
        out.append(("clone", f'cd /d "{parent}" && {env}git clone -b {branch} '
                             f'{cfg.clone_url} "{name}"'))
        # [중요] 소유권 교정 — 없으면 사람 세션에서 git 이 전부 거부한다(실측 rc=128)
        # [중요] 소유자를 **원격에서 평가**한다 — `%USERDOMAIN%\%USERNAME%` 이라 마스터가
        #    그 기계의 컴퓨터 이름을 알 필요가 없다(`DESKTOP-FU2GNGL` 같은 값을 표로 들면 낡는다).
        out.append(("owner",
                    f'icacls "{facts.path}" /setowner "%USERDOMAIN%\%USERNAME%" /T /C'))
    else:
        out.append(("mkdir", f"mkdir -p {_q(facts, parent)}"))
        out.append(("clone", f"cd {_q(facts, parent)} && {env}git clone -b {branch} "
                             f"{cfg.clone_url} {_q(facts, name)}"))
    # [주의] 빈 저장소면 `-b <branch>` 가 경고만 내고 로컬 기본 브랜치로 떨어진다 → 맞춘다.
    #    커밋이 있으면 이미 그 브랜치이므로 이 명령은 무해하다(같은 값을 다시 쓴다).
    out.append(("branch", (f'cd /d "{facts.path}" && ' if facts.windows
                           else f"cd {_q(facts, facts.path)} && ")
                          + f"git symbolic-ref HEAD refs/heads/{branch}"))
    return out


def _split(path: str, windows: bool) -> tuple:
    """`E:\\trunk\\NS` → (`E:\\trunk`, `NS`). [주의] 윈도우 경로를 posixpath 로 자르면 통째로
    남는다 — 구분자를 골라야 한다."""
    sep = "\\" if windows else "/"
    p = path.rstrip(sep)
    i = p.rfind(sep)
    return (p[:i] or sep, p[i + 1:]) if i > 0 else (".", p)
