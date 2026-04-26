from typing import Dict, List, Tuple

from tree_sitter import Parser

from src.assigner import GlobalIDAssigner
from src.db import CodeDB


class ParserBase:
    def __init__(self, assigner: GlobalIDAssigner, db: CodeDB, parser: Parser):
        self.assigner = assigner
        self.db = db
        self.symbols_snapshot = {}
        self.stack: List[Tuple[int, str, str]] = []
        self.symbols: List[Dict] = []
        self.imports: List[Dict] = []
        self.symbol_references_staging: List[Dict] = []

    def parse(
        self, file_id: int, file_bytes: bytes
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        raise NotImplementedError
