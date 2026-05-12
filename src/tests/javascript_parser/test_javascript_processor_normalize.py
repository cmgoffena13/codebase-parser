"""Processor normalized_path for JS/TS mirrors Python-style dotted paths."""

from pathlib import Path

from src.processor import CodeProcessor


def test_normalize_path_javascript_typescript_tsx():
    proc = object.__new__(CodeProcessor)
    p = Path("src/components/Button.tsx")
    assert proc._normalize_path(p, language="javascript") == "src.components.button"
    assert proc._normalize_path(p, language="typescript") == "src.components.button"
    assert proc._normalize_path(p, language="tsx") == "src.components.button"
