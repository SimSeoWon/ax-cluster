"""버전 핸드셰이크 (소 3.1.8 · `#191`, κ.9 계약 표면) — 원전 `get_server_version` 이식분.

검증하는 것:

    ① 정체에 커밋·계약·트윈이 실린다 (코드 버전만으로는 「같은 코드가 다른 트윈」을 못 본다)
    ② 🔴 판정이 **3분기**다 — `same` / `drifted` / **`unknown`**
       ⚠️ `unknown` 을 한쪽으로 접으면 없는 드리프트를 보고하거나 **있는 것을 놓친다**
    ③ 🔴 모르는 값은 **빈 문자열 + 사유**다 — `"unknown"` 문자열을 넣지 않는다
       (넣으면 두 「모름」이 서로 같다고 판정된다)
    ④ 계약 버전이 다르면 사유에 그것이 나온다 (도구 표면 변경 신호)
    ⑤ 작업트리가 더러우면 그 사실을 싣는다 (커밋이 정체를 다 말하지 못한다)
    ⑥ 🔴 배달된 config 에 **누가 언제 배달했는지**가 새겨진다 (배달 드리프트를 잡는 자리)

`.venv/bin/python master/test_version.py`
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import version as V                                  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


@dataclass
class Paths:
    """`ProjectPaths` 중 트윈 정체가 읽는 것만."""

    root: Path
    name: str = "T"

    @property
    def config(self) -> Path:
        return self.root / "config.yaml"


# ── ①⑤ 정체 ──────────────────────────────────────────────────────────────────

def test_identity_carries_commit_and_contract():
    idy = V.identity()
    check("① 계약 버전이 실린다", isinstance(idy.get("contract"), int), str(idy.get("contract")))
    check("① 커밋이 실린다 (이 저장소는 git 이다)", len(idy.get("commit", "")) == 40,
          idy.get("commit", "")[:12] + f" · {idy.get('error','')}")
    check("① 짧은 커밋도 함께", bool(idy.get("commit_short")), str(idy.get("commit_short")))
    check("⑤ dirty 를 판정한다 (True/False, 모르면 None)",
          idy.get("dirty") in (True, False, None), str(idy.get("dirty")))


def test_twin_identity_is_separate():
    """🔴 코드 버전만 말하면 「같은 코드가 다른 트윈을 본다」를 못 본다 (§8.4 세 값 동일)."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Paths(root=Path(tmp))
        p.config.write_text(
            "name: T\nindex:\n  last_indexed_commit: abc123\n"
            "  last_indexed_at: '2026-08-15T00:00:00'\n  source: zip\n", encoding="utf-8")
        idy = V.identity(paths=p)
        t = idy.get("twin") or {}
        check("① 트윈 커밋을 함께 낸다", t.get("indexed_commit") == "abc123", str(t))
        check("① 트윈 출처도", t.get("source") == "zip", str(t))

        # config 를 못 읽어도 정체 자체는 나온다
        p2 = Paths(root=Path(tmp) / "nope")
        t2 = (V.identity(paths=p2).get("twin") or {})
        check("① 트윈을 못 읽으면 사유를 낸다", bool(t2.get("error")), str(t2))


# ── ②③④ 판정 ────────────────────────────────────────────────────────────────

def test_verdict_is_three_way():
    ours = {"commit": "a" * 40}
    check("② 같으면 same",
          V.compare({"commit": "a" * 40}, ours)["verdict"] == "same")
    check("② 다르면 drifted",
          V.compare({"commit": "b" * 40}, ours)["verdict"] == "drifted")

    # 🔴 한쪽이 모르면 같다고도 다르다고도 하지 않는다
    for theirs in ({"commit": ""}, {}, {"commit": "   "}):
        r = V.compare(theirs, ours)
        check(f"② 🔴 모르면 unknown ({theirs})", r["verdict"] == "unknown", str(r))
    r = V.compare({"commit": "b" * 40}, {"commit": ""})
    check("② 🔴 우리가 몰라도 unknown", r["verdict"] == "unknown", str(r))


def test_unknown_is_not_a_version_string():
    """③ `"unknown"` 을 값으로 쓰면 두 「모름」이 같다고 판정된다."""
    r = V.compare({"commit": "unknown"}, {"commit": "unknown"})
    check("③ 🔴 'unknown' 문자열은 같음으로 판정된다 — 그래서 쓰지 않는다",
          r["verdict"] == "same", str(r))
    idy = V.identity()
    check("③ 우리 정체는 'unknown' 을 넣지 않는다",
          idy.get("commit") != "unknown", str(idy.get("commit"))[:20])


def test_contract_mismatch_is_named():
    r = V.compare({"commit": "b" * 40, "contract": 99}, {"commit": "a" * 40})
    check("④ 계약 불일치를 사유에 적는다", "계약" in r["reason"], r["reason"])
    check("④ 양쪽 계약을 싣는다",
          r.get("contract_ours") == V.CONTRACT and r.get("contract_theirs") == 99, str(r))
    r2 = V.compare({"commit": "b" * 40, "contract": V.CONTRACT}, {"commit": "a" * 40})
    check("④ 계약이 같으면 그렇게 말한다", "계약은 같다" in r2["reason"], r2["reason"])


# ── ⑥ 배달 정체 ──────────────────────────────────────────────────────────────

def test_delivered_config_is_stamped():
    from master.client import bundle

    f = bundle.HostFacts(host="h", user="u", path="/repo", driven="ssh", role="worker")
    cfg = bundle.config_for("T", f)
    d = cfg.get("delivered_by") or {}
    check("⑥ 🔴 배달 정체가 config 에 새겨진다", bool(d), str(cfg.keys()))
    check("⑥ 커밋이 실린다", len(d.get("commit", "")) == 40, str(d)[:80])
    check("⑥ 계약도 실린다", d.get("contract") == V.CONTRACT, str(d))
    check("⑥ 비밀은 없다", "token" not in str(cfg).lower(), "토큰이 실렸다")


def main() -> int:
    for fn in (test_identity_carries_commit_and_contract, test_twin_identity_is_separate,
               test_verdict_is_three_way, test_unknown_is_not_a_version_string,
               test_contract_mismatch_is_named, test_delivered_config_is_stamped):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_version: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
