"""Go import rows; structure mirrors ``test_py_imports`` (Go syntax differs from Python)."""

from pathlib import Path

import pytest

from src.processor import CodeProcessor
from src.tests.python_parser._assertions import assert_imports_invariants


def test_imports_spot_checks_basic_fixture(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("basic.go")
    _, imports, _ = go_parser.parse(1, file_bytes)

    assert len(imports) == 2
    assert_imports_invariants(imports)

    assert any(
        i["import_path"] == "fmt" and i["imported_symbol"] == "" and i["alias"] is None
        for i in imports
    )
    assert any(
        i["import_path"] == "strings"
        and i["imported_symbol"] == ""
        and i["alias"] is None
        for i in imports
    )
    assert all(i["import_type"] == "absolute" for i in imports)


def test_imports_aliases(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("import_aliases.go")
    symbols, imports, references = go_parser.parse(10, file_bytes)

    assert len(symbols) == 0
    assert len(references) == 0
    assert len(imports) == 3
    assert_imports_invariants(imports)

    assert any(
        i["import_path"] == "os"
        and i["imported_symbol"] == ""
        and i["alias"] == "operating_system"
        for i in imports
    )
    assert any(
        i["import_path"] == "path/filepath"
        and i["imported_symbol"] == ""
        and i["alias"] == "filepath"
        for i in imports
    )
    assert any(
        i["import_path"] == "encoding/json"
        and i["imported_symbol"] == ""
        and i["alias"] == "j"
        for i in imports
    )


def test_imports_multiple_in_one_statement(go_parser, go_fixture_bytes):
    file_bytes = go_fixture_bytes("imports_multiple.go")
    symbols, imports, references = go_parser.parse(11, file_bytes)

    assert len(symbols) == 0
    assert len(references) == 0
    assert len(imports) == 4
    assert_imports_invariants(imports)

    paths = {(i["import_path"], i["imported_symbol"]) for i in imports}
    assert ("bytes", "") in paths
    assert ("io", "") in paths
    assert ("os", "") in paths
    assert ("path/filepath", "") in paths


def test_go_normalized_path_for_files_matches_import_path_segments():
    """``resolve_imports`` joins on ``files.normalized_path``; Go keeps POSIX slashes."""
    proc = object.__new__(CodeProcessor)
    p = Path("src/Foo.go")
    assert proc._normalize_path(p, language="go") == "src/foo"
    assert proc._normalize_path(p, language="python") == "src.foo"


@pytest.mark.parametrize(
    ("path", "language", "expected"),
    [
        (Path("pkg/Sub/Thing.go"), "go", "pkg/sub/thing"),
        (Path("X.go"), "go", "x"),
        (Path("docs/Notes.md"), None, "docs/notes"),
    ],
)
def test_go_normalize_path_param(path: Path, language: str | None, expected: str):
    proc = object.__new__(CodeProcessor)
    assert proc._normalize_path(path, language=language) == expected
