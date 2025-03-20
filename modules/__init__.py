from .direct_apply import DirectApplyModule
from .backtrack_apply import BacktrackApplyModule
from .chunk_analyzer import ChunkAnalyzerModule
from .llm_adapter import LLMAdapterModule
from .patch_adapter import PatchAdapterModule
from .compiler import CompilerModule
# from .ast_parser import ASTParserModule
# from .fuzzy_matcher import FuzzyMatcherModule

module_registry = {
    "direct_apply": DirectApplyModule,
    "backtrack_apply": BacktrackApplyModule,
    "chunk_analyzer": ChunkAnalyzerModule,
    "llm_adapter": LLMAdapterModule,
    "patch_adapter": PatchAdapterModule,
    "compiler": CompilerModule,
    # "ast_parser": ASTParserModule,
    # "fuzzy_matcher": FuzzyMatcherModule
} 