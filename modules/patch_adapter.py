from typing import Dict, Any
from pathlib import Path
from loguru import logger
from .base_module import BaseModule, ModuleType
from patch_processor import PatchProcessor

class PatchAdapterModule(BaseModule):
    """补丁适配模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.PATCH_ADAPTER
        self.name = "patch_adapter"
        self.processor = PatchProcessor(config)
        self.successful_patches = 0
        self.failed_patches = 0
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        if not context.get("llm_output"):
            logger.info("没有LLM输出，跳过补丁适配")
            return context
        
        logger.info("开始应用LLM生成的补丁")
        try:
            adapted_patches = []
            for response in context["llm_output"]["openai_responses"]:
                try:
                    output_path = self.processor.save_response_to_project(response)
                    self.processor.apply_llm_patch(output_path)
                    adapted_patches.append({
                        'path': str(output_path),
                        'success': True
                    })
                    self.successful_patches += 1
                except Exception as e:
                    logger.error(f"应用补丁失败: {e}")
                    adapted_patches.append({
                        'success': False,
                        'error': str(e)
                    })
                    self.failed_patches += 1
            
            context["adapted_patches"] = adapted_patches
            
        except Exception as e:
            logger.error(f"补丁适配过程发生错误: {e}")
            context["patch_adapter_error"] = str(e)
        
        return context
    
    def get_metrics(self) -> Dict[str, Any]:
        total_patches = self.successful_patches + self.failed_patches
        return {
            "successful_patches": self.successful_patches,
            "failed_patches": self.failed_patches,
            "success_rate": (
                self.successful_patches / total_patches 
                if total_patches > 0 else 0
            )
        } 