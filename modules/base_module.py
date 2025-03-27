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
        # 示例实现:
        # start_time = datetime.now()
        # 
        # try:
        #     # 处理逻辑
        #     ...
        #     
        #     # 更新指标
        #     self._update_metrics(
        #         success=True,
        #         execution_time=(datetime.now() - start_time).total_seconds()
        #     )
        # except Exception as e:
        #     # 错误处理
        #     ...
        #     
        #     # 更新指标
        #     self._update_metrics(
        #         success=False,
        #         error_type='exception',
        #         execution_time=(datetime.now() - start_time).total_seconds()
        #     )
        # 
        # # 保存指标和评估信息
        # self._save_metrics(context)
        # self._save_evaluation_info(context)
        # 
        # return context
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
            if not context.patch_adapter_result['success']:
                logger.info("适配补丁失败，跳过编译")
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
        
    def _save_evaluation_info(self, context: ModuleContext):
        """
        保存美观易读的输入/输出评估信息，用于单元测试和调试
        这是基础方法，子类可扩展此方法添加特定的评估信息
        
        生成的评估信息包含:
        1. 基本模块信息（名称、类型、执行时间等）
        2. 输入参数信息
        3. 输出结果摘要
        4. HTML格式的可视化报告
        """
        try:
            # 获取评估目录路径
            eval_dir = context.base_dir / "evaluations" / self.name
            eval_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建详细评估信息目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            commit_sha = context.commit.commit_sha[:6]
            details_dir = eval_dir / f"details_{commit_sha}_{timestamp}"
            details_dir.mkdir(parents=True, exist_ok=True)
            
            # 基本评估信息
            evaluation_info = {
                "模块信息": {
                    "模块名称": self.name,
                    "模块类型": str(self.type) if self.type else "未知",
                    "提交SHA": context.commit.commit_sha,
                    "目标版本": context.config.target_version,
                    "执行时间": datetime.now().isoformat()
                },
                "输入信息": self._collect_input_info(context),
                "输出信息": self._collect_output_info(context)
            }
            
            # 保存评估信息摘要
            summary_file = details_dir / "summary.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(evaluation_info, f, indent=2, ensure_ascii=False)
            
            # 创建README文件
            self._generate_readme(details_dir, context, evaluation_info)
            
            # 生成HTML报告
            self._generate_html_report(details_dir, context, evaluation_info)
            
            logger.info(f"美观易读的评估信息已保存到: {details_dir}")
            
        except Exception as e:
            logger.error(f"保存评估信息失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    def _collect_input_info(self, context: ModuleContext) -> Dict[str, Any]:
        """
        收集输入信息，子类可覆盖以添加特定信息
        """
        return {
            "原始补丁路径": str(context.commit.patch_path) if hasattr(context.commit, "patch_path") else "未知",
            "代码仓库路径": str(context.config.repo_path) if hasattr(context.config, "repo_path") else "未知"
        }
    
    def _collect_output_info(self, context: ModuleContext) -> Dict[str, Any]:
        """
        收集输出信息，子类必须覆盖以提供模块特定的输出
        """
        return {
            "状态": "成功" if self.metrics['successful_executions'] > 0 else "失败",
            "成功次数": self.metrics['successful_executions'],
            "总尝试次数": self.metrics['total_attempts'],
            "执行时间": self.metrics['execution_time']
        }
    
    def _generate_readme(self, details_dir: Path, context: ModuleContext, evaluation_info: Dict[str, Any]):
        """
        生成评估信息的README文件，子类可覆盖以添加特定内容
        """
        readme_file = details_dir / "README.md"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(f"# {self.name} 模块评估信息\n\n")
            
            # 基本信息
            f.write(f"## 基本信息\n\n")
            f.write(f"- 模块名称: {self.name}\n")
            f.write(f"- 模块类型: {self.type}\n")
            f.write(f"- 提交SHA: {context.commit.commit_sha}\n")
            f.write(f"- 目标版本: {context.config.target_version}\n")
            f.write(f"- 执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # 处理结果
            f.write(f"## 处理结果\n\n")
            output_info = evaluation_info.get("输出信息", {})
            for key, value in output_info.items():
                f.write(f"- {key}: {value}\n")
                
            # 目录说明
            f.write(f"\n## 目录内容说明\n\n")
            f.write(f"- summary.json: 评估信息摘要\n")
            f.write(f"- report.html: HTML格式评估报告\n")
    
    def _generate_html_report(self, details_dir: Path, context: ModuleContext, evaluation_info: Dict[str, Any]):
        """
        生成HTML格式的评估报告，子类可覆盖以添加特定内容
        """
        html_file = details_dir / "report.html"
        commit_sha = context.commit.commit_sha[:6]
        
        # 准备数据
        module_info = evaluation_info.get("模块信息", {})
        input_info = evaluation_info.get("输入信息", {})
        output_info = evaluation_info.get("输出信息", {})
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>{self.name} 模块评估报告 - {commit_sha}</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; color: #333; }}
    h1, h2, h3 {{ color: #2c3e50; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    .card {{ background: #fff; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; padding: 20px; }}
    .success {{ color: #27ae60; }}
    .error {{ color: #e74c3c; }}
    .info {{ color: #3498db; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
    th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #eee; }}
    th {{ background-color: #f8f9fa; }}
    tr:hover {{ background-color: #f5f5f5; }}
    pre {{ background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }}
    .progress-container {{ width: 100%; background-color: #f1f1f1; border-radius: 5px; }}
    .progress-bar {{ height: 20px; border-radius: 5px; }}
    .success-bg {{ background-color: #4CAF50; }}
    .pending-bg {{ background-color: #2196F3; }}
    .error-bg {{ background-color: #f44336; }}
    .tag {{ display: inline-block; padding: 3px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; }}
    .tag-success {{ background-color: #e8f5e9; color: #2e7d32; }}
    .tag-error {{ background-color: #ffebee; color: #c62828; }}
    .tag-pending {{ background-color: #e3f2fd; color: #1565c0; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{self.name} 模块评估报告</h1>
    
    <div class="card">
      <h2>基本信息</h2>
      <table>
        <tr>
          <td width="150"><strong>模块名称</strong></td>
          <td>{module_info.get('模块名称', '未知')}</td>
        </tr>
        <tr>
          <td><strong>模块类型</strong></td>
          <td>{module_info.get('模块类型', '未知')}</td>
        </tr>
        <tr>
          <td><strong>提交SHA</strong></td>
          <td>{module_info.get('提交SHA', '未知')}</td>
        </tr>
        <tr>
          <td><strong>目标版本</strong></td>
          <td>{module_info.get('目标版本', '未知')}</td>
        </tr>
        <tr>
          <td><strong>执行时间</strong></td>
          <td>{module_info.get('执行时间', '未知')}</td>
        </tr>
        <tr>
          <td><strong>状态</strong></td>
          <td>
            <span class="tag {
                'tag-success' if output_info.get('状态') == '成功' else 'tag-error'
            }">{output_info.get('状态', '未知')}</span>
          </td>
        </tr>
      </table>
    </div>
    
    <div class="card">
      <h2>输入信息</h2>
      <table>
        {
            ''.join([
                f'''
                <tr>
                  <td width="200"><strong>{key}</strong></td>
                  <td>{value}</td>
                </tr>
                '''
                for key, value in input_info.items()
            ])
        }
      </table>
    </div>
    
    <div class="card">
      <h2>输出信息</h2>
      <table>
        {
            ''.join([
                f'''
                <tr>
                  <td width="200"><strong>{key}</strong></td>
                  <td>{value}</td>
                </tr>
                '''
                for key, value in output_info.items()
            ])
        }
      </table>
    </div>
    
    {self._generate_additional_html_sections(context)}
    
  </div>
</body>
</html>""")
    
    def _generate_additional_html_sections(self, context: ModuleContext) -> str:
        """
        生成额外的HTML报告部分，子类可覆盖以添加特定内容
        """
        return ""  # 默认不添加额外部分