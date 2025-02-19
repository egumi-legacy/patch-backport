from typing import Dict, Any
from loguru import logger
from .base_module import BaseModule, ModuleType
from patch_evaluator import PatchEvaluator

class DirectApplyModule(BaseModule):
    """直接应用补丁模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        self.type = ModuleType.DIRECT_APPLY
        self.name = "direct_apply"

        logger.info(f"config3:{config}")
        self.evaluator = PatchEvaluator(config)
        
        self.last_apply_success = False
        self.error_count = 0
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        patch_info = context["patch_info"]
        patch_path = patch_info.get("patch_path")
        
        logger.info(f"尝试直接应用补丁: {patch_path}")
        
        try:
            # 尝试直接应用补丁
            apply_result = self.evaluator.try_direct_apply(
                patch_file=patch_path,
                single_file=False
            )
            
            self.last_apply_success = apply_result.get('success', False)
            if not self.last_apply_success:
                self.error_count += 1
                logger.warning(f"直接应用失败: {apply_result.get('error')}")
            else:
                logger.info("直接应用成功")
            
            context["direct_apply_result"] = apply_result
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"直接应用过程发生错误: {e}")
            context["direct_apply_result"] = {
                'success': False,
                'error': str(e)
            }
        
        return context
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "apply_success": self.last_apply_success,
            "error_count": self.error_count
        } 