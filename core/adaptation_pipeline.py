from typing import Dict, Any, List, Optional
import yaml
from datetime import datetime
from loguru import logger
from modules.base_module import BaseModule
import importlib
# from core.adaptation_result import AdaptationResult
# from config_manager import ProjectConfig
from core.parameter_manager import ModuleContext, BaseConfig

class AdaptationPipeline:
    def __init__(self, config: BaseConfig):
        """
        初始化适配管道
        :param config: ProjectConfig对象，包含所有必要的配置
        """
        self.config = config
        self.modules = self._load_modules()

        
        # # 初始化启用的模块
        # if not config.pipeline.enabled_modules:
        #     raise ValueError("No modules enabled in pipeline configuration")
            
        # self._initialize_modules(config.pipeline.enabled_modules)

    def _load_modules(self) -> List[BaseModule]:
        """加载模块"""
        modules = []
        
        # 模块映射
        module_mapping = {
            "direct_apply": "modules.direct_apply.DirectApplyModule",
            "llm_adapter": "modules.llm_adapter.LLMAdapterModule",
            "patch_adapter": "modules.patch_adapter.PatchAdapterModule",
            "compiler": "modules.compiler.CompilerModule"
        }
        
        # 根据配置加载模块
        for module_name in self.config.enabled_modules:
            if module_name not in module_mapping:
                logger.warning(f"未知模块: {module_name}")
                continue
                
            try:
                # 动态导入模块
                module_path, class_name = module_mapping[module_name].rsplit('.', 1)
                module = importlib.import_module(module_path)
                module_class = getattr(module, class_name)
                
                # 实例化模块
                module_instance = module_class(self.config)
                modules.append(module_instance)
                
                logger.info(f"已加载模块: {module_name}")
            except Exception as e:
                logger.error(f"加载模块 {module_name} 失败: {e}")
        
        return modules
    
    def _should_run(self, module: BaseModule, context: ModuleContext) -> bool:
        """判断是否应该运行模块"""
        return module._should_run(context)
    
    def process_patch(self, context: ModuleContext) -> ModuleContext:
        """处理单个补丁"""
        logger.info(f"开始处理补丁: {context.commit.commit_sha}")
        
        start_time = datetime.now()
        
        # 执行模块
        for module in self.modules:
            # 直接应用成功后应该跳过后续所有模块（除了编译模块）
            if hasattr(context, 'direct_apply_result') and context.direct_apply_result and context.direct_apply_result.get('success', False):
                # if not isinstance(module, CompilerModule):
                logger.info(f"直接应用成功，跳过模块: {module.__class__.__name__}")
                continue
            if not self._should_run(module, context):
                continue
            
                
            logger.info(f"执行模块: {module.name}")
            
            try:
                context = module.execute(context)
                
                logger.info(f"此时upstream_patch_path存在状态: {True if context.commit.patch_path.exists() else False}")
                # 检查是否需要停止
                if context.last_error and self.config.stop_on_failure:
                    logger.error(f"模块 {module.name} 执行失败，停止处理: {context.last_error}")
                    break
                    
            except Exception as e:
                logger.error(f"模块 {module.name} 执行异常: {e}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
                
                context.last_error = str(e)
                
                if self.config.stop_on_failure:
                    break
        
        # 记录处理时间
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"补丁处理完成，耗时: {execution_time:.2f}秒")
        
        return context

    # def _initialize_modules(self, enabled_modules: List[str]):
    #     """初始化模块"""
    #     # logger.debug(f"开始初始化模块，配置信息: {self.config}")
    #     for module_name in enabled_modules:
    #         try:
    #             # 获取模块类
    #             module_class = self._get_module_class(module_name)
    #             if not module_class:
    #                 logger.warning(f"Module {module_name} not found, skipping")
    #                 continue
                
    #             # logger.debug(f"初始化模块 {module_name} 的配置: {self.config}")
    #             # 直接使用ProjectConfig对象初始化模块
    #             module = module_class(self.config)
    #             self.modules[module_name] = module
                
    #         except Exception as e:
    #             logger.error(f"初始化模块 {module_name} 失败: {e}")
    #             import traceback
    #             logger.debug(f"错误堆栈: {traceback.format_exc()}")
    #             if self.config.pipeline.stop_on_failure:
    #                 raise
    
    # def _get_module_class(self, module_name: str) -> type:
    #     """获取模块类"""
    #     from modules import module_registry
    #     return module_registry.get(module_name)
    
    # def process_patch(self, context: ModuleContext) -> AdaptationResult:
    #     """处理补丁"""
    #     try:
    #         # 执行每个模块
    #         for module_name, module in self.modules.items():
    #             try:
    #                 logger.info(f"执行模块: {module_name}")
    #                 start_time = datetime.now()
                    
    #                 # 执行模块
    #                 context = module.execute(context)
                    
    #                 # 记录模块执行结果
    #                 duration = (datetime.now() - start_time).total_seconds()
    #                 module_result = {
    #                     'module': module_name,
    #                     'success': True,
    #                     'duration': duration,
    #                     'metrics': module.get_metrics()
    #                 }
                    
    #                 context.module_results.append(module_result)
                    
    #             except Exception as e:
    #                 logger.error(f"模块 {module_name} 执行失败: {e}")
    #                 import traceback
    #                 logger.error(f"错误堆栈: {traceback.format_exc()}")
    #                 module_result = {
    #                     'module': module_name,
    #                     'success': False,
    #                     'error': str(e),
    #                     'duration': (datetime.now() - start_time).total_seconds()
    #                 }
    #                 context.module_results.append(module_result)
                    
    #                 if self.config.pipeline.stop_on_failure:
    #                     raise
            
    #         # 创建适配结果
    #         return AdaptationResult(
    #             metadata={
    #                 'timestamp': datetime.now().isoformat(),
    #                 'commit_sha': context.patch_info.get('commit_sha'),
    #                 'patch_url': context.patch_info.get('patch_url'),
    #                 'target_version': context.patch_info.get('target_version')
    #             },
    #             configuration=self.config.dict(),
    #             results={
    #                 'module_results': context.module_results,
    #                 'final_status': self._get_final_status(context)
    #             }
    #         )
            
    #     except Exception as e:
    #         logger.error(f"Pipeline执行失败: {e}")
    #         return AdaptationResult(
    #             metadata={
    #                 'timestamp': datetime.now().isoformat(),
    #                 'error': str(e)
    #             },
    #             configuration=self.config.dict(),
    #             results={
    #                 'module_results': context.module_results,
    #                 'final_status': {
    #                     'success': False,
    #                     'error': str(e)
    #                 }
    #             }
    #         )
    
    # def _get_final_status(self, context: ModuleContext) -> Dict[str, Any]:
    #     """获取最终状态"""
    #     # 检查是否有直接应用成功
    #     if (context.direct_apply_result and 
    #         context.direct_apply_result.get('success', False)):
    #         return {
    #             'success': True,
    #             'method': 'direct_apply',
    #             'message': '直接应用成功'
    #         }
        
    #     # 检查是否有成功的适配补丁
    #     if context.adapted_patches:
    #         successful_patches = [p for p in context.adapted_patches 
    #                             if p.get('success', False)]
    #         if successful_patches:
    #             return {
    #                 'success': True,
    #                 'method': 'llm_adaptation',
    #                 'message': f'成功适配 {len(successful_patches)} 个补丁'
    #             }
        
    #     # 如果都失败了
    #     return {
    #         'success': False,
    #         'message': '所有适配方法都失败了'
    #     }
    
    # def _save_result(self, result: AdaptationResult):
    #     """保存结果到文件"""
    #     commit_sha = result.metadata["commit_sha"]
    #     timestamp = result.metadata["timestamp"].replace(":", "-")
    #     result_file = self.results_dir / f"{commit_sha}_{timestamp}.yaml"
        
    #     with open(result_file, "w") as f:
    #         yaml.dump(result.to_dict(), f, default_flow_style=False)