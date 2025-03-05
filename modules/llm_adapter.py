# from typing import Dict, Any
# from loguru import logger
# from .base_module import BaseModule, ModuleType, ModuleContext
# from llm_assistant import LLMAssistant
# from patch_processor import PatchProcessor
# from config_manager import ProjectConfig
# from pathlib import Path
# import pprint

from typing import Dict, Any, Optional, List
from pathlib import Path
from loguru import logger
import json
import os
import re
import subprocess
import traceback
import html
from datetime import datetime
import requests
from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext
from llm_assistant import LLMAssistant
from patch_processor import PatchProcessor

class LLMAdapterModule(BaseModule):
    """LLM补丁适配模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.LLM_ADAPTER
        self.name = "llm_adapter"
        self.prompt_template = self._load_prompt_template()
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行LLM补丁适配"""
        if not self._should_run(context):
            return context
            
        start_time = datetime.now()
        
        try:
            # 检查是否是反馈重试
            is_retry = context.config.retry_with_feedback and context.retry_count > 0 and context.feedback_data
            
            # 获取补丁文件路径
            patch_path = context.commit.patch_path
            if not patch_path.exists():
                raise ValueError("没有找到补丁文件路径")

            # context.commit.patch_path = patch_path
            # 准备LLM输入内容
            prompt_data = self._prepare_prompt_data(context, is_retry)
            # logger.info(f"prompt_data:{prompt_data}")
            
            # 调用LLM 保存原始LLM响应到context
            context.llm_output = self._call_llm(prompt_data, context)
            
            # 解析LLM响应
            parsed_response = self._parse_llm_response(context.llm_output)
            
            # 保存LLM响应
            response_path = self._save_llm_response(context, parsed_response)
            
            # # 测试LLM生成的补丁是否可以应用
            # apply_result = self._test_patch_apply(context, response_path)
            
            # 更新上下文
            context.llm_output = {
                'status': 'success',
                'content': parsed_response,
                'prompt': prompt_data,
                'response_path': str(response_path),
                # 'apply_result': apply_result,
                'timestamp': datetime.now().isoformat(),
                'retry_count': context.retry_count
            }
            
            # 更新指标
            self._update_metrics(
                success=True,
                execution_time=(datetime.now() - start_time).total_seconds(),
                # apply_success=apply_result.get('success', False),
                # apply_error=apply_result.get('error')
            )
            
        except Exception as e:
            logger.error(f"LLM处理过程发生错误: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            context.llm_output = {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            context.last_error = str(e)
            
            # 更新指标
            self._update_metrics(
                success=False,
                error_type='exception',
                execution_time=(datetime.now() - start_time).total_seconds()
            )
        
        # 保存指标
        self._save_metrics(context)
        
        return context
    
    def _load_prompt_template(self) -> str:
        """加载提示模板"""
        template_file = Path("configs") / "test_prompts.json"
        if not template_file.exists():
            raise FileNotFoundError(f"提示模板文件不存在: {template_file}")
        with open(template_file, 'r', encoding='utf-8') as f:
            return json.load(f)
        # if not template_path.exists():
        #     # 如果未找到，创建默认模板
        #     default_template = """
        #     你是一个经验丰富的Linux内核开发人员，帮助我将补丁从一个版本移植到另一个版本。
            
        #     原始补丁:
        #     ```
        #     {patch_content}
        #     ```
            
        #     目标版本: {target_version}
            
        #     上下文差异:
        #     ```
        #     {context_diff}
        #     ```
            
        #     请生成适用于目标版本的补丁，保持与原始补丁相同的意图和功能。
        #     输出格式应该与git format-patch格式相符。
            
        #     {feedback_instruction}
        #     """
            
        #     # 确保目录存在
        #     template_path.parent.mkdir(parents=True, exist_ok=True)
            
        #     # 写入默认模板
        #     with open(template_path, 'w') as f:
        #         f.write(default_template.strip())
            
        #     logger.info(f"已创建默认提示模板: {template_path}")
        
        # # 读取模板
        # with open(template_path, 'r') as f:
        #     template = f.read()
            
        # return template
    
    def _prepare_prompt_data(self, context: ModuleContext, is_retry: bool = False) -> Dict[str, Any]:
        """准备LLM输入数据"""
        # 读取补丁内容
        with open(context.commit.patch_path, 'r') as f:
            patch_content = f.read()
        
        # 获取上下文差异
        context_diff = self._get_context_diff(context, patch_content)
        
        # 构建提示数据
        prompt_data = {
            'patch_content': patch_content,
            'target_version': context.config.target_version,
            'context_diff': context_diff,
            'feedback_instruction': ''
        }
        
        # 如果是重试，添加反馈信息
        if is_retry and context.feedback_data:
            error_log = context.feedback_data.get('error_log', '')
            prompt_data['feedback_instruction'] = f"""
            前一次尝试编译失败，错误日志如下:
            ```
            {error_log}
            ```
            
            请根据错误信息修改补丁。
            """
        
        return prompt_data
    
    def _get_context_diff(self, context: ModuleContext, patch_content: str) -> str:
        """获取上下文差异"""
        try:
            # 从commit目录中直接读取diff文件
            diff_file = context.commit.base_dir / 'diff'
            if diff_file.exists():
                return html.unescape(diff_file.read_text())
                
            # 如果diff文件不存在，直接使用PatchProcessor的功能来获取差异
            from patch_processor import PatchProcessor
            
            # 修复commit_info中可能存在的.patch后缀问题
            if hasattr(context.commit, 'patch_url') and context.commit.patch_url.endswith('.patch'):
                # 移除.patch后缀
                context.commit.patch_url = context.commit.patch_url.replace('.patch', '')
                logger.info(f"修正URL格式，移除.patch后缀: {context.commit.patch_url}")
            
            # 初始化PatchProcessor，使用ModuleContext中的参数
            patch_processor = PatchProcessor(context)
            
            # 确保commit_info中的commit_sha不包含.patch后缀
            if hasattr(patch_processor, 'commit_info') and 'commit_sha' in patch_processor.commit_info:
                if patch_processor.commit_info['commit_sha'].endswith('.patch'):
                    patch_processor.commit_info['commit_sha'] = patch_processor.commit_info['commit_sha'].replace('.patch', '')
                    logger.info(f"修正commit_sha，移除.patch后缀: {patch_processor.commit_info['commit_sha']}")
            
            # 运行patch_processor生成diff文件
            try:
                result = patch_processor.run()
                
                # 读取生成的diff文件
                if diff_file.exists():
                    return html.unescape(diff_file.read_text())
                elif "prompt_values" in result and result["prompt_values"]:
                    return result["prompt_values"][0]["diffCode"]
                else:
                    raise ValueError("无法获取diff内容")
            except Exception as inner_e:
                logger.error(f"执行patch_processor失败: {inner_e}")
                # 尝试回退到替代方法
                if hasattr(context.commit, 'patch_path'):
                    patch_path = context.commit.patch_path
                    # 确保patch_path是Path对象
                    if isinstance(patch_path, str):
                        patch_path = Path(patch_path)
                    
                    if patch_path.exists():
                        logger.info("使用patch文件作为diff内容")
                        return patch_path.read_text()
                # 尝试直接使用patch_content作为diff
                return patch_content
                
        except Exception as e:
            logger.error(f"获取上下文差异失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            # 在错误情况下，直接使用patch_content作为diff
            return f"获取上下文差异时出错，使用patch内容作为差异：\n{patch_content}"
    
    def _extract_affected_files(self, patch_content: str) -> List[str]:
        """从补丁内容中提取受影响的文件"""
        affected_files = []
        
        # 使用正则表达式提取 "diff --git a/path/to/file b/path/to/file" 中的文件路径
        pattern = r"diff --git a/(.*?) b/"
        matches = re.findall(pattern, patch_content)
        
        for match in matches:
            if match not in affected_files:
                affected_files.append(match)
        
        return affected_files
    
    def _call_llm(self, prompt_data: Dict[str, Any], context: ModuleContext) -> str:
        """调用LLM模型"""
        # 创建ModuleContext对象供LLMAssistant使用
        # llm_context = ModuleContext(
        #     config=context.config,
        #     commit=context.commit  # 保持原有的commit信息
        # )
        
        # # 获取backport模板
        # template = None
        # for t in self.prompt_template:
        #     if t['id'] == config.prompt_id:
        #         template = t
        #         break
        
        # if not template:
        #     raise ValueError(f"未找到{config.prompt_id}提示模板")
        
        # 配置LLMAssistant所需的参数
        llm_config = {
            # 'model': context.config.model,
            # 'response_file': context.config.response_file,
            # 'prompt_template_file': context.config.prompt_template_file,
            # 'prompt_id': context.config.prompt_id,
            'extra_config': {
                'prompt_values': [{
                    'patchCode': prompt_data['patch_content'],
                    'diffCode': prompt_data['context_diff']
                }]
            }
        }
        # 创建新的ModuleContext，使用原始配置并添加新的配置
        llm_context = ModuleContext(
            config=context.config.model_copy(update=llm_config),  # 使用pydantic的model_copy方法
            commit=context.commit
        )
        # 更新context的config
        # context.config.update(llm_config)
        
        # 初始化LLMAssistant
        llm = LLMAssistant(llm_context)
        # 直接设置prompts，避免重复加载模板文件
        # llm.prompts = template['prompts']
        
        try:
            # 调用run方法获取结果
            result = llm.run()
            logger.info(f"llm.run() result:{result}")
            
            if not result or not result.get('openai_responses'):
                raise ValueError("LLM未返回有效响应")
                
            # 返回第一个响应
            return result['openai_responses'][0]
            
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            raise
        
        # # 根据配置选择模型和参数
        # model = config.model
        # temperature = getattr(config, 'temperature', 0.7)
        # max_tokens = getattr(config, 'max_tokens', 4096)
        
        # # 调用OpenAI API (示例)
        # if model.startswith('gpt'):
        #     try:
        #         import openai
        #         openai.api_key = os.environ.get("OPENAI_API_KEY")
                
        #         response = openai.ChatCompletion.create(
        #             model=model,
        #             messages=[
        #                 {"role": "system", "content": "你是一个经验丰富的Linux内核开发人员，帮助适配补丁。"},
        #                 {"role": "user", "content": prompt}
        #             ],
        #             temperature=temperature,
        #             max_tokens=max_tokens
        #         )
                
        #         return response.choices[0].message['content']
                
        #     except ImportError:
        #         logger.error("未安装OpenAI库，无法调用GPT模型")
        #         raise ValueError("未安装OpenAI库，无法调用GPT模型")
        #     except Exception as e:
        #         logger.error(f"调用OpenAI API失败: {e}")
        #         raise
        
        # # 调用Claude API (示例)
        # elif model.startswith('claude'):
        #     try:
        #         import anthropic
        #         api_key = os.environ.get("ANTHROPIC_API_KEY")
                
        #         client = anthropic.Client(api_key=api_key)
        #         response = client.messages.create(
        #             model=model,
        #             system="你是一个经验丰富的Linux内核开发人员，帮助适配补丁。",
        #             messages=[{"role": "user", "content": prompt}],
        #             temperature=temperature,
        #             max_tokens=max_tokens
        #         )
                
        #         return response.content[0].text
                
        #     except ImportError:
        #         logger.error("未安装Anthropic库，无法调用Claude模型")
        #         raise ValueError("未安装Anthropic库，无法调用Claude模型")
        #     except Exception as e:
        #         logger.error(f"调用Anthropic API失败: {e}")
        #         raise
        
        # # 本地模型 (示例)
        # elif model.startswith('local'):
        #     try:
        #         # TODO: 实现本地模型调用逻辑
        #         return "此处需要实现本地模型调用逻辑"
        #     except Exception as e:
        #         logger.error(f"调用本地模型失败: {e}")
        #         raise
        
        # else:
        #     logger.error(f"未支持的模型: {model}")
        #     raise ValueError(f"未支持的模型: {model}")
    
    def _parse_llm_response(self, response: str) -> str:
        """解析LLM响应"""
        # 记录原始响应前100个字符，方便调试
        logger.info(f"原始LLM响应(前100字符): {response[:100]}...")
        
        # 提取格式化补丁内容
        patch_pattern = r"```(?:diff|patch)?\n([\s\S]*?)\n```"
        matches = re.findall(patch_pattern, response)
        
        if matches:
            logger.info(f"找到格式化补丁块，内容前100字符: {matches[0][:100]}...")
            return matches[0]
        else:
            # 如果没有找到明确的补丁块，尝试查找git format的开头
            git_header_pattern = r"(From [a-f0-9]+ [\s\S]*)"
            header_matches = re.findall(git_header_pattern, response)
            
            if header_matches:
                logger.info(f"找到git format头部，内容前100字符: {header_matches[0][:100]}...")
                return header_matches[0]
            
            # 查找diff --git开头的内容
            diff_pattern = r"(diff --git [\s\S]*)"
            diff_matches = re.findall(diff_pattern, response)
            
            if diff_matches:
                logger.info(f"找到diff --git格式，内容前100字符: {diff_matches[0][:100]}...")
                return diff_matches[0]
            
            # 如果都没找到，返回整个响应
            logger.warning("未找到任何已知补丁格式，返回完整响应")
            return response
    
    def _save_llm_response(self, context: ModuleContext, response: str) -> Path:
        """保存LLM响应到文件"""
        # 创建目录
        llm_dir = context.commit.base_dir / "llm_output"
        llm_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        if context.config.retry_with_feedback:
            retry_suffix = f"_retry{context.retry_count}" if context.retry_count > 0 else ""
            filename = f"output_{context.config.target_version}_{context.config.model}_{retry_suffix}.patch"
        else:
            filename = f"output_{context.config.target_version}_{context.config.model}.patch"
        
        # 保存响应
        response_path = llm_dir / filename
        with open(response_path, 'w') as f:
            f.write(response)
        
        # 同时保存原始响应便于调试
        raw_response_path = llm_dir / f"raw_{filename}"
        with open(raw_response_path, 'w') as f:
            f.write(context.llm_output if hasattr(context, 'llm_output') else "")
        
        logger.info(f"LLM响应已保存到: {response_path}")
        logger.info(f"原始LLM响应已保存到: {raw_response_path}")
        return response_path

    def _test_patch_apply(self, context: ModuleContext, patch_path: Path) -> Dict[str, Any]:
        """测试LLM生成的补丁是否能应用到目标分支"""
        result = {
            'success': False,
            'error': None,
            'error_type': None,
            'output': None,
        }
        
        # 创建测试分支名
        branch_name = f"test_llm_patch_{context.config.target_version}"
        
        try:
            # 准备测试分支
            branch_created = self._prepare_test_branch(context, branch_name)
            if not branch_created:
                result['error'] = f"创建测试分支失败: {branch_name}"
                result['error_type'] = 'branch_creation_failed'
                return result
            
            # 应用补丁
            return self._apply_patch(context, patch_path, branch_name)
        except Exception as e:
            result['error'] = str(e)
            result['error_type'] = 'exception'
            logger.error(f"测试LLM补丁应用时发生错误: {e}")
            return result
        finally:
            # 清理测试分支
            self._cleanup_test_branch(context, branch_name)

    def _prepare_test_branch(self, context: ModuleContext, branch_name: str) -> bool:
        """准备测试分支"""
        try:
            # 获取仓库路径
            repo_path = context.config.repo_path
            
            # 首先尝试清理已存在的分支
            self._cleanup_test_branch(context, branch_name)
            
            # 切换到目标版本分支
            logger.info(f"切换到分支: {context.config.target_version}")
            subprocess.run(
                ['git', 'checkout', context.config.target_version],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            # 创建新的测试分支
            logger.info(f"创建测试分支: {branch_name}")
            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"准备测试分支失败: {e.stderr if hasattr(e, 'stderr') else str(e)}")
            return False
        except Exception as e:
            logger.error(f"准备测试分支时发生错误: {e}")
            return False

    def _apply_patch(self, context: ModuleContext, patch_path: Path, branch_name: str) -> Dict[str, Any]:
        """应用补丁到测试分支"""
        result = {
            'success': False,
            'error': None,
            'error_type': None,
            'output': None,
        }

        try:
            # 确保使用绝对路径
            absolute_patch_path = patch_path.absolute()
            
            # 验证文件存在
            if not absolute_patch_path.exists():
                logger.error(f"补丁文件不存在: {absolute_patch_path}")
                result['error'] = f"补丁文件不存在: {absolute_patch_path}"
                result['error_type'] = 'file_not_found'
                return result

            apply_process = subprocess.run(
                ['git', 'am', str(absolute_patch_path)],
                cwd=context.config.repo_path,
                capture_output=True,
                text=True
            )
            
            if apply_process.returncode == 0:
                result['success'] = True
                result['output'] = apply_process.stdout
                logger.info(f"LLM补丁应用成功: {patch_path}")
            else:
                result['error'] = apply_process.stderr
                result['error_type'] = self._categorize_error(apply_process.stderr)
                logger.error(f"LLM补丁应用失败: {result['error']}")

            return result
        except Exception as e:
            result['error'] = str(e)
            result['error_type'] = 'exception'
            logger.error(f"应用LLM补丁时发生错误: {e}")
            return result
        finally:
            # 无论成功与否，都清理git am状态
            subprocess.run(['git', 'am', '--abort'], 
                           cwd=context.config.repo_path, 
                           capture_output=True,
                           text=True)

    def _cleanup_test_branch(self, context: ModuleContext, branch_name: str) -> None:
        """清理测试分支"""
        try:
            repo_path = context.config.repo_path
            
            # 检查分支是否存在
            branches = subprocess.run(
                ['git', 'branch'],
                cwd=repo_path,
                check=False,
                capture_output=True,
                text=True
            ).stdout
            
            if branch_name in branches:
                logger.info(f"清理测试分支: {branch_name}")
                
                # 先切换到master或main分支
                default_branches = ['master', 'main']
                for default_branch in default_branches:
                    try:
                        subprocess.run(
                            ['git', 'checkout', default_branch],
                            cwd=repo_path,
                            check=True,
                            capture_output=True,
                            text=True
                        )
                        break
                    except:
                        continue
                
                # 删除测试分支
                subprocess.run(
                    ['git', 'branch', '-D', branch_name],
                    cwd=repo_path,
                    check=False,
                    capture_output=True,
                    text=True
                )
        except Exception as e:
            logger.error(f"清理测试分支失败: {e}")

    def _categorize_error(self, error_message: str) -> str:
        """分类错误类型"""
        if 'patch does not apply' in error_message:
            return 'patch_conflict'
        elif 'permission denied' in error_message.lower():
            return 'permission_error'
        elif 'fatal: not a git repository' in error_message:
            return 'not_git_repo'
        else:
            return 'other'

    def _update_metrics(self, **kwargs):
        """更新指标"""
        # 先调用父类方法处理基本指标
        super()._update_metrics(
            success=kwargs.get('success', False),
            error_type=kwargs.get('error_type'),
            execution_time=kwargs.get('execution_time', 0)
        )
        
        # 特别记录补丁应用结果
        if 'apply_success' in kwargs:
            self.metrics['apply_success'] = kwargs['apply_success']
        if 'apply_error' in kwargs and kwargs['apply_error']:
            if 'apply_errors' not in self.metrics:
                self.metrics['apply_errors'] = []
            # 记录应用错误，但限制长度
            error_summary = kwargs['apply_error'][:200] + "..." if len(kwargs['apply_error']) > 200 else kwargs['apply_error']
            self.metrics['apply_errors'].append(error_summary)
