from typing import Dict, Any
from pathlib import Path
from loguru import logger
from .base_module import BaseModule, ModuleType
from patch_evaluator import PatchEvaluator

class CompilerModule(BaseModule):
    """编译测试模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.COMPILER
        self.name = "compiler"
        self.evaluator = PatchEvaluator(config)
        self.successful_compilations = 0
        self.failed_compilations = 0
        self.total_files = 0
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        adapted_dir = self.config.base_dir / f"adapted_{self.config.target_version}"
        if not adapted_dir.exists():
            logger.info(f"适配目录不存在: {adapted_dir}")
            return context
        
        logger.info("开始编译测试")
        try:
            compilation_result = self.evaluator.try_compile(adapted_dir)
            context["compilation_result"] = compilation_result
            
            # 更新指标
            if compilation_result.get('success', False):
                self.successful_compilations += 1
            else:
                self.failed_compilations += 1
            
            self.total_files += len(compilation_result.get('modified_files', []))
            
        except Exception as e:
            logger.error(f"编译测试过程发生错误: {e}")
            context["compilation_error"] = str(e)
            self.failed_compilations += 1
        
        return context
    
    def get_metrics(self) -> Dict[str, Any]:
        total_attempts = self.successful_compilations + self.failed_compilations
        return {
            "successful_compilations": self.successful_compilations,
            "failed_compilations": self.failed_compilations,
            "total_files": self.total_files,
            "success_rate": (
                self.successful_compilations / total_attempts 
                if total_attempts > 0 else 0
            ),
            "average_files_per_compilation": (
                self.total_files / total_attempts 
                if total_attempts > 0 else 0
            )
        } 