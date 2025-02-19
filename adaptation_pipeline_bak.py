from typing import List, Dict, Any
from pathlib import Path
import yaml
from datetime import datetime
import json
from dataclasses import dataclass, asdict
from enum import Enum
import time

class ModuleType(Enum):
    DIRECT_APPLY = "direct_apply"
    AST_PARSER = "ast_parser"
    FUZZY_MATCHER = "fuzzy_matcher"
    LLM_ADAPTER = "llm_adapter"
    COMPILER = "compiler"
    PATCH_ADAPTER = "patch_adapter"

@dataclass
class AdaptationResult:
    """适配结果数据类"""
    metadata: Dict[str, Any]
    configuration: Dict[str, Any]
    results: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

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

class AdaptationPipeline:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.modules: Dict[str, BaseModule] = {}
        self.results_dir = Path(config.get("results_dir", "results"))
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化启用的模块
        self._initialize_modules()
    
    def _initialize_modules(self):
        """初始化所有配置中启用的模块"""
        enabled_modules = self.config.get("enabled_modules", [])
        for module_name in enabled_modules:
            module_config = self.config.get(f"{module_name}_config", {})
            module_class = self._get_module_class(module_name)
            if module_class:
                self.modules[module_name] = module_class(module_config)
    
    def _get_module_class(self, module_name: str) -> type:
        """获取模块类"""
        module_map = {
            "direct_apply": DirectApplyModule,
            # "ast_parser": ASTParserModule,
            # "fuzzy_matcher": FuzzyMatcherModule,
            "llm_adapter": LLMAdapterModule,
            "compiler": CompilerModule,
            "patch_adapter": PatchAdapterModule
        }
        return module_map.get(module_name)
    
    def process_patch(self, patch_info: Dict[str, Any]) -> AdaptationResult:
        """处理补丁"""
        context = {
            "patch_info": patch_info,
            "start_time": datetime.now(),
            "module_results": []
        }
        
        # 记录初始元数据
        metadata = {
            "timestamp": context["start_time"].isoformat(),
            "commit_sha": patch_info.get("commit_sha"),
            "target_version": patch_info.get("target_version")
        }
        
        # 记录配置信息
        configuration = {
            "enabled_modules": list(self.modules.keys()),
            "module_configs": {name: module.config for name, module in self.modules.items()}
        }
        
        try:
            # 按顺序执行每个模块
            for module_name, module in self.modules.items():
                start_time = time.time()
                try:
                    context = module.execute(context)
                    duration = time.time() - start_time
                    
                    # 记录模块执行结果
                    module_result = {
                        "module": module_name,
                        "duration": duration,
                        "success": True,
                        "metrics": module.get_metrics()
                    }
                    
                except Exception as e:
                    module_result = {
                        "module": module_name,
                        "duration": time.time() - start_time,
                        "success": False,
                        "error": str(e)
                    }
                    
                context["module_results"].append(module_result)
                
                # 如果模块失败且配置为失败时停止，则中断流程
                if not module_result["success"] and self.config.get("stop_on_failure", True):
                    break
            
            # 整理最终结果
            results = {
                "module_results": context["module_results"],
                "final_status": self._get_final_status(context)
            }
            
        except Exception as e:
            results = {
                "module_results": context.get("module_results", []),
                "final_status": {
                    "success": False,
                    "error": str(e)
                }
            }
        
        # 创建结果对象
        adaptation_result = AdaptationResult(
            metadata=metadata,
            configuration=configuration,
            results=results
        )
        
        # 保存结果
        self._save_result(adaptation_result)
        
        return adaptation_result
    
    def _get_final_status(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """获取最终状态"""
        module_results = context["module_results"]
        return {
            "success": all(r["success"] for r in module_results),
            "total_duration": sum(r["duration"] for r in module_results),
            "successful_modules": [r["module"] for r in module_results if r["success"]],
            "failed_modules": [r["module"] for r in module_results if not r["success"]]
        }
    
    def _save_result(self, result: AdaptationResult):
        """保存结果到文件"""
        commit_sha = result.metadata["commit_sha"]
        timestamp = result.metadata["timestamp"].replace(":", "-")
        result_file = self.results_dir / f"{commit_sha}_{timestamp}.yaml"
        
        with open(result_file, "w") as f:
            yaml.dump(result.to_dict(), f, default_flow_style=False)

class DirectApplyModule(BaseModule):
    """直接应用补丁模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.DIRECT_APPLY
        self.name = "direct_apply"
        self.evaluator = PatchEvaluator(config)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        patch_info = context["patch_info"]
        patch_path = patch_info.get("patch_path")
        
        # 尝试直接应用补丁
        apply_result = self.evaluator.try_direct_apply(
            patch_file=patch_path,
            single_file=False
        )
        
        context["direct_apply_result"] = apply_result
        return context
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "apply_success": self.evaluator.last_apply_success,
            "error_count": self.evaluator.error_count
        }

class LLMAdapterModule(BaseModule):
    """LLM适配模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.LLM_ADAPTER
        self.name = "llm_adapter"
        self.llm_assistant = LLMAssistant(config)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # 只在直接应用失败时执行
        if context.get("direct_apply_result", {}).get("success", False):
            return context
            
        # 准备LLM输入
        patch_processor = PatchProcessor(self.config)
        processor_output = patch_processor.run()
        
        # 调用LLM
        llm_output = self.llm_assistant.run()
        context["llm_output"] = llm_output
        
        return context

class PatchAdapterModule(BaseModule):
    """补丁适配模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.PATCH_ADAPTER
        self.name = "patch_adapter"
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not context.get("llm_output"):
            return context
            
        patch_processor = PatchProcessor(self.config)
        for response in context["llm_output"]["openai_responses"]:
            output_path = patch_processor.save_response_to_project(response)
            patch_processor.apply_llm_patch(output_path)
            
        return context

class CompilerModule(BaseModule):
    """编译测试模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.COMPILER
        self.name = "compiler"
        self.evaluator = PatchEvaluator(config)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        adapted_dir = self.config.base_dir / f"adapted_{self.config.target_version}"
        if not adapted_dir.exists():
            return context
            
        compilation_result = self.evaluator.try_compile(adapted_dir)
        context["compilation_result"] = compilation_result
        
        return context