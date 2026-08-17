"""마스터 서비스 공용 인증 — 공유 베어러 토큰, fail-closed (PLAN §9.5.6).

**왜 지금 하나.** `task_queue`(8101)·브로커(8102)·`ax-projects`(8103) 세 서비스가
전부 인증 계층 없이 떠 있고, 방어선이 `ufw` 하나뿐이다. 방화벽은 *LAN 밖*을 막을 뿐이라
LAN 안의 무엇이든 — 감염된 기기, 브라우저가 연 악성 페이지, 잘못 설정된 컨테이너 —
그대로 큐를 조작하고 추론을 태우고 프로젝트를 전환할 수 있다.

**형태.** 공유 베어러 토큰 하나. mTLS 도 OAuth 도 아니다 — 클라이언트가 소수(작업장 2대 +
마스터 자신)이고 전부 사람이 관리하는 LAN 장비다. 과한 장치는 운영이 안 되고, 운영 안 되는
보안은 없는 것과 같다. 세분화가 필요해지면 서비스별 토큰으로 나눈다(구조는 그대로다).

[중요] **fail-closed 3중:**

1. **토큰이 없으면 서비스가 뜨지 않는다.** "인증 없이 계속" 은 선택지가 아니다 —
   그게 바로 지금 고치려는 상태다.
2. **약한 토큰도 거부한다.** 32자 미만이면 기동 실패. 파일 권한이 열려 있어도 거부한다.
3. **헤더가 없거나 틀리면 401.** 비교는 `hmac.compare_digest` — 타이밍으로 새지 않는다.

**열어 두는 것은 `/livez` 하나뿐이다.** `{"ok": true}` 만 돌려주고 아무것도 노출하지
않는다. 브로커의 `/health` 는 노드 주소와 적재 모델을 드러내므로 **인증 뒤에 둔다** —
살아 있는지 확인하는 것과 무엇이 돌고 있는지 보는 것은 다른 권한이다.
"""
from __future__ import annotations

import hmac
import os
import secrets
import stat
from pathlib import Path

# 토큰 파일. [중요] `~/ax-state` 에 두지 않는다 — 그쪽은 감사 커밋이 도는 git 저장소다.
DEFAULT_TOKEN_FILE = Path.home() / ".config" / "ax-cluster" / "token"
MIN_TOKEN_LEN = 32

HEADER = "authorization"
SCHEME = "Bearer"
BASIC = "Basic"

# [중요] **뷰 토큰은 API 토큰과 다르다** (2026-08-13).
#
# 브라우저에서 화면을 보려면 브라우저가 자격증명을 들고 있어야 하는데, 그것이 **API 토큰이면
# 그 브라우저는 MCP 도구를 호출할 수 있는 자격**을 들고 있는 셈이다. LAN 안의 악성 페이지가
# 그 자격을 노리는 경로(CSRF)가 열린다 — DNS 리바인딩 보호와 Origin 검사가 완화하지만,
# **애초에 다른 비밀이면 그 걱정 자체가 없다.**
#
# 그래서 읽기 전용 화면에는 **별도 토큰**을 쓴다. 이 토큰으로는 큐도 브로커도 MCP 도구도
# 호출할 수 없다 — 정적 파일 두 장만 읽힌다. [중요] 없으면 뷰 경로는 **열리지 않는다**(fail-closed).
VIEW_TOKEN_FILE = Path.home() / ".config" / "ax-cluster" / "view-token"

# 인증 없이 열어 두는 경로. **정보를 노출하지 않는 것만** 여기 들어갈 수 있다.
OPEN_PATHS = frozenset({"/livez"})


class AuthError(RuntimeError):
    """토큰을 읽을 수 없거나 쓸 수 없는 상태. 서비스는 기동을 포기해야 한다."""


def token_file() -> Path:
    raw = os.environ.get("AX_AUTH_TOKEN_FILE", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_TOKEN_FILE


def generate_token() -> str:
    """새 토큰. `secrets` 를 쓴다 — `random` 은 예측 가능하다."""
    return secrets.token_urlsafe(48)


def write_token(path: Path | None = None, token: str | None = None) -> tuple[Path, str]:
    """토큰 파일을 0600 으로 만든다. 이미 있으면 덮지 않는다 — 회전은 명시적이어야 한다."""
    p = path or token_file()
    if p.exists():
        raise AuthError(f"이미 있다: {p}. 회전하려면 지우고 다시 만들 것(모든 클라이언트 갱신 필요).")
    p.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(p.parent, 0o700)
    t = token or generate_token()
    # 만들 때부터 0600 이어야 한다 — 쓰고 나서 chmod 하면 그 사이가 열린다.
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(t + "\n")
    return p, t


def load_token(path: Path | None = None) -> str:
    """토큰을 읽는다. **어떤 실패도 '인증 없음' 으로 강등되지 않는다 — 예외를 던진다.**"""
    p = path or token_file()
    if not p.is_file():
        raise AuthError(
            f"토큰 파일이 없다: {p}\n"
            "인증 없이 기동하지 않는다(PLAN §9.5.6). 먼저 만들 것:\n"
            "  .venv/bin/python -m master.auth init"
        )
    mode = p.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise AuthError(
            f"토큰 파일 권한이 열려 있다: {p} ({stat.filemode(mode)}). "
            f"`chmod 600 {p}` 로 좁힐 것."
        )
    tok = p.read_text(encoding="utf-8").strip()
    if not tok:
        raise AuthError(f"토큰 파일이 비어 있다: {p}")
    if len(tok) < MIN_TOKEN_LEN:
        raise AuthError(
            f"토큰이 너무 짧다({len(tok)}자 < {MIN_TOKEN_LEN}). "
            "짧은 토큰은 없는 것보다 나쁘다 — 있다는 착각을 준다."
        )
    return tok


def verify(provided: str | None, expected: str) -> bool:
    """상수 시간 비교. 앞자리부터 맞춰 가는 공격을 막는다.

    [중요] **바이트로 비교한다.** `compare_digest` 는 비ASCII `str` 에 `TypeError` 를 던진다 —
    잘못된 클라이언트가 비ASCII 헤더를 보내면 깨끗한 401 대신 500 이 됐다(테스트가 잡은
    실결함, 2026-08-16). 우리 토큰은 항상 ASCII 지만 **입력은 우리가 정하지 않는다.**
    """
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def parse_bearer(header_value: str | None) -> str | None:
    """`Bearer <token>` 에서 토큰만. 형식이 아니면 None."""
    if not header_value:
        return None
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != SCHEME.lower():
        return None
    return parts[1].strip() or None


def view_token_file() -> Path:
    raw = os.environ.get("AX_VIEW_TOKEN_FILE", "").strip()
    return Path(raw).expanduser() if raw else VIEW_TOKEN_FILE


def load_view_token(path: Path | None = None) -> str | None:
    """뷰 토큰. **없으면 `None`** — 뷰 경로를 열지 않는다는 뜻이다(예외가 아니다).

    [주의] API 토큰과 달리 *없어도 서비스는 뜬다* — 화면이 안 열릴 뿐이다. 화면 하나 때문에
    큐와 MCP 가 못 뜨는 것은 과하다.
    """
    p = path or view_token_file()
    if not p.is_file():
        return None
    # [중요] 권한·길이 검사는 API 토큰과 **같은 기준**이다. 읽기 전용이라고 느슨하게 두지 않는다.
    return load_token(p)


# ─────────────────────────────────────────────────────────────
# 역할 스코프 토큰 (소 3.8.2 · `#200`) — 최소권한 클라이언트 자격
# ─────────────────────────────────────────────────────────────
#
# 왜 세 번째 토큰 종류인가. 요청자(`.33`)가 검수를 하려면 큐를 읽고 결정을 반영해야 하는데,
# 선택지가 둘뿐이었다 — 전권 API 토큰을 사람 PC 에 두거나(탈취 시 큐·브로커·온톨로지 전부),
# 아무것도 못 하거나. 뷰 토큰이 화면 하나를 위해 분리된 것과 같은 이유로, 역할 토큰은
# **그 역할이 하는 일의 경로만** 연다.
#
# [중요] 스코프 밖은 401 이 아니라 **403** 이다 — 신원은 맞고 권한이 없다. 이 구분이 없으면
# 클라이언트 배선이 조용히 깨졌을 때 "토큰이 틀렸나" 로 오진한다(우리가 겪는 오진의 부류).
# 403 본문은 사유를 상세히 적지 않는다 — 무엇이 열려 있는지는 서버 쪽 정의가 SSOT 다.

# 요청자 역할이 여는 경로 — 검수 흐름 + 되먹임 생산, 그것뿐이다.
#   읽기       works·tasks 조회 (검수 대상 파악)
#   PATCH      검수 결정 반영 (merge_status · review_decision — 사람의 자리)
#   redmine    마스터 경유 코멘트 (키는 마스터에만 있다)
#   signals    code-writer 신호 적재 (#206 — 신호 파일은 마스터의 트윈 디렉토리에 있다)
REQUESTER_SCOPE: tuple = (
    ("GET", "/api/v1/works"),
    ("GET", "/api/v1/tasks"),
    ("PATCH", "/api/v1/works/"),
    ("POST", "/api/v1/redmine/note"),
    ("POST", "/api/v1/signals"),
    ("POST", "/api/v1/history"),
)

# worker (작업장 claimer, #204 — κ.0 CI 러너 패턴): 집고(claim) · 살아 있다 알리고(heartbeat) ·
#   결과를 낸다(submit). [중요] 등록·검수(verify)·정리는 **못 한다** — 판단은 마스터(①),
#   워커는 실행+보고(②)라는 κ.0 경계를 토큰 스코프가 강제한다. 규칙의 3번째 원소는
#   **접미사**다 (경로 중간의 task_id 가 가변이라 접두어만으로는 verify 를 못 가른다).
WORKER_SCOPE: tuple = (
    ("POST", "/api/v1/tasks/claim"),
    ("POST", "/api/v1/tasks/", "/heartbeat"),
    ("POST", "/api/v1/tasks/", "/submit"),
    ("POST", "/api/v1/tasks/", "/submit-fail"),
    ("GET", "/api/v1/tasks"),
)


def role_token_file(role: str) -> Path:
    raw = os.environ.get(f"AX_{role.upper()}_TOKEN_FILE", "").strip()
    return Path(raw).expanduser() if raw else (DEFAULT_TOKEN_FILE.parent / f"{role}-token")


def load_role_token(role: str) -> str | None:
    """역할 토큰. **없으면 `None`** — 그 역할의 경로가 열리지 않을 뿐이다(뷰 토큰과 같은 결).

    [중요] 권한·길이 검사는 API 토큰과 같은 기준이다(`load_token` 재사용). 스코프가 좁다고
    느슨하게 두면, 좁힌 이유가 없어진다.
    """
    p = role_token_file(role)
    if not p.is_file():
        return None
    return load_token(p)


def parse_basic(header_value: str | None) -> str | None:
    """`Basic base64(user:token)` → 토큰. [중요] **브라우저를 위해서만** 받는다.

    브라우저는 `Authorization: Bearer` 를 스스로 붙일 수 없다(자바스크립트 없이는). Basic 은
    URL·프롬프트로 붙는다 — 그래서 **사람이 보는 경로에만** 열어 준다. 사용자명은 무시한다:
    비밀은 토큰 하나이고, 사용자 계정 개념이 없다.
    """
    if not header_value:
        return None
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != BASIC.lower():
        return None
    import base64
    import binascii
    try:
        raw = base64.b64decode(parts[1].strip(), validate=True).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return None
    _user, _, tok = raw.partition(":")
    return tok.strip() or None


def auth_headers(token: str | None = None) -> dict[str, str]:
    """내부 클라이언트가 붙일 헤더. 토큰을 못 읽으면 예외 — 조용히 빠뜨리지 않는다."""
    return {"Authorization": f"{SCHEME} {token or load_token()}"}


class BearerAuthMiddleware:
    """순수 ASGI 미들웨어 — FastAPI 와 MCP(Starlette) 양쪽에 같은 것을 쓴다.

    [중요] `http` 가 아닌 스코프(`lifespan`)는 통과시킨다. 통과시키지 않으면 앱이 기동조차 못 한다.
    [중요] `websocket` 은 **거부**한다 — 지금 쓰는 서비스가 없고, 인증 안 된 업그레이드 경로를
       열어 둘 이유가 없다.
    """

    def __init__(self, app, token: str, open_paths=OPEN_PATHS, *,
                 view_prefix: str = "", view_token: str | None = None,
                 view_public: bool = False, public_prefixes: tuple = (),
                 scoped: tuple = ()):
        self.app = app
        self._token = token
        self.open_paths = frozenset(open_paths)
        self._view_prefix = view_prefix or ""
        self._view_token = view_token
        # [중요] **뷰는 기본적으로 인증 없이 열린다** (사용자 결정 2026-08-13).
        #
        #   > *"그냥 있는거 보여주는 뷰어를 원하는거라니까."*
        #
        # 세 서비스에 토큰을 요구하는 규칙은 **조작 가능한 API** 를 위해 쓰인 것이다 — 큐를
        # 조작하고 추론을 태우고 프로젝트를 전환하는 경로들. [중요] `/view/` 는 **아무것도 못 한다**:
        # GET/HEAD 만, 화이트리스트된 파일만, 요청이 수집을 유발하지도 않는다. 규칙의 글자를
        # 지키려고 **쓰이지 않는 화면**을 만드는 것이 더 나쁘다 — 매번 64자를 치게 하면 안 본다.
        #
        # [주의] **남는 방어는 ufw LAN 한정 한 층이다.** 그것이 이 경로의 의도된 상태다.
        #    [중요] `AX_VIEW_REQUIRE_TOKEN=1` 로 되돌릴 수 있다(그때는 뷰 토큰이 필요하다).
        self._view_public = view_public
        # [중요] 읽기 전용 화면 접두어들 — 원전 웹 UI 복각(2026-08-13). 조작 경로가 아니다.
        self._public = tuple(public_prefixes or ())
        # 역할 스코프 토큰 (소 3.8.2) — ((토큰, ((METHOD, 경로접두어), …)), …).
        # [중요] 토큰이 None 인 항목은 버린다 — 파일이 없으면 그 역할은 닫힌 것이다(fail-closed).
        self._scoped = tuple((t, tuple(rules)) for t, rules in (scoped or ()) if t)

    async def __call__(self, scope, receive, send):
        typ = scope.get("type")
        if typ == "lifespan":
            return await self.app(scope, receive, send)
        if typ == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if typ != "http":
            return await self.app(scope, receive, send)

        if scope.get("path", "") in self.open_paths:
            return await self.app(scope, receive, send)

        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        path = scope.get("path", "")
        if self._public and any(path.startswith(p) for p in self._public):
            return await self.app(scope, receive, send)
        is_view = bool(self._view_prefix) and path.startswith(self._view_prefix)

        if is_view:
            # [중요] 기본은 **공개**다 (위 `view_public` § 참조)
            if self._view_public:
                return await self.app(scope, receive, send)
            # 잠갔을 때는 **뷰 토큰만** 받는다. API 토큰으로 여기에 들어올 수 없고, 그 반대도
            # 안 된다 — 두 자격이 섞이면 분리한 이유가 없어진다.
            if self._view_token and (
                    verify(parse_basic(headers.get(HEADER)), self._view_token)
                    or verify(parse_bearer(headers.get(HEADER)), self._view_token)):
                return await self.app(scope, receive, send)
            # 브라우저가 로그인 창을 띄우도록 **Basic** 으로 도전한다
            return await self._deny(send, challenge=b'Basic realm="ax-cluster view"',
                                   why=(b"view token not configured" if not self._view_token
                                        else b"unauthorized"))

        provided = parse_bearer(headers.get(HEADER))
        if verify(provided, self._token):
            return await self.app(scope, receive, send)
        # 역할 스코프 토큰 — 신원이 맞으면 경로·메서드를 스코프에 대조한다.
        # [중요] 규칙은 (METHOD, 접두어[, 접미사]) — 접미사(#204, WORKER_SCOPE)는 task_id 가
        #    경로 중간에 끼는 자리를 가른다. 2원소 규칙은 기존 그대로(접미사 무조건 통과).
        method = (scope.get("method") or "").upper()
        for stok, rules in self._scoped:
            if not verify(provided, stok):
                continue
            for rule in rules:
                m, pfx = rule[0], rule[1]
                sfx = rule[2] if len(rule) > 2 else ""
                if method == m and path.startswith(pfx) and (not sfx or path.endswith(sfx)):
                    return await self.app(scope, receive, send)
            # [중요] 401 이 아니라 403 — 신원은 맞고 권한이 없다. 이 구분이 없으면
            # 배선이 깨졌을 때 "토큰이 틀렸나" 로 오진한다.
            return await self._deny(send, status=403, why=b"forbidden (scope)",
                                    challenge=b'Bearer realm="ax-cluster"')
        # 왜 실패했는지(헤더 없음 vs 토큰 틀림)는 알려주지 않는다.
        return await self._deny(send, challenge=b'Bearer realm="ax-cluster"')

    @staticmethod
    async def _deny(send, *, challenge: bytes, why: bytes = b"unauthorized",
                    status: int = 401) -> None:
        body = b'{"error":"' + why + b'"}'
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", challenge),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def _main(argv: list[str]) -> int:
    """`python -m master.auth init|init-view|init-role <역할>|show|check`"""
    cmd = argv[0] if argv else "check"
    p = token_file()
    if cmd == "init":
        try:
            path, tok = write_token(p)
        except AuthError as e:
            print(f"실패: {e}")
            return 1
        print(f"토큰 생성: {path} (0600)")
        print(f"토큰: {tok}")
        print("\n클라이언트에 붙일 헤더:")
        print(f'  Authorization: Bearer {tok}')
        return 0
    if cmd == "init-view":
        vp = view_token_file()
        try:
            path, tok = write_token(vp)
        except AuthError as e:
            print(f"실패: {e}")
            return 1
        print(f"뷰 토큰 생성: {path} (0600)")
        print(f"토큰: {tok}")
        print("\n브라우저에서 열 때 — 사용자명은 아무거나, 비밀번호에 이 토큰:")
        print(f"  http://192.168.0.57:8103/view/")
        print("[중요] 이 토큰으로는 큐·브로커·MCP 도구를 호출할 수 없다 (화면 전용).")
        return 0
    if cmd == "init-role":
        role = (argv[1] if len(argv) > 1 else "").strip()
        if not role or not role.isalpha():
            print("사용법: python -m master.auth init-role <역할>   (예: requester)")
            return 1
        rp = role_token_file(role)
        try:
            path, tok = write_token(rp)
        except AuthError as e:
            print(f"실패: {e}")
            return 1
        print(f"{role} 토큰 생성: {path} (0600)")
        print(f"토큰: {tok}")
        print(f"[중요] 이 토큰은 {role} 스코프의 경로만 연다 — 스코프 밖은 403.")
        return 0
    if cmd == "show":
        try:
            print(load_token(p))
        except AuthError as e:
            print(f"실패: {e}")
            return 1
        return 0
    # check
    try:
        tok = load_token(p)
    except AuthError as e:
        print(f"[실패] {e}")
        return 1
    print(f"[완료] 토큰 정상: {p} ({len(tok)}자)")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_main(sys.argv[1:]))
