"""Ollama 노드 점검·설치 — 이 모듈은 모델을 상주시키지 않는다.

마스터가 각 기계의 Ollama 를 HTTP 로 점검하고 필요한 모델을 원격 설치한다.
**모델을 올리지(load) 않는다** — 상주 관리는 브로커가 담당한다.

`.33`(메인 작업 PC)의 14b 상주 금지는 유지하되, 2026-10-03 승인된 합성 모델
`gemma4:e4b` 상주는 허용한다 (#753). 보유 여부(`/api/tags`)와 상주 정책(`/api/ps`)은
별도로 점검한다. 이 모듈은 위반을 보고할 뿐 모델을 올리거나 내리지 않는다.

[중요] **"됐다" 를 믿지 않는다.** `~/CLAUDE.md` 하드룰이기도 하다 — pull 이 성공했다고 보고해도
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
SYNTH = "gemma4:e4b"                # .33 승인된 합성 모델


@dataclass
class Node:
    name: str
    host: str                        # "192.168.0.2:11434"
    want: list[str] = field(default_factory=list)   # 있어야 하는 모델
    resident: bool = True            # 모델별 목록이 없을 때 전체 상주 허용/금지
    note: str = ""
    resident_models: frozenset[str] | None = None  # 명시하면 이 모델들만 상주 허용

    def __post_init__(self) -> None:
        if self.resident_models is not None:
            self.resident_models = frozenset(self.resident_models)


NODES: list[Node] = [
    # 35B 는 뺐다 — 상주 해제(2026-08-17, #105) 뒤에도 남아 매번 「없음」으로 보고됐다
    Node("bc250", "192.168.0.43:11434", want=[CODER],
         note="추론 엔드포인트 #1 — e4b 핀"),
    Node("rtx3060", "192.168.0.2:11434", want=[CODER],
         note="추론 엔드포인트 #2 겸 작업장 — e4b 핀 · 14b 보유"),
    Node("rtx3080", "192.168.0.33:11434", want=[CODER, SYNTH], resident=False,
         note="[중요] 메인 작업 PC. e4b 상주 허용 · 14b는 보유만, 상주 금지",
         resident_models=frozenset({SYNTH})),
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
    resident_models: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.resident_models is not None:
            self.resident_models = frozenset(self.resident_models)

    @property
    def ok(self) -> bool:
        return self.reachable and not self.missing

    @property
    def violating_models(self) -> list[str]:
        """상주 정책에서 허용하지 않은 적재 모델만 반환한다."""
        if self.resident_models is not None:
            return [m for m in self.loaded if m not in self.resident_models]
        return [] if self.resident_allowed else list(self.loaded)

    @property
    def violating(self) -> bool:
        return bool(self.violating_models)

    def line(self) -> str:
        if not self.reachable:
            return f"  [실패] {self.name:<9} {self.host:<22} 닿지 않음 — {self.error}"
        bits = [f"모델 {len(self.models)}종"]
        if self.loaded:
            bits.append(f"상주 {','.join(self.loaded)}")
        else:
            bits.append("상주 없음")
        if self.missing:
            bits.append(f"[중요] 없음: {','.join(self.missing)}")
        if self.violating:
            bits.append(f"[중요] 상주 금지인데 올라와 있다: {','.join(self.violating_models)}")
        mark = "[완료]" if self.ok and not self.violating else "[주의] "
        return f"  {mark} {self.name:<9} {self.host:<22} " + " · ".join(bits)


def check_node(node: Node, *, getter=None) -> NodeStatus:
    """한 노드를 점검한다. **아무것도 올리지 않는다** — 읽기만 한다.

    `getter` 를 주입할 수 있는 이유는 테스트다 (`workshop_check.runner` 와 같은 방식).
    """
    get = getter or _get
    st = NodeStatus(name=node.name, host=node.host, resident_allowed=node.resident,
                    resident_models=node.resident_models)
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

    [중요] **pull 응답을 믿지 않고 `/api/tags` 로 다시 확인한다.** 위임한 백엔드의 "됐다" 를
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
            print(f"  [실패] {e}")
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
            print(f"\n  ℹ  {n.name}: {n.note}")
    bad = [s for s in sts if not s.ok or s.violating]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
