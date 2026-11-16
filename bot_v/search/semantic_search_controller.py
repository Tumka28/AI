from bot_v.search.file_scanner import FileScanner
from bot_v.search.index_builder import IndexBuilder
from bot_v.search.semantic_search import SemanticSearch
from bot_v.search.high_level_query import HighLevelQueryExpander

class SemanticSearchController:
    def __init__(self):
        self.scanner = FileScanner()
        self.builder = IndexBuilder()
        self.searcher = SemanticSearch()
        self.expander = HighLevelQueryExpander()

    def build_index(self, root="."):
        files = self.scanner.scan(root)
        self.builder.build(files)
        return {"status": "index built", "files": len(files)}

    def search(self, query):
        expanded = self.expander.expand(query)
        results = self.searcher.search(expanded)
        return {"query": query, "expanded": expanded, "results": results}
