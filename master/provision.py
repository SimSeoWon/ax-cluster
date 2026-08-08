"""Ollama 노드 점검·설치 — **상주시키지 않는다** (사용자 지시 2026-08-08).

> **"상주시키지 말고 설치나 체크 등에 쓰라고"**

마스터가 각 기계의 Ollama 를 HTTP 로 점검하고 필요한 모델을 원격 설치한다.
**모델을 올리지(load) 않는다** — 그건 브로커가 추론 요청을 보낼 때 알아서 일어난다.

🔴 **왜 `.33`(메인 작업 PC)을 추론 엔드포인트로 만들지 않는가** (실측 2026-08-08):

    .33  RTX 3080 10240MiB · 사용 2401 · **여유 7651MiB**   ← 윈도우 바탕화면만 떠 있는 상태
         보유 모델 gemma4:e4b = 8.9GiB  →  **자기 모델조차 안 들어간다**
         qwen2.5-coder:14b = 9.0GB      →  더 안 들어간다

UE5 에디터를 열면 여유는 더 줄어든다. 상주시키면 Ollama 가 CPU 로 흘러넘쳐 극도로 느려지고
사용자 작업과 VRAM 을 두고 싸운다. 게다가 §4.4 의 모델 전환 비용이 **왕복 100초**라
자리를 비웠다 돌아왔다 할 때마다 스래싱이 난다.

**그래서 역할을 나눈다:**

| 역할 | 기계 | 상주 |
|---|---|---|
| 추론 엔드포인트 | `.43`(BC-250) · `.2`(RTX 3060) | ✅ 핀 고정 |
| 작업장 겸 점검 대상 | `.33`(RTX 3080, 메인 작업 PC) | ❌ **점검·설치만** |

🔴 **"됐다" 를 믿지 않는다.** `~/CLAUDE.md` 하드룰이기도 하다 — pull 이 성공했다고 보고해도
`/api/tags` 에 실제로 나타나는지 **다시 확인**한다. 상태가 아니라 산출물을 검증한다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

TIMEOUT = 15
# pull 은 수 GB 를 받는다 — 짧은 타임아웃으로 끊으면 받다 만 상태가 된다.
PULL_TIMEOUT = 3600

# §4.4 가 확정한 모델 배정. 여기가 **의도**이고, `check()` 가 실제와 대조한다.
CODER = "qwen2.5-coder:14b"          # UE5 C++ 생성
DRIVER = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"   # 컨텍스트 쿠킹


@dataclass
class Node:
    name: str
    host: str                        # "192.168.0.2:11434"
    want: list[str] = field(default_factory=list)   # 있어야 하는 모델
    resident: bool = True            # False = 점검·설치만, 상주시키지 않는다
    note: str = ""


# 🔴 `.33` 은 `resident=False` 다. 이 플래그가 이 모듈의 존재 이유다.
NODES: list[Node] = [
    Node("bc250", "192.168.0.43:11434", want=[DRIVER, CODER],
         note="추론 엔드포인트 #1 — 35B 핀"),
    Node("rtx3060", "192.168.0.2:11434", want=[CODER],
         note="추론 엔드포인트 #2 겸 작업장 — 14b 핀"),
    # 🔴 `want` 는 있는데 `resident=False` 다 — 모순이 아니라 **정확히 의도한 상태**다.
    #    "디스크에는 둔다(설치) · VRAM 에는 안 올린다(상주 금지)" 를 그대로 표현한 것이고,
    #    사용자 지시 "상주시키지 말고 설치나 체크 등에 쓰라고" 가 이 두 축으로 갈린다.
    #    보유 여부는 `/api/tags`, 상주 여부는 `/api/ps` 가 답한다 — 서로 다른 질문이다.
    Node("rtx3080", "192.168.0.33:11434", want=[CODER], resident=False,
         note="🔴 메인 작업 PC. 여유 VRAM 7.6GiB < 14b 9.0GB — 받아는 두되 상주 금지"),
]


class ProvisionError(Exception):
    pass


def _get(url: str, timeout: int = TIMEOUT) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(url: str, payload: dict, timeout: int = TIMEOUT) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


@dataclass
class NodeStatus:
    name: str
    host: str
    reachable: bool = False
    error: str = ""
    models: list[str] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)      # 지금 VRAM 에 올라와 있는 것
    missing: list[str] = field(default_factory=list)     # want 중 없는 것
    resident_allowed: bool = True

    @property
    def ok(self) -> bool:
        return self.reachable and not self.missing

    @property
    def violating(self) -> bool:
        """상주 금지인데 모델이 올라와 있다 — 사용자 작업과 VRAM 을 다투는 중이다."""
        return not self.resident_allowed and bool(self.loaded)

    def line(self) -> str:
        if not self.reachable:
            return f"  ❌ {self.name:<9} {self.host:<22} 닿지 않음 — {self.error}"
        bits = [f"모델 {len(self.models)}종"]
        if self.loaded:
            bits.append(f"상주 {','.join(self.loaded)}")
        else:
            bits.append("상주 없음")
        if self.missing:
            bits.append(f"🔴 없음: {','.join(self.missing)}")
        if self.violating:
            bits.append("🔴 상주 금지인데 올라와 있다")
        mark = "✅" if self.ok and not self.violating else "⚠️ "
        return f"  {mark} {self.name:<9} {self.host:<22} " + " · ".join(bits)


def check_node(node: Node, *, getter=None) -> NodeStatus:
    """한 노드를 점검한다. **아무것도 올리지 않는다** — 읽기만 한다.

    `getter` 를 주입할 수 있는 이유는 테스트다 (`workshop_check.runner` 와 같은 방식).
    """
    get = getter or _get
    st = NodeStatus(name=node.name, host=node.host, resident_allowed=node.resident)
    base = f"http://{node.host}"
    try:
        tags = get(f"{base}/api/tags")
    except urllib.error.URLError as e:
        st.error = str(getattr(e, "reason", e))
        return st
    except Exception as e:                       # noqa: BLE001
        st.error = f"{type(e).__name__}: {e}"
        return st
    st.reachable = True
    st.models = sorted(m["name"] for m in tags.get("models", []))
    try:
        # /api/ps 는 **지금 VRAM 에 올라와 있는 것**이다. /api/tags(디스크)와 다르다.
        st.loaded = sorted(m["name"] for m in get(f"{base}/api/ps").get("models", []))
    except Exception:                            # noqa: BLE001
        pass   # 구버전 Ollama 는 없을 수 있다 — 점검을 통째로 실패시키지 않는다
    st.missing = [w for w in node.want if w not in st.models]
    return st


def check(nodes: list[Node] | None = None, *, getter=None) -> list[NodeStatus]:
    return [check_node(n, getter=getter) for n in (nodes or NODES)]


def pull(node: Node, model: str, *, progress=None, poster=None, getter=None) -> NodeStatus:
    """모델을 원격 설치한다. SSH 도 파일 접근도 필요 없다 — HTTP 만 오간다.

    🔴 **pull 응답을 믿지 않고 `/api/tags` 로 다시 확인한다.** 위임한 백엔드의 "됐다" 를
    그대로 받으면 안 된다는 것은 이 저장소의 하드룰이다(2026-08-07 agy 사건).
    """
    if progress:
        progress(f"{node.name}: {model} 받는 중… (수 GB, 오래 걸린다)")
    post = poster or (lambda u, p: _post(u, p, timeout=PULL_TIMEOUT))
    try:
        res = post(f"http://{node.host}/api/pull", {"model": model, "stream": False})
    except urllib.error.URLError as e:
        raise ProvisionError(f"{node.name}: pull 실패 — {getattr(e, 'reason', e)}") from e
    if res.get("error"):
        raise ProvisionError(f"{node.name}: pull 거부 — {res['error']}")

    st = check_node(node, getter=getter)          # ← 산출물 검증
    if model not in st.models:
        raise ProvisionError(
            f"{node.name}: pull 이 status={res.get('status')!r} 를 돌려줬는데 "
            f"`/api/tags` 에 {model} 이 없다 — 받아지지 않았다"
        )
    if progress:
        progress(f"{node.name}: {model} 확인됨")
    return st


def reconcile(nodes: list[Node] | None = None, *, dry_run: bool = True,
              progress=None, poster=None, getter=None) -> list[NodeStatus]:
    """의도(`want`)와 실제를 맞춘다. **기본은 dry-run** — 수 GB 를 말없이 받지 않는다."""
    out = []
    for node in (nodes or NODES):
        st = check_node(node, getter=getter)
        for model in st.missing:
            if dry_run:
                if progress:
                    progress(f"[dry-run] {node.name} ← {model}")
                continue
            st = pull(node, model, progress=progress, poster=poster, getter=getter)
        out.append(st)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Ollama 노드 점검·원격 설치 (상주는 안 시킨다)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check", help="전 노드 점검 (읽기만)")
    p = sub.add_parser("pull", help="모델 원격 설치")
    p.add_argument("node")
    p.add_argument("model")
    r = sub.add_parser("reconcile", help="want 와 실제를 맞춘다")
    r.add_argument("--apply", action="store_true", help="실제로 받는다 (기본은 dry-run)")
    args = ap.parse_args(argv)

    if args.cmd == "pull":
        node = next((n for n in NODES if n.name == args.node), None)
        if node is None:
            print(f"모르는 노드: {args.node} — 있는 것: {', '.join(n.name for n in NODES)}")
            return 2
        try:
            print(pull(node, args.model, progress=lambda m: print(f"  {m}")).line())
        except ProvisionError as e:
            print(f"  ❌ {e}")
            return 1
        return 0

    if args.cmd == "reconcile":
        sts = reconcile(dry_run=not args.apply, progress=lambda m: print(f"  {m}"))
    else:
        sts = check()

    print("\nOllama 노드 상태")
    for st in sts:
        print(st.line())
    for n in NODES:
        if not n.resident:
            print(f"\n  ℹ️  {n.name}: {n.note}")
    bad = [s for s in sts if not s.ok or s.violating]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
