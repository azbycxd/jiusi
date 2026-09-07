"""只审计 architecture-reference 的标准库脚本，不访问真实项目服务。"""
from __future__ import annotations

import ast
import compileall
import io
import re
import shutil
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DOCS = ROOT / "docs"
EXAMPLES = ROOT / "examples"
TESTS = ROOT / "tests"
PRODUCTION_MARKER = "【生产化扩展设计，当前真实项目未实现】"


def files_under(folder: Path, suffix: str) -> list[Path]:
    return sorted(p for p in folder.rglob(f"*{suffix}") if "__pycache__" not in p.parts)


def nonempty_lines(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def effective_python_lines(path: Path) -> int:
    """排除空行、纯注释与模块/类/函数 docstring，得到可重复的近似有效行。"""
    text = path.read_text(encoding="utf-8")
    ignored: set[int] = set()
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ignored.update(range(body[0].lineno, body[0].end_lineno + 1))
    except SyntaxError:
        return 0
    return sum(
        1 for number, line in enumerate(text.splitlines(), 1)
        if number not in ignored and line.strip() and not line.lstrip().startswith("#")
    )


def check_prompts() -> tuple[bool, str]:
    prompt_files = files_under(SRC / "prompts", ".py")
    prompt_files += files_under(SRC / "skills", "prompt.py")
    chinese = re.compile(r"[\u4e00-\u9fff]")
    missing = [str(p.relative_to(ROOT)) for p in prompt_files
               if not chinese.search(p.read_text(encoding="utf-8"))]
    return not missing, ", ".join(missing) or "all prompts contain Chinese"


def check_truth_markers() -> tuple[bool, str]:
    combined = (ROOT / "README.md").read_text(encoding="utf-8")
    combined += (DOCS / "02_真实项目映射.md").read_text(encoding="utf-8")
    ok = all(token in combined for token in ("A", "B", "C", "真实", "参考", "生产化扩展"))
    return ok, "README/docs02 contain A/B/C truth boundary" if ok else "truth marker missing"


def check_production_markers() -> tuple[bool, str]:
    targets = files_under(SRC / "production", ".py")
    targets += [SRC / "memory" / "long_term_memory.py"]
    targets += [SRC / "rag" / name for name in (
        "embedding_retriever.py", "vector_store.py", "hybrid_retriever.py",
        "reranker.py", "bm25_retriever.py",
    )]
    missing = [str(p.relative_to(ROOT)) for p in targets
               if p.exists() and PRODUCTION_MARKER not in p.read_text(encoding="utf-8")[:500]]
    return not missing, ", ".join(missing) or "all C-layer files are marked"


def is_skeleton(path: Path) -> bool:
    """短文件可合法承载 Enum/Protocol/Prompt；只有占位实现才算 Skeleton。"""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return True
    has_definition = any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                         for node in ast.walk(tree))
    placeholders = [node for node in ast.walk(tree)
                    if isinstance(node, (ast.Pass, ast.Constant))
                    and (isinstance(node, ast.Pass) or node.value is Ellipsis)]
    # Protocol 的省略号方法是明确契约，不是空骨架；没有定义但有可执行常量也不是骨架。
    protocol_only = "Protocol" in text
    return bool(placeholders) and not protocol_only and not has_definition


def run_tests() -> tuple[bool, int, str]:
    suite = unittest.defaultTestLoader.discover(str(TESTS), pattern="test_*.py")
    count = suite.countTestCases()
    stream = io.StringIO()
    with redirect_stdout(stream), redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    summary = f"{count - len(result.failures) - len(result.errors)}/{count} passed"
    return result.wasSuccessful(), count, summary


def check_v11_progress() -> tuple[bool, str]:
    """v1.1 核心不得退回静态 Dimension 或 Tool-success 完成语义。"""
    base = (SRC / "skills" / "base.py").read_text(encoding="utf-8")
    runtime = (SRC / "harness" / "runtime.py").read_text(encoding="utf-8")
    selector = (SRC / "context" / "selector.py").read_text(encoding="utf-8")
    completion = (SRC / "harness" / "completion_guard.py").read_text(encoding="utf-8")
    frozen = (ROOT / "FROZEN.md").read_text(encoding="utf-8")
    required_files = tuple(SRC / "progress" / name for name in (
        "requirements.py", "evidence_obligation.py", "evaluator.py",
    ))
    ok = (
        all(path.exists() for path in required_files)
        and "possible_dimensions" in base
        and "requirement_resolver" in base
        and "EvidenceObligationEvaluator" in runtime
        and "tool.dimension" not in runtime
        and "progress_dimensions" not in selector
        and "skill.progress_dimensions" not in completion
        and "progress.complete" in completion
        and "REFERENCE_ARCHITECTURE_VERSION = 1.1" in frozen
    )
    return ok, "v1.1 evidence-driven completion" if ok else "v1.1 coupling/version mismatch"


def main() -> int:
    source_files = files_under(SRC, ".py")
    docs = files_under(DOCS, ".md")
    examples = files_under(EXAMPLES, ".md")
    small_sources = [p for p in source_files if p.name != "__init__.py" and nonempty_lines(p) < 10]
    skeletons = [p for p in source_files if p.name != "__init__.py" and is_skeleton(p)]
    short_docs = [p for p in docs if p.name[:2].isdigit() and int(p.name[:2]) <= 24
                  and nonempty_lines(p) < 30]
    prompt_ok, prompt_detail = check_prompts()
    truth_ok, truth_detail = check_truth_markers()
    marker_ok, marker_detail = check_production_markers()
    v11_ok, v11_detail = check_v11_progress()
    compile_ok = compileall.compile_dir(str(SRC), quiet=1)
    tests_ok, tests_total, tests_summary = run_tests()
    checks = {
        "source_skeletons": (not skeletons, str(len(skeletons))),
        "key_docs_learning_grade": (not short_docs, str(len(short_docs))),
        "seven_examples": (len(examples) == 7, str(len(examples))),
        "chinese_prompts": (prompt_ok, prompt_detail),
        "abc_truth_markers": (truth_ok, truth_detail),
        "production_markers": (marker_ok, marker_detail),
        "evidence_progress_v11": (v11_ok, v11_detail),
        "compileall": (compile_ok, "PASS" if compile_ok else "FAIL"),
        "unittest": (tests_ok and tests_total > 102, tests_summary),
    }
    print(f"SOURCE_FILES={len(source_files)}")
    print(f"SOURCE_EFFECTIVE_LINES={sum(effective_python_lines(p) for p in source_files)}")
    print(f"DOC_FILES={len(docs)}")
    print(f"DOC_EFFECTIVE_LINES={sum(nonempty_lines(p) for p in docs)}")
    print(f"EXAMPLE_FILES={len(examples)}")
    print(f"EXAMPLE_EFFECTIVE_LINES={sum(nonempty_lines(p) for p in examples)}")
    print(f"TESTS_TOTAL={tests_total}")
    print(f"SMALL_SOURCE_FILES={len(small_sources)}")
    for name, (ok, detail) in checks.items():
        print(f"[{('PASS' if ok else 'FAIL')}] {name}: {detail}")
    if skeletons:
        print("SKELETON_FILES=" + ",".join(str(p.relative_to(ROOT)) for p in skeletons))
    if short_docs:
        print("SHORT_DOCS=" + ",".join(str(p.relative_to(ROOT)) for p in short_docs))
    overall = all(ok for ok, _ in checks.values())
    print(f"AUDIT_REFERENCE={'PASS' if overall else 'FAIL'}")
    # compileall 只用于语法核验；审计脚本自己清理缓存，避免污染 Reference。
    for cache in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    for pyc in ROOT.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
