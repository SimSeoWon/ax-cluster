"""마스터 정체 — 버전 핸드셰이크 (소 3.1.8 · `#191`, κ.9 계약 표면).

원전 `get_server_version` 이식. 🔴 **원전이 이것을 만든 계기가 우리에게 그대로 있다:**

> *"`bump_version.ps1` 이 build.bat 실행마다 세 파일을 동시에 bump 한다(2026-07-12 추가,
> **그 전엔 context_search.exe 가 어느 빌드인지 확인할 방법이 전혀 없었음**)."*

실측 2026-08-15 — 우리 상태도 같다:

    버전 상수                 🔴 없다 (`grep '^VERSION' master/` → 0건)
    배달된 `.ax/config.json`  `generated_by: "master/client/bundle.py"` 뿐 —
                              **어느 마스터가 언제 배달했는지 안 적혀 있다**

## 🔴 신호원은 exe 빌드 번호가 아니라 **git 커밋**이다

우리는 exe 를 만들지 않으므로 `VERSION` 상수를 bump 할 자리가 없다. 대신 **정체를 말해 주는
것이 이미 있다** — 이 저장소의 git 커밋. 그래서 기제는 옮기고 신호원을 바꾼다.
⚠️ 이 세션에 같은 판단을 세 번 했다(σ.9.0 의 `mtime`→git · 폴백 임베더 · 여기).

## 무엇에 쓰나 — 우리 구조에서 이 핸드셰이크가 막는 것 셋

    ① 세 클론 드리프트   마스터·GitHub·`.43` 이 같은 커밋인지 (지금은 사람이 손으로 확인한다)
    ② 배달 드리프트      작업장의 번들이 **어느 마스터에서** 나왔는지 (config 에 없다)
    ③ 클라이언트 계약    `.33` 의 폴백 캐시가 **호환되는 마스터**와 말하는지 (소 3.4.3)

🔴 **그리고 트윈 커밋을 함께 낸다.** §8.4 가 *"durable 을 만드는 기준 커밋 == 매니페스트의
`twin_commit` == `index.last_indexed_commit`"* 로 세 값이 같음을 정의해 뒀다 — 코드 버전만
말하고 트윈 버전을 빼면, **같은 코드가 다른 트윈을 보고 있는 상태**를 못 본다.

## ⚠️ 「모른다」를 버전으로 접지 않는다

git 을 못 읽으면 `commit=""` 과 사유를 낸다. 🔴 `"unknown"` 같은 문자열을 넣으면 소비자가
그것을 **버전으로 비교**하고, 두 「모름」이 같다고 판정한다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_TIMEOUT = 15

# 🔴 계약 버전 — **코드 커밋과 다른 것**이다. MCP 도구 이름·응답 형태처럼 **소비자가 기대는
#    표면**이 바뀔 때만 올린다. 커밋마다 바뀌면 소비자가 매 커밋에 불호환을 의심한다.
CONTRACT = 1


def _git(*args) -> tuple:
    try:
        r = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                           capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        return "", f"{type(e).__name__}: {e}"
    if r.returncode != 0:
        return "", (r.stderr or "").strip()[:120]
    return (r.stdout or "").strip(), ""


def identity(*, paths=None) -> dict:
    """마스터의 정체. 🔴 **모르는 값은 빈 문자열 + 사유**다 (`"unknown"` 을 넣지 않는다).

    `paths` 를 주면 트윈 커밋(`index.last_indexed_commit`)도 함께 낸다 — 코드 버전만으로는
    *"같은 코드가 다른 트윈을 본다"* 를 못 본다(§8.4 의 세 값 동일 규약).
    """
    commit, err = _git("rev-parse", "HEAD")
    short, _ = _git("rev-parse", "--short", "HEAD")
    when, _ = _git("log", "-1", "--format=%cI")
    dirty_out, dirty_err = _git("status", "--porcelain")

    out = {
        "contract": CONTRACT,
        "commit": commit,
        "commit_short": short,
        "committed_at": when,
        # 🔴 작업트리가 더러우면 **커밋이 정체를 다 말하지 못한다** — 그 사실을 싣는다
        "dirty": bool(dirty_out) if not dirty_err else None,
        "repo": str(REPO_ROOT),
    }
    if err:
        out["error"] = f"git 을 읽지 못했다: {err}"
    if dirty_err:
        out["dirty_error"] = dirty_err

    if paths is not None:
        out["twin"] = twin_identity(paths)
    return out


def twin_identity(paths) -> dict:
    """트윈(색인)의 정체 — `config.yaml` 의 `index.last_indexed_commit`.

    §8.4: *"durable 을 만드는 기준 커밋 == 매니페스트의 `twin_commit` ==
    `index.last_indexed_commit`"* — 세 값이 같아야 한다. 여기서 그 한 값을 노출한다.
    """
    try:
        import yaml
        cfg = yaml.safe_load(Path(paths.config).read_text(encoding="utf-8")) or {}
    except Exception as e:                                   # noqa: BLE001
        return {"project": getattr(paths, "name", ""), "error": f"config 를 읽지 못했다: {e}"}
    idx = (cfg.get("index") or {})
    return {
        "project": getattr(paths, "name", ""),
        "indexed_commit": str(idx.get("last_indexed_commit") or ""),
        "indexed_at": str(idx.get("last_indexed_at") or ""),
        "source": str(idx.get("source") or ""),
    }


def compare(theirs: dict, ours: dict | None = None) -> dict:
    """상대가 말한 정체와 우리를 맞춘다. 🔴 **판정을 세 가지로 가른다.**

        "same"        커밋이 같다
        "drifted"     둘 다 알고 있고 다르다 — 배달·동기가 필요하다
        "unknown"     🔴 한쪽이라도 모른다 → **같다고도 다르다고도 하지 않는다**

    ⚠️ `unknown` 을 `drifted` 로 접으면 없는 드리프트를 보고하고, `same` 으로 접으면 **있는
    드리프트를 놓친다.** 오늘 세 번 물린 계측 오류가 정확히 그 부류다.
    """
    ours = ours or identity()
    a = (ours.get("commit") or "").strip()
    b = (theirs or {}).get("commit", "").strip()
    if not a or not b:
        return {"verdict": "unknown", "ours": a, "theirs": b,
                "reason": "한쪽이 커밋을 모른다 — 같다고도 다르다고도 하지 않는다"}
    if a == b:
        return {"verdict": "same", "ours": a, "theirs": b, "reason": ""}
    ct = (theirs or {}).get("contract")
    return {"verdict": "drifted", "ours": a, "theirs": b,
            "contract_ours": CONTRACT, "contract_theirs": ct,
            "reason": ("계약 버전도 다르다 — 도구 표면이 바뀌었을 수 있다"
                       if ct is not None and ct != CONTRACT
                       else "코드 커밋이 다르다 (계약은 같다)")}


def main(argv: list | None = None) -> int:
    import json
    import sys

    args = list(argv if argv is not None else sys.argv[1:])
    paths = None
    if args and args[0] == "--twin":
        from .context_search.paths import resolve
        paths = resolve("")
    print(json.dumps(identity(paths=paths), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
