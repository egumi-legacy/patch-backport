from typing import Dict, Any, List
from pathlib import Path
import yaml
from datetime import datetime
import time
from loguru import logger
from modules.base_module import BaseModule
from core.adaptation_result import AdaptationResult
from config_manager import ProjectConfig
from modules.base_module import ModuleContext

class AdaptationPipeline:
    def __init__(self, config: ProjectConfig):
        """
        初始化适配管道
        :param config: ProjectConfig对象，包含所有必要的配置
        """
        self.config = config
        self.modules = {}
        self.results_dir = config.base_dir / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化启用的模块
        if not config.pipeline.enabled_modules:
            raise ValueError("No modules enabled in pipeline configuration")
            
        self._initialize_modules(config.pipeline.enabled_modules)
    
    def _initialize_modules(self, enabled_modules: List[str]):
        """初始化模块"""
        # logger.debug(f"开始初始化模块，配置信息: {self.config}")
        for module_name in enabled_modules:
            try:
                # 获取模块类
                module_class = self._get_module_class(module_name)
                if not module_class:
                    logger.warning(f"Module {module_name} not found, skipping")
                    continue
                
                # logger.debug(f"初始化模块 {module_name} 的配置: {self.config}")
                # 直接使用ProjectConfig对象初始化模块
                module = module_class(self.config)
                self.modules[module_name] = module
                
            except Exception as e:
                logger.error(f"初始化模块 {module_name} 失败: {e}")
                import traceback
                logger.debug(f"错误堆栈: {traceback.format_exc()}")
                if self.config.pipeline.stop_on_failure:
                    raise
    
    def _get_module_class(self, module_name: str) -> type:
        """获取模块类"""
        from modules import module_registry
        return module_registry.get(module_name)
    
    def process_patch(self, context: ModuleContext) -> AdaptationResult:
        """处理补丁"""
        try:
            # 执行每个模块
            for module_name, module in self.modules.items():
                try:
                    logger.info(f"执行模块: {module_name}")
                    start_time = datetime.now()
                    
                    # 执行模块
                    context = module.execute(context)
                    
                    # 记录模块执行结果
                    duration = (datetime.now() - start_time).total_seconds()
                    module_result = {
                        'module': module_name,
                        'success': True,
                        'duration': duration,
                        'metrics': module.get_metrics()
                    }
                    
                    context.module_results.append(module_result)
                    
                except Exception as e:
                    logger.error(f"模块 {module_name} 执行失败: {e}")
                    import traceback
                    logger.error(f"错误堆栈: {traceback.format_exc()}")
                    module_result = {
                        'module': module_name,
                        'success': False,
                        'error': str(e),
                        'duration': (datetime.now() - start_time).total_seconds()
                    }
                    context.module_results.append(module_result)
                    
                    if self.config.pipeline.stop_on_failure:
                        raise
            
            # 创建适配结果
            return AdaptationResult(
                metadata={
                    'timestamp': datetime.now().isoformat(),
                    'commit_sha': context.patch_info.get('commit_sha'),
                    'patch_url': context.patch_info.get('patch_url'),
                    'target_version': context.patch_info.get('target_version')
                },
                configuration=self.config.dict(),
                results={
                    'module_results': context.module_results,
                    'final_status': self._get_final_status(context)
                }
            )
            
        except Exception as e:
            logger.error(f"Pipeline执行失败: {e}")
            return AdaptationResult(
                metadata={
                    'timestamp': datetime.now().isoformat(),
                    'error': str(e)
                },
                configuration=self.config.dict(),
                results={
                    'module_results': context.module_results,
                    'final_status': {
                        'success': False,
                        'error': str(e)
                    }
                }
            )
    
    def _get_final_status(self, context: ModuleContext) -> Dict[str, Any]:
        """获取最终状态"""
        # 检查是否有直接应用成功
        if (context.direct_apply_result and 
            context.direct_apply_result.get('success', False)):
            return {
                'success': True,
                'method': 'direct_apply',
                'message': '直接应用成功'
            }
        
        # 检查是否有成功的适配补丁
        if context.adapted_patches:
            successful_patches = [p for p in context.adapted_patches 
                                if p.get('success', False)]
            if successful_patches:
                return {
                    'success': True,
                    'method': 'llm_adaptation',
                    'message': f'成功适配 {len(successful_patches)} 个补丁'
                }
        
        # 如果都失败了
        return {
            'success': False,
            'message': '所有适配方法都失败了'
        }
    
    def _save_result(self, result: AdaptationResult):
        """保存结果到文件"""
        commit_sha = result.metadata["commit_sha"]
        timestamp = result.metadata["timestamp"].replace(":", "-")
        result_file = self.results_dir / f"{commit_sha}_{timestamp}.yaml"
        
        with open(result_file, "w") as f:
            yaml.dump(result.to_dict(), f, default_flow_style=False)