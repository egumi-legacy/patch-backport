from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from enum import Enum
from core.parameter_manager import ModuleContext, ModuleType
from datetime import datetime
from loguru import logger
import json

# class ModuleType(Enum):
#     DIRECT_APPLY = "direct_apply"
#     # AST_PARSER = "ast_parser"
#     # FUZZY_MATCHER = "fuzzy_matcher"
#     LLM_ADAPTER = "llm_adapter"
#     COMPILER = "compiler"
#     PATCH_ADAPTER = "patch_adapter"

class BaseModule(ABC):
    """模块基类"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.type = None
        self.name = None
        # self.name = "base_module"
        self.metrics = {
            'total_attempts': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'error_types': {},
            'execution_time': 0
        }
    
    @abstractmethod
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行模块处理"""
        pass
    
    # def execute(self, context: ModuleContext) -> ModuleContext:
    #     """执行模块逻辑"""
    #     raise NotImplementedError

    def _should_run(self, context: ModuleContext) -> bool:
        """判断是否应该运行此模块"""
        # 检查模块是否启用
        if self.name not in context.config.enabled_modules:
            logger.info(f"模块 {self.name} 未启用，跳过")
            return False
        
        # 检查前置条件
        if self.type == ModuleType.LLM_ADAPTER:
            # 如果直接应用成功，跳过LLM处理
            if context.direct_apply_result and context.direct_apply_result.get('success', False):
                logger.info("直接应用成功，跳过LLM处理")
                return False
        
        elif self.type == ModuleType.PATCH_ADAPTER:
            # 如果没有LLM响应，跳过补丁适配
            if not context.llm_output:
                logger.info("没有LLM响应，跳过补丁适配")
                return False
        
        elif self.type == ModuleType.COMPILER:
            # 如果没有适配补丁，跳过编译
            if not context.adapted_patches:
                logger.info("没有适配补丁，跳过编译")
                return False
        
        return True
    
    def _update_metrics(self, success: bool, error_type: Optional[str] = None, execution_time: float = 0):
        """更新指标统计"""
        self.metrics['total_attempts'] += 1
        if success:
            self.metrics['successful_executions'] += 1
        else:
            self.metrics['failed_executions'] += 1
            if error_type:
                self.metrics['error_types'][error_type] = self.metrics['error_types'].get(error_type, 0) + 1
        
        self.metrics['execution_time'] += execution_time
    
    def _save_metrics(self, context: ModuleContext):
        """保存评测指标到文件"""
        try:
            # 使用正确的评估目录路径
            eval_dir = context.base_dir / "evaluations" / self.name
            eval_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            commit_sha = context.commit.commit_sha[:6]
            eval_file = eval_dir / f"metrics_{commit_sha}_{timestamp}.json"
            
            success_rate = (self.metrics['successful_executions'] / 
                          self.metrics['total_attempts'] if self.metrics['total_attempts'] > 0 else 0)
            
            evaluation = {
                'metrics': self.metrics,
                'config': {
                    'timestamp': timestamp,
                    'commit_sha': commit_sha,
                    'module_name': self.name,
                    'target_version': context.config.target_version
                },
                'summary': {
                    'success_rate': success_rate,
                    'total_attempts': self.metrics['total_attempts'],
                    'successful_executions': self.metrics['successful_executions'],
                    'error_distribution': self.metrics['error_types'],
                    'average_execution_time': self.metrics['execution_time'] / max(1, self.metrics['total_attempts'])
                }
            }
            
            with open(eval_file, 'w') as f:
                json.dump(evaluation, f, indent=2)
            logger.info(f"评测指标已保存到: {eval_file}")
            
        except Exception as e:
            logger.error(f"保存评测指标失败: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取模块指标"""
        return self.metrics