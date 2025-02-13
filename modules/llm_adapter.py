from typing import Dict, Any
from loguru import logger
from .base_module import BaseModule, ModuleType
from llm_assistant import LLMAssistant
from patch_processor import PatchProcessor

class LLMAdapterModule(BaseModule):
    """LLM适配模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.LLM_ADAPTER
        self.name = "llm_adapter"
        self.llm_assistant = LLMAssistant(config)
        self.processor = PatchProcessor(config)
        self.total_tokens = 0
        self.successful_adaptations = 0
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # 只在直接应用失败时执行
        if context.get("direct_apply_result", {}).get("success", False):
            logger.info("直接应用成功，跳过LLM处理")
            return context
        
        logger.info("开始LLM适配流程")
        try:
            # 准备LLM输入
            processor_output = self.processor.run()
            context.update(processor_output)
            
            # 调用LLM
            llm_output = self.llm_assistant.run()
            context["llm_output"] = llm_output
            
            # 更新指标
            self.total_tokens += sum(llm_output.get("request_tokens", []))
            self.total_tokens += sum(llm_output.get("response_tokens", []))
            if llm_output.get("openai_responses"):
                self.successful_adaptations += 1
                
        except Exception as e:
            logger.error(f"LLM适配过程发生错误: {e}")
            context["llm_error"] = str(e)
        
        return context
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "successful_adaptations": self.successful_adaptations,
            "average_tokens_per_success": (
                self.total_tokens / self.successful_adaptations 
                if self.successful_adaptations > 0 else 0
            )
        } 