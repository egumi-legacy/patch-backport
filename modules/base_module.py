from typing import Dict, Any
from enum import Enum

class ModuleType(Enum):
    DIRECT_APPLY = "direct_apply"
    AST_PARSER = "ast_parser"
    FUZZY_MATCHER = "fuzzy_matcher"
    LLM_ADAPTER = "llm_adapter"
    COMPILER = "compiler"
    PATCH_ADAPTER = "patch_adapter"

class BaseModule:
    """模块基类"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.type = ModuleType.DIRECT_APPLY
        self.name = "base_module"
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行模块逻辑"""
        raise NotImplementedError
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取模块执行指标"""
        return {} 