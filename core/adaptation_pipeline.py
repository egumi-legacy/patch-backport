from typing import Dict, Any
from pathlib import Path
import yaml
from datetime import datetime
import time
from loguru import logger
from modules.base_module import BaseModule
from core.adaptation_result import AdaptationResult

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
            try:
                module_config = self.config.get(f"{module_name}_config", {})
                module_class = self._get_module_class(module_name)
                if module_class:
                    self.modules[module_name] = module_class(module_config)
                else:
                    logger.warning(f"找不到模块类: {module_name}")
            except Exception as e:
                logger.error(f"初始化模块 {module_name} 失败: {e}")
    
    def _get_module_class(self, module_name: str) -> type:
        """获取模块类"""
        from modules import module_registry
        return module_registry.get(module_name)
    
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