"""로컬 생성 기록과 표시된 문서의 클라우드 재합성 (#840).

조각 기록은 원래 브랜치·응답 스풀과 별도로 보존한다. 이 모듈은 조각 상태나
조각·작업 브랜치를 변경하지 않는다. 문서 재합성은 기존 게이트와 쓰기 직전 지문 대조를 쓴다.
조각 재생성(`run_tasks`)은 클라우드 결과를 **별도 후보 브랜치**
`task/<work>/r<N>/<piece>-cloud` 에만 새로 만든다 — 덮어쓰지 않고, 채택은 ⑦ 에서 사람이 한다.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def artifact_fingerprint(path):
    """파일 bytes 또는 디렉터리의 상대경로→파일 bytes hash를 비교한다."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"재검증 대상은 심볼릭 링크일 수 없다: {path}")
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if not path.is_dir():
        raise FileNotFoundError(path)
    files = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"재검증 대상에 심볼릭 링크가 있다: {item}")
        if item.is_file():
            files[item.relative_to(path).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    return hashlib.sha256(_canonical(files).encode("utf-8")).hexdigest()


def source_fingerprint(paths, files):
    from .. import source_text
    if not isinstance(files, list) or not files:
        raise ValueError("재검증 소스 목록이 비어 있다")
    bodies = {}
    repo = Path(paths.repo).resolve()
    for name in files:
        if not isinstance(name, str) or not name or Path(name).is_absolute():
            raise ValueError("잘못된 재검증 소스 경로")
        target = repo / name
        if not target.resolve().is_relative_to(repo) or target.is_symlink():
            raise ValueError(f"재검증 소스 경계 이탈: {name}")
        if not paths.scope.contains(name):
            raise ValueError(f"등록 소스 경계 밖: {name}")
        source = source_text.read(target)
        if source is None:
            raise FileNotFoundError(target)
        bodies[name] = source.text
    # 생성기가 기록한 source_fingerprint와 같은 직렬화 규약.
    return hashlib.sha256(json.dumps(bodies, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@contextmanager
def _store(root):
    directory = Path(root) / "revalidation"
    if directory.is_symlink():
        raise ValueError("재검증 기록 디렉터리는 심볼릭 링크일 수 없다")
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "records.lock"
    if lock_path.is_symlink():
        raise ValueError("재검증 잠금은 심볼릭 링크일 수 없다")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = directory / "records.json"
        if path.is_symlink():
            raise ValueError("재검증 기록은 심볼릭 링크일 수 없다")
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
            raise ValueError("손상된 재검증 기록")
        yield path, data


def _save(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".records-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(_canonical(data) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _identity(kind, key):
    if kind not in ("context", "ontology", "task") or not isinstance(key, str) or not key.strip():
        raise ValueError("재검증 종류·key가 올바르지 않다")
    return _canonical([kind, key])


def mark(root, kind, key, *, fingerprint, metadata):
    identity = _identity(kind, key)
    if not isinstance(fingerprint, str) or not fingerprint or not isinstance(metadata, dict):
        raise ValueError("재검증 지문·metadata가 올바르지 않다")
    # 입력이 JSON 왕복 가능함을 쓰기 전에 검사한다.
    metadata = json.loads(_canonical(metadata))
    with _store(root) as (path, data):
        old = data.get(identity)
        if old and old.get("fingerprint") == fingerprint:
            return old
        entry = dict(kind=kind, key=key, fingerprint=fingerprint, metadata=metadata,
                     needs_revalidation=True, created_at=datetime.now(timezone.utc).isoformat())
        data[identity] = entry
        _save(path, data)
        return entry


def pending(root, *, limit=100):
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("limit는 음수가 아닌 정수여야 한다")
    path = Path(root) / "revalidation" / "records.json"
    if not path.exists():
        return []
    with _store(root) as (_, data):
        return [v for _, v in sorted(data.items()) if v.get("needs_revalidation") is True][:limit]


def clear(root, kind, key, *, fingerprint):
    """처리한 지문과 현재 기록이 같을 때만 해제한다. 새 결과를 지우지 않는다."""
    identity = _identity(kind, key)
    with _store(root) as (path, data):
        if identity not in data or data[identity].get("fingerprint") != fingerprint:
            return False
        del data[identity]
        _save(path, data)
        return True


def set_candidate(root, kind, key, *, fingerprint, candidate):
    """처리한 지문과 현재 기록이 같을 때만 후보를 붙인다 (`clear` 와 같은 CAS).

    [중요] 표시(`needs_revalidation=True`)는 유지한다 — 후보는 채택 전까지 별도 산출물이다.
    """
    identity = _identity(kind, key)
    if not isinstance(candidate, dict) or not candidate.get("branch"):
        raise ValueError("재검증 후보가 올바르지 않다")
    candidate = json.loads(_canonical(candidate))
    with _store(root) as (path, data):
        entry = data.get(identity)
        if not entry or entry.get("fingerprint") != fingerprint:
            return False
        data[identity] = dict(entry, candidate=candidate, needs_revalidation=True)
        _save(path, data)
        return True


def drop_candidate(root, kind, key, *, fingerprint, head):
    """후보만 떼어 낸다 — 지문과 후보 head 가 둘 다 같을 때만 (CAS). 표시는 유지한다.

    [중요] head 까지 대조한다 — 판정과 쓰기 사이에 새 후보가 붙었으면 그것을 지우지 않는다.
    """
    identity = _identity(kind, key)
    with _store(root) as (path, data):
        entry = data.get(identity)
        if (not entry or entry.get("fingerprint") != fingerprint
                or not isinstance(entry.get("candidate"), dict)
                or entry["candidate"].get("head") != head):
            return False
        data[identity] = {k: v for k, v in entry.items() if k != "candidate"}
        data[identity]["needs_revalidation"] = True
        _save(path, data)
        return True


UNREADABLE_SAMPLE = 5


def _short(exc):
    text = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {text[:120]}"


def unreadable_summary(unreadable, *, sample=UNREADABLE_SAMPLE):
    """머리말 못 읽은 문서 요약 한 줄. 없으면 `""`. 파일별 줄은 찍지 않는다(전체는 결과에)."""
    if not unreadable:
        return ""
    names = ", ".join(u["path"] for u in unreadable[:sample])
    more = " …" if len(unreadable) > sample else ""
    return f"[revalidation] 머리말 못 읽음 {len(unreadable)}건 (예: {names}{more})"


def marked_documents(paths, *, unreadable=None):
    """기존 생성기 표기만 읽는다. 전체 문서를 재생성 대상으로 삼지 않는다.

    [중요] 머리말을 못 읽는 문서 하나가 스캔 전체를 죽이지 않는다(사용자 결정 2026-11-03) —
    「표시 없음」으로 보고 `unreadable` 목록에 `{path(트윈 기준 상대), reason}` 를 남긴다.
    그 관용은 **파일 내용 해석**(YAML 오류·dict 아님·디코딩)에만 적용한다 — 스캔 루트 경계 위반·
    디렉터리/파일 OSError 는 그대로 올라간다.
    """
    import yaml
    documents = []
    skipped = unreadable if unreadable is not None else []
    context = Path(getattr(paths, "context", Path(paths.root) / "context"))
    ontology = Path(getattr(paths, "ontology", Path(paths.root) / "ontology"))
    # 항목 단위 symlink 검사만으로는 루트 자체가 트윈 밖을 가리키는 경우를 못 막는다.
    twin = Path(paths.root).resolve()
    for scan_root in (context, ontology, ontology / "domains"):
        if scan_root.is_symlink() or (scan_root.exists()
                                      and not scan_root.resolve().is_relative_to(twin)):
            raise ValueError(f"재검증 스캔 루트가 트윈 경계 밖이다: {scan_root}")

    def skip(path, reason):
        try:
            rel = path.resolve().relative_to(twin).as_posix()
        except ValueError:
            rel = path.name
        skipped.append(dict(path=rel, reason=reason))

    if context.is_dir():
        for path in sorted(context.rglob("*.md")):
            if path.is_symlink():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                skip(path, _short(exc))
                continue
            if not text.startswith("---\n"):
                continue
            _, header, *_rest = text.split("---", 2) if text.count("---") >= 2 else ("", "", "")
            try:
                meta = yaml.safe_load(header)
            except yaml.YAMLError as exc:
                skip(path, _short(exc))
                continue
            if meta is None:
                meta = {}
            if not isinstance(meta, dict):
                skip(path, f"머리말이 mapping 이 아니다 ({type(meta).__name__})")
                continue
            if meta.get("needs_revalidation") is True:
                documents.append(dict(kind="context", key=path.relative_to(context).as_posix()[:-3],
                                      path=path, source_files=meta.get("generation_source_files"),
                                      source_fingerprint=meta.get("generation_source_fingerprint")))
    domains = ontology / "domains"
    if domains.is_dir():
        from ..ontology import yaml_io, package
        for path in sorted(domains.glob("*/" + package.MANIFEST)):
            if path.is_symlink() or path.parent.is_symlink():
                continue
            # yaml_io 는 자체 파서라 문법 오류로 예외를 내지 않는다 — 못 읽는 모양은 「mapping 아님」.
            manifest = yaml_io.read(path)
            if manifest is None:
                manifest = {}
            if not isinstance(manifest, dict):
                skip(path, f"매니페스트가 mapping 이 아니다 ({type(manifest).__name__})")
                continue
            meta = manifest.get("generation") or {}
            if isinstance(meta, dict) and meta.get("needs_revalidation") is True:
                documents.append(dict(kind="ontology", key=path.parent.name, path=path.parent,
                                      source_files=meta.get("source_files"),
                                      source_fingerprint=meta.get("source_fingerprint")))
    return documents


def _attempts_path(paths, name="document_attempts.json"):
    directory = Path(paths.root) / "revalidation"
    if directory.is_symlink():
        raise ValueError("재검증 기록 디렉터리는 심볼릭 링크일 수 없다")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    if path.is_symlink():
        raise ValueError("재검증 시도 기록은 심볼릭 링크일 수 없다")
    return path


def _read_attempts(paths, name="document_attempts.json"):
    path = _attempts_path(paths, name)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("손상된 재검증 시도 기록")
    return data


def run_documents(paths, *, limit=2, context_runner=None, ontology_runner=None):
    """표시된 대상만 기존 게이트로 재합성한다. 실패·변경 시에는 표시를 남긴다.

    `limit` 은 재합성 호출 수다 — 소스 변경·경계 거절처럼 호출 전에 끝나는 대상은 세지 않는다.
    호출한 대상은 시도 시각을 남겨 다음 주기에 가장 오래 안 본 것부터 고른다. 그러지 않으면
    정렬 앞쪽의 영구 실패가 매 주기 예산을 먹어 뒤 문서가 영영 안 돈다.
    """
    from ..context_synth import synth as context_synth
    from ..ontology import synth as ontology_synth
    context_runner = context_runner or context_synth.synthesize_group
    ontology_runner = ontology_runner or ontology_synth.refresh_domain
    attempts = _read_attempts(paths)
    unreadable = []
    entries = marked_documents(paths, unreadable=unreadable)
    entries.sort(key=lambda e: attempts.get(_identity(e["kind"], e["key"]), ""))
    outcomes = []
    calls = 0
    for entry in entries:
        if calls >= limit:
            break
        outcome = dict(kind=entry["kind"], key=entry["key"], ok=False)
        try:
            source_hash = source_fingerprint(paths, entry["source_files"])
            if source_hash != entry["source_fingerprint"]:
                outcome["reason"] = "소스 변경 — 표시와 기존 결과 보존"
                outcomes.append(outcome)
                continue
            artifact_hash = artifact_fingerprint(entry["path"])
            args = dict(cloud_only=True, expected_source_fingerprint=source_hash,
                        expected_artifact_fingerprint=artifact_hash)
            calls += 1
            attempts[_identity(entry["kind"], entry["key"])] = datetime.now(timezone.utc).isoformat()
            _save(_attempts_path(paths), attempts)
            if entry["kind"] == "context":
                result = context_runner(paths, entry["key"], entry["source_files"], **args)
                outcome["ok"] = bool(result.written and not result.needs_revalidation)
                outcome["reason"] = result.reason
            else:
                result = ontology_runner(paths, entry["key"], **args)
                outcome["ok"] = bool(result.ok and result.written and not result.needs_revalidation)
                outcome["reason"] = " / ".join(result.reasons)
        except (OSError, ValueError, TypeError) as exc:
            outcome["reason"] = f"재검증 실패 — {type(exc).__name__}: {exc}"
        outcomes.append(outcome)
    # 머리말 못 읽음은 실패가 아니다(표시 없음으로 본다) — 전체 목록만 결과에 싣는다.
    return dict(ok=all(o["ok"] for o in outcomes), entries=len(outcomes), outcomes=outcomes,
                unreadable=unreadable,
                reason="; ".join(o.get("reason", "") for o in outcomes if not o["ok"]))


# ─────────────────────────────────────────────────────────────────────────────
# 조각 재생성 (#840 T1) — 로컬 생성으로 표시된 조각만 클라우드로 다시 쓰고 **후보**로 남긴다.
# ─────────────────────────────────────────────────────────────────────────────

TASK_ATTEMPTS = "task_attempts.json"
OPEN_WORK_STATUSES = ("in_progress", "ready_for_review")
_TASK_METADATA = ("work_id", "task_id", "base_commit", "branch", "head_commit")


def _default_work_open(work_id):
    """큐에서 work 가 아직 열려 있나. 못 찾으면 닫힌 것으로 본다. 예외는 호출자가 받는다."""
    from .review import fetch_work
    work, _ = fetch_work(work_id)
    return (work or {}).get("merge_status") in OPEN_WORK_STATUSES


def _task_target(entry):
    """기록 → 재생성 대상. 빠졌거나 어긋나면 `(None, 사유)`."""
    from . import branch_names
    meta = entry.get("metadata")
    if not isinstance(meta, dict):
        return None, "metadata 없음"
    missing = [k for k in _TASK_METADATA if not isinstance(meta.get(k), str) or not meta[k].strip()]
    skeleton = meta.get("skeleton")
    if not isinstance(skeleton, dict) or not skeleton or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in skeleton.items()):
        missing.append("skeleton")
    try:
        round_no = int(meta.get("round") or 0)
    except (TypeError, ValueError):
        missing.append("round")
        round_no = 0
    if missing:
        return None, "metadata 불완전 — " + ", ".join(missing)
    if meta["task_id"] != entry.get("key"):
        return None, "metadata task_id 가 기록 key 와 다르다"
    try:
        piece = branch_names.durable_branch(meta["work_id"], meta["task_id"], round_no)
        candidate = branch_names.candidate_branch(meta["work_id"], meta["task_id"], round_no)
    except branch_names.BranchNameError as exc:
        return None, f"브랜치 이름 불가 — {exc}"
    if meta["branch"] != piece:
        return None, f"metadata branch 가 조각 브랜치 규약과 다르다 ({meta['branch']} ≠ {piece})"
    for rel in skeleton:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts or not rel.strip():
            return None, f"골조 경로가 올바르지 않다: {rel}"
    return dict(work_id=meta["work_id"], task_id=meta["task_id"], round=round_no,
                base=meta["base_commit"].strip(), piece=piece, head=meta["head_commit"].strip(),
                candidate=candidate, skeleton=dict(skeleton)), ""


def _regenerate(skeleton, *, generator, budget, log, task_id):
    """클라우드 레인만 정책 순서로. `(성공 LaneRun|None, 시도, 호출 수, 사유)`.

    [중요] 로컬 레인은 절대 부르지 않는다(`allow_local=False`). Claude 는 `llm_policy.eligible`
    이 여는 경우(agy·codex 모두 한도 소진)에만 열린다. 층1 위반은 사실 실패로 보고 다른 클라우드로.
    """
    from . import lanes, layer1, llm_policy
    attempts, calls = [], 0
    while True:
        lane = llm_policy.next_lane(attempts, allow_local=False)
        if lane is None:
            return None, attempts, calls, "클라우드 레인 소진 — " + (
                " / ".join(f"{a['lane']}:{a['kind']}" for a in attempts) or "허용 레인 없음")
        if llm_policy.family(lane) == "local":           # 그물 — 정책이 바뀌어도 로컬은 안 연다
            return None, attempts, calls, f"로컬 레인 {lane} 거절 (cloud_only)"
        if calls >= budget:
            return None, attempts, calls, "호출 예산 소진 — 다음 주기"
        calls += 1
        run = lanes.run_one(skeleton, lane, generator=generator)
        if not run.ok:
            kind = run.failure_kind or "error"
            attempts.append(dict(lane=lane, kind=kind, reason=run.reason[:300]))
            log(f"[revalidate] {task_id} {lane} 실패({kind}) — {run.reason[:160]}")
            continue
        gate = layer1.check(run.files, baseline=skeleton.get)
        if not gate.ok:
            attempts.append(dict(lane=lane, kind="facts", reason=gate.summary[:300]))
            log(f"[revalidate] {task_id} {lane} 층1 위반 — {gate.summary[:160]}")
            continue
        attempts.append(dict(lane=lane, kind="success"))
        log(f"[revalidate] {task_id} {lane} 생성·층1 통과 ({len(run.files)}파일)")
        return run, attempts, calls, ""


def _push_candidate(paths, target, files, *, lane, remote, log):
    """격리 worktree(정본 옆 · base 에 detach)에서 커밋해 후보 브랜치로 push. `(head, 사유)`.

    [중요] 강제 push 없음 — 그새 생긴 후보는 거절로 남는다. worktree 는 실패해도 지운다.
    """
    import shutil
    from .attempt import GitError, _git
    from .subbranch import _ensure_base_locally
    repo = Path(paths.repo)
    why = _ensure_base_locally(repo, target["work_id"], target["base"], remote)
    if why:
        return "", why
    tree = Path(tempfile.mkdtemp(prefix=f"ax-revalidate-{target['task_id']}-", dir=repo.parent))
    added = False
    try:
        _git(repo, "worktree", "add", "--detach", str(tree), target["base"])
        added = True
        root = tree.resolve()
        for rel, body in sorted(files.items()):
            dest = tree / rel
            if not dest.resolve().is_relative_to(root) or dest.is_symlink():
                return "", f"후보 파일 경계 이탈: {rel}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8", newline="")
        _git(tree, "add", "--", *sorted(files))
        if not _git(tree, "diff", "--cached", "--name-only"):
            return "", "골조와 차이가 없다 — 후보 커밋 없음"
        _git(tree, "commit", "-q", "-m",
             f"#840 cloud revalidation candidate — {target['task_id']} (lane={lane})\n\n"
             f"piece {target['piece']} @ {target['head'][:12]} · base {target['base'][:12]}")
        head = _git(tree, "rev-parse", "HEAD")
        _git(tree, "push", remote, f"HEAD:refs/heads/{target['candidate']}")
        log(f"[revalidate] {target['task_id']} push {target['candidate']} ← {head[:8]}")
        return head, ""
    except (GitError, OSError) as exc:
        return "", f"후보 push 실패 — {type(exc).__name__}: {str(exc)[:300]}"
    finally:
        if added:
            try:
                _git(repo, "worktree", "remove", "--force", str(tree))
            except GitError as exc:
                log(f"[revalidate] {target['task_id']} worktree 제거 실패 — {exc}")
        if tree.exists():
            shutil.rmtree(tree, ignore_errors=True)
        try:
            _git(repo, "worktree", "prune")
        except GitError:
            pass


def run_tasks(paths, *, limit=2, generator=None, work_open=None, guard=None,
              remote=None, logf=None):
    """표시된 조각만 클라우드로 다시 써서 **후보 브랜치**로 남긴다 (#840 T1).

    `limit` 은 실제 LLM 호출 수다 — 호출 전에 건너뛴 대상은 세지 않는다. 시도한 대상은 시각을
    남겨 다음 주기에 가장 오래 안 본 것부터 고른다(`run_documents` 와 같은 이유).
    조각 브랜치·작업 브랜치·라운드는 건드리지 않고, 표시는 성공해도 유지된다(채택은 ⑦).
    주입 자리: `generator(prompt, lane)` · `work_open(work_id)->bool` · `guard(paths)->사유`.
    """
    from .attempt import WRITE_REMOTE, GitError, remote_tip
    from .attempt import guard_or_reason
    log = logf or (lambda message: None)
    work_open = work_open or _default_work_open
    guard = guard or guard_or_reason
    remote = remote or WRITE_REMOTE
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("limit는 음수가 아닌 정수여야 한다")
    repo = Path(paths.repo)
    attempts = _read_attempts(paths, TASK_ATTEMPTS)
    entries = [e for e in pending(paths.root, limit=1_000_000) if e.get("kind") == "task"]
    waiting = [e for e in entries if isinstance(e.get("candidate"), dict)]
    entries = [e for e in entries if not isinstance(e.get("candidate"), dict)]
    entries.sort(key=lambda e: attempts.get(_identity("task", e["key"]), ""))
    log(f"[revalidate] 조각 대상 {len(entries)} · 채택 대기 후보 {len(waiting)} · 호출 예산 {limit}")
    outcomes, calls = [], 0
    for entry in entries:
        if calls >= limit:
            log(f"[revalidate] 호출 예산 {limit} 소진 — 나머지는 다음 주기")
            break
        key = entry["key"]
        outcome = dict(kind="task", key=key, ok=False, calls=0)
        outcomes.append(outcome)
        log(f"[revalidate] {key} 시작")

        def skip(reason):
            outcome.update(skipped=True, reason=reason)
            log(f"[revalidate] {key} 건너뜀 — {reason}")

        target, why = _task_target(entry)
        if target is None:
            skip(why)
            continue
        try:
            is_open = work_open(target["work_id"])
        except Exception as exc:                             # noqa: BLE001
            skip(f"work 상태 확인 실패 — {type(exc).__name__}: {exc}")
            continue
        if is_open is not True:
            skip(f"work {target['work_id']} 가 열려 있지 않다")
            continue
        try:
            tip = remote_tip(repo, remote, target["piece"])
            existing = remote_tip(repo, remote, target["candidate"])
        except GitError as exc:
            skip(f"원격 조회 실패 — {str(exc)[:200]}")
            continue
        if tip != target["head"]:
            skip(f"조각 브랜치가 바뀌었다 ({target['piece']} {tip[:8] or '없음'} ≠ "
                 f"{target['head'][:8]})")
            continue
        if existing:
            recorded = set_candidate(paths.root, "task", key, fingerprint=entry["fingerprint"],
                                     candidate=dict(branch=target["candidate"], head=existing,
                                                    lane="", provenance=[], recovered=True,
                                                    created_at=datetime.now(timezone.utc).isoformat()))
            skip(f"후보가 이미 있다 ({target['candidate']} {existing[:8]}) — 덮어쓰지 않음"
                 + (" · 기록에 반영" if recorded else " · 기록 지문 변경으로 반영 안 함"))
            continue
        reason = guard(paths)
        if reason:
            skip(f"쓰기 가드 — {reason}")
            continue

        attempts[_identity("task", key)] = datetime.now(timezone.utc).isoformat()
        _save(_attempts_path(paths, TASK_ATTEMPTS), attempts)
        run, tried, used, why = _regenerate(target["skeleton"], generator=generator,
                                            budget=limit - calls, log=log, task_id=key)
        calls += used
        outcome.update(calls=used, provenance=tried)
        if run is None:
            outcome["reason"] = why
            log(f"[revalidate] {key} 후보 없음 — {why} (표시 유지)")
            continue
        head, why = _push_candidate(paths, target, run.files, lane=run.lane, remote=remote, log=log)
        if not head:
            outcome["reason"] = why
            log(f"[revalidate] {key} 후보 없음 — {why} (표시 유지)")
            continue
        candidate = dict(branch=target["candidate"], head=head, lane=run.lane, provenance=tried,
                         created_at=datetime.now(timezone.utc).isoformat())
        recorded = set_candidate(paths.root, "task", key, fingerprint=entry["fingerprint"],
                                 candidate=candidate)
        outcome.update(candidate=candidate, lane=run.lane)
        if recorded:
            outcome.update(ok=True, reason="")
            log(f"[revalidate] {key} 기록 — 후보 {target['candidate']} {head[:8]} (표시 유지)")
        else:
            outcome["reason"] = "후보는 push 했지만 기록 지문이 바뀌어 반영하지 않았다"
            log(f"[revalidate] {key} {outcome['reason']}")
    return dict(ok=all(o["ok"] for o in outcomes), entries=len(outcomes), calls=calls,
                waiting=len(waiting), outcomes=outcomes,
                reason="; ".join(f"{o['key']}: {o.get('reason', '')}" for o in outcomes if not o["ok"]))


# ─────────────────────────────────────────────────────────────────────────────
# 후보 정산 (#840 T2) — LLM 0. 배치가 `run_tasks` **앞에** 부른다.
# ─────────────────────────────────────────────────────────────────────────────

def task_entries(root):
    """표시된 조각 기록 전부 (후보 유무 무관). 배치 입력 수를 세는 자리다."""
    return [e for e in pending(root, limit=1_000_000) if e.get("kind") == "task"]


def _settle_one(repo, entry, target, *, remote, work_open):
    """기록 하나의 판정. `(결정, 사유, 부가)` — 결정은 adopted·waiting·dropped·kept_closed·error.

    [중요] 판정 실패는 전부 `error` 다 — 호출자는 기록을 건드리지 않는다(fail-closed).
    """
    from .attempt import GitError, has_commit, remote_tip
    from .coordinator import _git, _git_rc
    from . import branch_names
    cand = entry.get("candidate") or {}
    head = cand.get("head")
    if not isinstance(head, str) or not head.strip():
        return "error", "후보 head 가 기록에 없다", {}
    if cand.get("branch") != target["candidate"]:
        return "error", (f"후보 브랜치 기록이 규약과 다르다 "
                         f"({cand.get('branch')} ≠ {target['candidate']})"), {}
    base = branch_names.base_branch(target["work_id"])
    try:
        base_tip = remote_tip(repo, remote, base)
        if not base_tip:
            return "error", f"작업 브랜치 {base} 가 원격에 없다 — 채택 여부 판정 불가", {}
        _git(repo, "fetch", "-q", remote, f"refs/heads/{base}")
        if not has_commit(repo, base_tip):
            return "error", f"작업 브랜치 tip {base_tip[:8]} 을 가져오지 못했다", {}
        cand_tip = remote_tip(repo, remote, target["candidate"])
        if not has_commit(repo, head) and cand_tip:
            _git(repo, "fetch", "-q", remote, f"refs/heads/{target['candidate']}")
    except GitError as exc:
        return "error", f"원격 조회 실패 — {str(exc)[:200]}", {}
    extra = dict(base=base, base_tip=base_tip, candidate_tip=cand_tip)
    if has_commit(repo, head):
        rc, out = _git_rc(repo, "merge-base", "--is-ancestor", head, base_tip)
        if rc == 0:
            return "adopted", f"후보 {head[:8]} 이 {base} {base_tip[:8]} 에 들어 있다 — 채택", extra
        if rc != 1:
            return "error", f"도달 판정 실패 rc={rc} — {out[:200]}", extra
    # 여기부터 미채택. (작업 브랜치 이력을 다 가져왔는데 head 객체가 없으면 그 이력에 없다.)
    if cand_tip:
        note = "" if cand_tip == head else f" · 원격 tip {cand_tip[:8]} ≠ 기록 {head[:8]}"
        return "waiting", f"미채택 · 후보 브랜치 있음 — 채택 대기{note}", extra
    try:
        is_open = work_open(target["work_id"])
    except Exception as exc:                                 # noqa: BLE001
        return "error", f"후보 브랜치 없음 · work 상태 확인 실패 — {type(exc).__name__}: {exc}", extra
    if is_open is True:
        return "dropped", "미채택 · 후보 브랜치 삭제됨 · work 열림 — 후보를 떼어 다음 주기 재생성", extra
    return "kept_closed", (f"미채택 · 후보 브랜치 삭제됨 · work {target['work_id']} 닫힘 "
                           f"— 기록 유지(사람 판단)"), extra


def settle_tasks(paths, *, remote=None, work_open=None, logf=None, dry_run=False):
    """후보가 붙은 조각 기록을 정산한다 (#840 T2). LLM 0.

        채택됨(후보 head 가 원격 `task/<work>/base` 에 도달)    → `clear`(지문 CAS)
        미채택 · 후보 브랜치 있음                              → 그대로(채택 대기)
        미채택 · 후보 브랜치 삭제 · work 열림                   → 후보만 뗀다(지문+head CAS)
        미채택 · 후보 브랜치 삭제 · work 닫힘                   → 그대로 · 보고
        판정 실패(원격·fetch·work 조회·기록 불완전)              → 그대로 · 보고 · ok=False

    [주의] 채택 판정은 **조상 관계**다 — ⑦ 이 후보 커밋을 머지(그 커밋이 이력에 남는 방식)로
    들여야 잡힌다. squash·cherry-pick 이면 「미채택」으로 보인다.
    `dry_run=True` 면 판정과 로그만 하고 기록은 쓰지 않는다(git fetch 는 한다 — 객체만, ref 없음).
    """
    from .attempt import WRITE_REMOTE
    log = logf or (lambda message: None)
    work_open = work_open or _default_work_open
    remote = remote or WRITE_REMOTE
    repo = Path(paths.repo)
    entries = [e for e in task_entries(paths.root) if isinstance(e.get("candidate"), dict)]
    log(f"[settle] 후보 붙은 조각 {len(entries)}건" + (" · dry-run(기록 안 씀)" if dry_run else ""))
    outcomes = []
    counts = dict(adopted=0, waiting=0, dropped=0, kept_closed=0, error=0)
    for entry in entries:
        key = entry["key"]
        outcome = dict(kind="task", key=key, ok=True)
        outcomes.append(outcome)
        target, why = _task_target(entry)
        if target is None:
            decision, reason, extra = "error", why, {}
        else:
            decision, reason, extra = _settle_one(repo, entry, target, remote=remote,
                                                  work_open=work_open)
        applied = None
        if not dry_run and decision == "adopted":
            applied = clear(paths.root, "task", key, fingerprint=entry["fingerprint"])
        elif not dry_run and decision == "dropped":
            applied = drop_candidate(paths.root, "task", key, fingerprint=entry["fingerprint"],
                                     head=entry["candidate"].get("head"))
        if applied is False:
            reason += " · [주의] 기록이 그새 바뀌어(지문/후보 CAS) 반영하지 않았다"
            decision = "error"
        outcome.update(decision=decision, reason=reason, **extra)
        if dry_run and decision in ("adopted", "dropped"):
            outcome["dry_run"] = True
        if decision == "error":
            outcome["ok"] = False
        counts[decision] += 1
        verb = {"adopted": "해제", "dropped": "후보 뗌", "waiting": "유지", "kept_closed": "유지",
                "error": "건드리지 않음"}[decision]
        if dry_run and decision in ("adopted", "dropped"):
            verb = f"(dry-run) {verb} 예정"
        log(f"[settle] {key} {decision} — {reason} → {verb}")
    summary = " · ".join(f"{k} {v}" for k, v in counts.items())
    log(f"[settle] 요약 — {summary}")
    return dict(ok=all(o["ok"] for o in outcomes), entries=len(outcomes), counts=counts,
                dry_run=dry_run, outcomes=outcomes, summary=summary,
                reason="; ".join(f"{o['key']}: {o['reason']}" for o in outcomes if not o["ok"]))
