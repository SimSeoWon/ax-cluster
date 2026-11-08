#!/usr/bin/env python3
"""Gemini 4 Argon vs Gemini 3.8 Flash 실측 평가 스크립트 (#913).

특정 PC 경로 하드코딩 없이 저장소 루트 및 실행 환경을 동적으로 감지한다.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 동적 저장소 루트 탐색
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT))

# agy CLI 탐색
AGY_EXE = shutil.which("agy") or "agy"


def run_agy(model: str, prompt: str, timeout: int = 120) -> dict:
    """agy CLI를 통해 지정 모델로 프롬프트를 실행하고 JSON 결과를 반환한다."""
    cmd = [
        AGY_EXE,
        "--model", model,
        "--output-format", "json",
        "--print", prompt,
    ]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        elapsed = time.monotonic() - t0
        stdout = proc.stdout.strip()
        if not stdout:
            return {
                "ok": False,
                "error": f"Empty output (rc={proc.returncode}): {proc.stderr.strip()}",
                "elapsed": elapsed,
            }
        try:
            data = json.loads(stdout)
            data["ok"] = (proc.returncode == 0 and data.get("status") == "SUCCESS")
            data["wall_elapsed"] = elapsed
            return data
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": f"JSON decode error (rc={proc.returncode}): {stdout[:200]}",
                "raw_stdout": stdout,
                "elapsed": elapsed,
            }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Timeout after {timeout}s",
            "elapsed": time.monotonic() - t0,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "elapsed": time.monotonic() - t0,
        }


def eval_scenario1_review(commit_hash: str = "201a81a") -> dict:
    """시나리오 1: 층2 자동 리뷰 및 Grounding 정확도 실측 대조."""
    print(f"[시나리오 1] 커밋 {commit_hash} 리뷰 프롬프트 생성...")
    from master.context_synth import review_gen

    # git show로 diff 획득
    diff_proc = subprocess.run(
        ["git", "show", "--no-color", commit_hash],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    diff = diff_proc.stdout

    # 커밋 변경 파일 목록 획득
    files_proc = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", commit_hash],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    files = [f.strip() for f in files_proc.stdout.splitlines() if f.strip()]

    prompt = review_gen.build_prompt(
        diff=diff,
        files=files,
        commit=commit_hash,
        kind="code",
        subject=f"Review test for commit {commit_hash}",
    )

    models = ["gemini-3.8-flash-medium", "gemini-4-argon-medium"]
    results = {}

    for m in models:
        print(f"  > 모델 {m} 호출 중...")
        res = run_agy(m, prompt, timeout=180)
        response_text = res.get("response", "")

        # 형식 준수 검사
        verdicts = review_gen.parse_verdicts(response_text)
        has_verdict_section = bool(verdicts)

        # Grounding 검사: 응답에서 언급된 파일명이 실제 변경 파일에 포함되는지
        mentioned_files = [f for f in files if f in response_text]

        results[m] = {
            "ok": res.get("ok", False),
            "duration_seconds": res.get("duration_seconds", res.get("wall_elapsed")),
            "usage": res.get("usage", {}),
            "verdicts_count": len(verdicts),
            "verdicts": verdicts,
            "has_verdict_section": has_verdict_section,
            "mentioned_files": mentioned_files,
            "response_preview": response_text[:500],
            "full_response": response_text,
        }
        print(f"  > {m} 완료: {results[m]['duration_seconds']:.2f}s, verdicts={len(verdicts)}")

    return results


def eval_scenario2_code_generation() -> dict:
    """시나리오 2: 코드 구현력 및 복합 추론력(작성 레인 agy) 평가."""
    print("[시나리오 2] 코드 구현 및 추론력 평가 프롬프트 실행...")

    prompt = (
        "You are an expert Python engineer. Implement a robust metadata extractor using Python's standard library `ast`.\n"
        "Requirements:\n"
        "1. Write a pure function `extract_metadata(source: str) -> dict[str, dict]`.\n"
        "2. Parse the input Python source code and extract all top-level functions and classes.\n"
        "3. For each definition, return a dictionary with:\n"
        "   - 'type': 'function' or 'class'\n"
        "   - 'decorators': list of decorator name strings\n"
        "   - 'has_docstring': boolean (True if docstring exists, False otherwise)\n"
        "   - 'line_number': integer of starting line\n"
        "4. Handle syntax errors gracefully by raising `ValueError` with the syntax error message.\n"
        "5. Output STRICTLY AND ONLY the Python code without any explanation, markdown backticks, or greetings."
    )

    models = ["gemini-3.8-flash-medium", "gemini-4-argon-medium"]
    results = {}

    for m in models:
        print(f"  > 모델 {m} 호출 중...")
        res = run_agy(m, prompt, timeout=120)
        code_text = res.get("response", "")

        # 마크다운 백틱 제거 시도 및 파싱
        cleaned_code = code_text.strip()
        had_backticks = False
        if cleaned_code.startswith("```"):
            had_backticks = True
            lines = cleaned_code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_code = "\n".join(lines).strip()

        # AST 검증
        ast_ok = False
        ast_err = ""
        try:
            ast.parse(cleaned_code)
            ast_ok = True
        except Exception as exc:
            ast_err = str(exc)

        # 동적 실행 검증 (격리 환경)
        func_ok = False
        func_err = ""
        if ast_ok:
            try:
                local_scope = {}
                exec(cleaned_code, local_scope)
                fn = local_scope.get("extract_metadata")
                if callable(fn):
                    sample_code = """
@decorator_one
@module.decorator_two
def sample_func():
    '''This is a docstring.'''
    pass

class SampleClass:
    pass
"""
                    res_data = fn(sample_code)
                    if (
                        "sample_func" in res_data
                        and res_data["sample_func"]["has_docstring"] is True
                        and "SampleClass" in res_data
                        and res_data["SampleClass"]["has_docstring"] is False
                    ):
                        func_ok = True
                    else:
                        func_err = f"Returned unexpected structure: {res_data}"
                else:
                    func_err = "extract_metadata function not found"
            except Exception as exc:
                func_err = str(exc)

        results[m] = {
            "ok": res.get("ok", False),
            "duration_seconds": res.get("duration_seconds", res.get("wall_elapsed")),
            "usage": res.get("usage", {}),
            "had_backticks": had_backticks,
            "ast_ok": ast_ok,
            "ast_err": ast_err,
            "func_ok": func_ok,
            "func_err": func_err,
            "response_preview": code_text[:300],
            "full_code": cleaned_code,
        }
        print(f"  > {m} 완료: {results[m]['duration_seconds']:.2f}s, ast_ok={ast_ok}, func_ok={func_ok}, had_backticks={had_backticks}")

    return results


def main() -> int:
    output_dir = SCRIPT_DIR
    out_file = output_dir / "argon_eval_result.json"

    print("=== Gemini 4 Argon vs Gemini 3.8 Flash 평가 시작 ===")
    s1_res = eval_scenario1_review("201a81a")
    s2_res = eval_scenario2_code_generation()

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "scenario1_review": s1_res,
        "scenario2_code_gen": s2_res,
    }

    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"=== 평가 완료! 결과 저장: {out_file} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
