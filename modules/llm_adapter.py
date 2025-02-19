from typing import Dict, Any
from loguru import logger
from .base_module import BaseModule, ModuleType, ModuleContext
from llm_assistant import LLMAssistant
from patch_processor import PatchProcessor
from config_manager import ProjectConfig
from pathlib import Path
import pprint

class LLMAdapterModule(BaseModule):
    """LLM适配模块"""
    def __init__(self, config: ProjectConfig):
        super().__init__(config)
        self.type = ModuleType.LLM_ADAPTER
        self.name = "llm_adapter"
        
        # 检查关键配置
        if not config.model:
            logger.warning("model not set, using default model")
            config.model = "qwen-plus"
            
        if not config.prompt_template_file:
            raise ValueError("prompt_template_file is required")
        
        # logger.debug(f"LLMAdapter配置验证完成: model={config.model}, prompt_template={config.prompt_template_file}")
        
        # self.config = config
        # logger.info("hello1")
        
        # logger.info("hello3")
        self.total_tokens = 0
        self.successful_adaptations = 0
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        # 只在直接应用失败时执行
        if context.direct_apply_result and context.direct_apply_result.get("success", False):
            logger.info("直接应用成功，跳过LLM处理")
            return context
        
        logger.info("开始LLM适配流程")
        try:
            
            # 调用LLM
            self.processor = PatchProcessor(self.config)
            
            
            # 准备LLM输入
            processor_output = self.processor.run()
            self.config.update(**processor_output)
            use_cache = self.config.extra_config.get("use_cache", False)
            logger.info(f"use_cache:{use_cache}")
            if use_cache:
                self.config.extra_config["cache_path"] = self.processor.get_response_path()
                print(f"self.config.extra_config['cache_path']:{self.config.extra_config['cache_path']}")

            context.batch_update(processor_output)

            logger.debug("the context now is:")
            pprint.pprint(f"{context}")
            
            self.llm_assistant = LLMAssistant(self.config)
            llm_output = self.llm_assistant.run()

            

            context.update_data("llm_output", llm_output)
            # context.llm_output = llm_output
            
            # 更新指标
            self.total_tokens += sum(llm_output.get("request_tokens", []))
            self.total_tokens += sum(llm_output.get("response_tokens", []))
            if llm_output.get("openai_responses"):
                self.successful_adaptations += 1
                
        except Exception as e:
            logger.error(f"LLM适配过程发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            context.update_data("llm_output", {"error": str(e)})
        
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