"""저장소 작업 리포트의 읽기 전용 목록·상세 (#919).

고정된 reports/*.md와 reports/research/*.md만 읽는다. 목록의 시각·커밋 작성자는
로컬 Git 이력이고, 본문에서 찾은 작성 표기·이슈·해시는 별도로 표시한다.
"""
from __future__ import annotations

import html
import os
import posixpath
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from .. import redmine
from ..status import _CSS
from .nav import SIDE_CSS, nav_html

REPO = Path(__file__).resolve().parents[2]
_ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")
_SHA = re.compile(r"(?<![\w])([0-9a-f]{7,40})(?![\w])")
_TOKEN = re.compile(r"(`[^`\n]+`|\[[^\]\n]+\]\([^\s)]+\)|\*\*[^*\n]+\*\*)")
_STYLE = """
.report-list{width:100%;border-collapse:collapse}.report-list td,.report-list th{padding:.65rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.report-meta,.note{color:var(--dim);font-size:.85rem}.report-meta{line-height:1.8}.report-body{line-height:1.75;overflow-wrap:anywhere;max-width:1000px}
.report-body pre{overflow:auto;background:var(--card);border:1px solid var(--line);padding:1rem;border-radius:8px;white-space:pre;line-height:1.5}
.report-body table{border-collapse:collapse;min-width:50%}.report-body th,.report-body td{border:1px solid var(--line);padding:.4rem .6rem;text-align:left}
.report-body .wrap{overflow:auto}.report-body blockquote{border-left:3px solid var(--line);padding-left:1rem;color:var(--dim)}
.report-body code{font-size:.9em}.report-list small{display:block;color:var(--dim)}.report-body h2,.report-body h3{margin-top:1.8rem}
form{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0}input,select,button{font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);padding:.4rem;border-radius:5px}
"""


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _shell(body):
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>작업 리포트</title><style>{_CSS}{SIDE_CSS}{_STYLE}</style></head>'
            f'<body><div class="shell">{nav_html("/reports")}<main>{body}</main></div></body></html>').encode()


def _git(*args):
    """네트워크 없는 로컬 이력 조회. 실패는 메타 미상으로 표시한다."""
    result = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                            text=True, timeout=15)
    if result.returncode:
        raise OSError("Git metadata unavailable")
    return result.stdout


def _history():
    history, commits = {}, set()
    try:
        raw = _git("log", "--format=%x1e%H%x00%ct%x00%an", "--name-only", "--", "reports")
        for block in raw.split("\x1e"):
            lines = block.strip().splitlines()
            if not lines:
                continue
            sha, stamp, author = lines[0].split("\x00", 2)
            for filename in lines[1:]:
                if filename.startswith("reports/"):
                    history.setdefault(filename[8:], {"sha": sha, "stamp": int(stamp), "author": author})
        commits = {s.strip() for s in _git("log", "--all", "--format=%H").splitlines()
                   if re.fullmatch(r"[0-9a-f]{40}", s.strip())}
        return history, commits, True
    except (OSError, ValueError, subprocess.SubprocessError):
        return history, commits, False


def _commit(sha, commits):
    matches = [s for s in commits if s.startswith(sha)]
    return matches[0] if len(matches) == 1 else ""


def _allowed(relative):
    """단일 파일명 또는 research/파일명만. URL 이중 인코딩도 허용하지 않는다."""
    name = unquote(str(relative))
    if not name or any(c in name for c in ("\\", "%", "\x00", "\r", "\n")):
        raise ValueError("invalid report path")
    parts = PurePosixPath(name).parts
    if name.startswith("/") or name != "/".join(parts):
        raise ValueError("invalid report path")
    if not (len(parts) == 1 or len(parts) == 2 and parts[0] == "research"):
        raise ValueError("invalid report path")
    if any(part.startswith(".") for part in parts) or not name.endswith(".md"):
        raise ValueError("invalid report path")
    base = REPO / "reports"
    candidate = base.joinpath(*parts)
    if base.is_symlink() or any(base.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts)+1)):
        raise ValueError("linked report")
    if not candidate.resolve().is_relative_to(base.resolve()):
        raise ValueError("invalid report path")
    return name, candidate


def _href(name):
    return "/reports?file=" + quote(name, safe="")


def _issue_href(number):
    base = redmine.base_url()
    return base + "/issues/" + number if _external(base) else ""


def _external(url):
    try:
        parsed = urlsplit(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc) and not parsed.username and not parsed.password
    except ValueError:
        return False


def _commit_base():
    """Git 원격 URL에서 저장소를 읽고, 웹 base는 기존 Gitea 설정으로 결정한다."""
    # SSH 원격의 포트는 웹 포트가 아니므로 origin만 보고 웹 주소를 지어내지 않는다.
    # AX 배포 웹 포트 정본: machines/sim-desktop.d/services.md (Gitea 3000).
    base = os.environ.get("AX_GITEA_WEB_URL", "http://192.168.0.57:3000").rstrip("/")
    if not _external(base):
        return ""
    try:
        origin = _git("remote", "get-url", "origin").strip()
        if "://" in origin:
            remote = urlsplit(origin)
            host, path = remote.hostname, remote.path.lstrip("/")
        else:
            match = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):(.+)", origin)
            if not match:
                return ""
            host, path = match.groups()
        if path.endswith(".git"):
            path = path[:-4]
        if host != urlsplit(base).hostname or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
            return ""
        return base + "/" + path
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""


def _link(label, url):
    return f'<a href="{_e(url)}" rel="noopener noreferrer">{_e(label)}</a>' if url else _e(label)


def _plain(text, commits, commit_base):
    def ref(match):
        token = match.group()
        if token.startswith("#"):
            return _link(token, _issue_href(token[1:]))
        sha = _commit(token, commits)
        return _link(token, commit_base + "/commit/" + sha if sha and commit_base else "")
    return _refs(text, ref)


def _refs(text, replace):
    out, previous = [], 0
    pattern = re.compile(r"(?<![\w/])#\d+\b|(?<![\w])[0-9a-f]{7,40}(?![\w])")
    for match in pattern.finditer(text):
        out.extend((_e(text[previous:match.start()]), replace(match)))
        previous = match.end()
    out.append(_e(text[previous:]))
    return "".join(out)


def _inline(text, current, commits, commit_base):
    out, previous = [], 0
    for match in _TOKEN.finditer(text):
        out.append(_plain(text[previous:match.start()], commits, commit_base))
        token = match.group()
        if token.startswith("`"):
            value = token[1:-1]
            sha = _commit(value, commits) if _SHA.fullmatch(value) else ""
            label = _link(value, commit_base + "/commit/" + sha) if sha and commit_base else _e(value)
            out.append("<code>" + label + "</code>")
        elif token.startswith("**"):
            out.append("<strong>" + _plain(token[2:-2], commits, commit_base) + "</strong>")
        else:
            label, target = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
            url = target if _external(target) else ""
            try:
                relative_target = not urlsplit(target).scheme and not target.startswith(("/", "\\"))
            except ValueError:
                relative_target = False
            if not url and relative_target:
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(current), target))
                try:
                    name, candidate = _allowed(resolved)
                    if candidate.is_file():
                        url = _href(name)
                except ValueError:
                    pass
            out.append(_link(label, url))
        previous = match.end()
    out.append(_plain(text[previous:], commits, commit_base))
    return "".join(out)


def render_markdown(text, current, commits, commit_base):
    """리포트용 안전한 MD: 원시 HTML을 실행하지 않고 코드 펜스·표·목록을 보존한다."""
    lines, out, paragraph, i = text.splitlines(), [], [], 0
    inline = lambda s: _inline(s, current, commits, commit_base)

    def flush():
        if paragraph:
            out.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(("```", "~~~")):
            flush()
            fence = line[:3]
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>" + _e("\n".join(code)) + "</code></pre>")
        elif re.match(r"^#{1,6}\s+", line):
            flush()
            level, title = line.split(None, 1)
            n = min(len(level)+1, 6)
            out.append(f"<h{n}>" + inline(title) + f"</h{n}>")
        elif line.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [s.strip() for s in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                out.append('<div class="wrap"><table><thead><tr>' + "".join("<th>"+inline(c)+"</th>" for c in rows[0]) + "</tr></thead><tbody>" + "".join("<tr>"+"".join("<td>"+inline(c)+"</td>" for c in row)+"</tr>" for row in rows[1:]) + "</tbody></table></div>")
            continue
        elif re.match(r"^(?:[-*]|\d+\.)\s+", line):
            flush()
            ordered = bool(re.match(r"^\d+\.", line))
            tag = "ol" if ordered else "ul"
            items = []
            pattern = r"^\d+\.\s+(.*)$" if ordered else r"^[-*]\s+(.*)$"
            while i < len(lines) and (match := re.match(pattern, lines[i].strip())):
                items.append("<li>"+inline(match[1])+"</li>")
                i += 1
            out.append(f"<{tag}>"+"".join(items)+f"</{tag}>")
            continue
        elif line.startswith(">"):
            flush()
            out.append("<blockquote>"+inline(line[1:].strip())+"</blockquote>")
        elif not line or line == "---":
            flush()
        else:
            paragraph.append(line)
        i += 1
    flush()
    return "\n".join(out)


def _record(name, path, history):
    text = path.read_text(encoding="utf-8", errors="replace")
    title = next((m[1] for line in text.splitlines() if (m := re.match(r"^#\s+(.*)", line))), path.stem)
    writer = next((line.lstrip("> ") for line in text.splitlines()[:25]
                   if re.search(r"작성\s*[:：]|지휘\s|Author\s*:", line, re.I)), "미상")
    return {"name": name, "title": title, "text": text, "writer": writer,
            "issues": sorted(set(_ISSUE.findall(text)), key=int), "git": history.get(name)}


def _metadata(record, commit_base):
    meta = record.get("git")
    if not meta:
        return "커밋 시각·작성자 미상 · 파일명순"
    at = datetime.fromtimestamp(meta["stamp"], timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit = _link(meta["sha"][:12], commit_base+"/commit/"+meta["sha"] if commit_base else "")
    return _e(at) + " · " + _e(meta["author"]) + " · " + commit


def page(relative="", *, query="", kind=""):
    try:
        if kind not in ("", "work", "research"):
            raise ValueError("invalid kind")
        history, commits, available = _history()
        commit_base = _commit_base()
        body = '<h1>작업 리포트</h1>'
        if relative:
            name, path = _allowed(relative)
            if not path.is_file():
                return 404, _shell(body+'<p>리포트를 찾을 수 없습니다.</p>')
            record = _record(name, path, history)
            body += '<a href="/reports">← 리포트 목록</a><h2>'+_e(record["title"])+"</h2>"
            body += '<p class="report-meta">'+_e(name)+"<br>"+_metadata(record, commit_base)+"<br>본문 작성 표기: "+_e(record["writer"])+"</p>"
            body += '<article class="report-body">'+render_markdown(record["text"], name, commits, commit_base)+"</article>"
        else:
            body += '<p class="note">저장소에 남긴 작업·연구 기록입니다. 최신 커밋 순이며, Git 정보가 없는 문서는 파일명순으로 뒤에 표시합니다. 리포트 이후 마감·배달 결과는 연결된 Redmine 노트에서 확인하세요.</p>'
            body += '<form><input name="q" aria-label="제목·본문 검색" placeholder="제목·본문·일감 번호" value="'+_e(query)+'"><select name="kind" aria-label="리포트 종류">'+"".join('<option value="'+v+'"'+(' selected' if kind==v else '')+'>'+label+'</option>' for v,label in (("","전체"),("work","작업"),("research","연구")))+'</select><button>조회</button></form>'
            records = []
            for candidate in (REPO/"reports").glob("*.md"):
                try:
                    name, path = _allowed(candidate.name)
                    if path.is_file():
                        records.append(_record(name, path, history))
                except ValueError:
                    continue
            for candidate in (REPO/"reports"/"research").glob("*.md"):
                try:
                    name, path = _allowed("research/"+candidate.name)
                    if path.is_file():
                        records.append(_record(name, path, history))
                except ValueError:
                    continue
            records = [r for r in records if (not query or query.casefold() in (r["name"]+" "+r["text"]).casefold()) and (not kind or (kind=="research")==r["name"].startswith("research/"))]
            records.sort(key=lambda r: (bool(r["git"]), r["git"]["stamp"] if r["git"] else 0, r["name"]), reverse=True)
            if not available:
                body += '<p class="note">Git 이력 조회 불가: 확인된 정보만 표시하며 나머지는 파일명순입니다.</p>'
            body += '<p class="report-meta">'+str(len(records))+'개 리포트</p><div class="wrap"><table class="report-list"><thead><tr><th>리포트</th><th>본문 작성 표기</th><th>최종 커밋</th><th>관련 일감</th></tr></thead><tbody>'
            for record in records:
                body += '<tr><td><a href="'+_href(record["name"])+'">'+_e(record["title"])+'</a><small>'+_e(record["name"])+"</small></td><td>"+_e(record["writer"])+"</td><td>"+_metadata(record, commit_base)+"</td><td>"+" · ".join(_link("#"+n, _issue_href(n)) for n in record["issues"])+"</td></tr>"
            body += "</tbody></table></div>"
        return 200, _shell(body)
    except ValueError:
        return 400, _shell('<h1>작업 리포트</h1><p>리포트 경로·조회 조건을 확인하세요.</p>')
    except (OSError, subprocess.SubprocessError):
        return 503, _shell('<h1>작업 리포트</h1><p>리포트를 읽을 수 없습니다.</p>')
