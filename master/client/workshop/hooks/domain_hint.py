"""PostToolUse hook: 편집된 파일이 속한 도메인 정보를 Claude에게 전달한다."""
import sys, json, subprocess
from pathlib import Path

def main():
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return

    cwd = data.get("cwd", ".")
    exe = Path(cwd) / ".claude" / "mcp" / "context_search.exe"
    if not exe.exists():
        return

    query = Path(file_path).stem
    try:
        result = subprocess.run(
            [str(exe), "--search", cwd, query, "3"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return

        info = json.loads(result.stdout.strip())
        results = info.get("results", [])
        domains = [r for r in results if "_domains/" in r.get("file", "")]
        if domains:
            d = domains[0]
            hint = f"[도메인] {d.get('file', '')}\n{d.get('content_preview', '')[:300]}"
            print(hint, file=sys.stderr)
    except Exception:
        pass

if __name__ == "__main__":
    main()
