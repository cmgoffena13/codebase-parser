from pathlib import Path

from src.assigner import GlobalIDAssigner
from src.db import CodeDB
from src.parsers.factory import ParserFactory


def test_snapshot_deletes_removed_symbol_and_reference_go(tmp_path: Path):
    first = b"""package snap

func a() {
	b()
}

func b() int { return 1 }
"""
    second = b"""package snap

func a() {
	return 1
}
"""

    db = CodeDB(tmp_path)
    assigner = GlobalIDAssigner(db)
    parser = ParserFactory.get_parser("go", assigner, db)

    sym1, imp1, ref1 = parser.parse(99, first)
    db.bulk_insert(
        {
            "directories": [],
            "files": [],
            "symbols": sym1,
            "imports": imp1,
            "symbol_references": ref1,
        }
    )
    db.resolve_symbol_references()
    db.resolve_imports(0, 0)

    assigner2 = GlobalIDAssigner(db)
    parser2 = ParserFactory.get_parser("go", assigner2, db)
    sym2, _imp2, ref2 = parser2.parse(99, second)

    assert len(sym1) == 2
    assert len(ref1) == 1
    assert len(sym2) == 0
    assert len(ref2) == 0


def test_snapshot_allows_two_type_annotations_same_line_distinct_refs_go(
    tmp_path: Path,
):
    first = b"""package snap

func f(a Thing, b Other) int { return 0 }

type Thing struct{}
type Other struct{}
"""

    db = CodeDB(tmp_path)
    assigner = GlobalIDAssigner(db)
    parser = ParserFactory.get_parser("go", assigner, db)

    ref1 = parser.parse(100, first)[2]
    db.bulk_insert(
        {
            "directories": [],
            "files": [],
            "symbols": [],
            "imports": [],
            "symbol_references": ref1,
        }
    )
    db.resolve_symbol_references()
    db.resolve_imports(0, 0)

    assigner2 = GlobalIDAssigner(db)
    parser2 = ParserFactory.get_parser("go", assigner2, db)
    ref2 = parser2.parse(100, first)[2]

    assert len(ref1) == len(ref2)
    keys1 = {
        (r["ref_symbol_qualified_name"], r["ref_kind"], r["source_line"]) for r in ref1
    }
    keys2 = {
        (r["ref_symbol_qualified_name"], r["ref_kind"], r["source_line"]) for r in ref2
    }
    assert len(keys1) == len(ref1)
    assert len(keys2) == len(ref2)
