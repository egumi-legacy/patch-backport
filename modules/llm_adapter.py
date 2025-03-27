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
import tempfile
import shutil
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
            # 优先使用chunk_analyzer模块优化后的补丁路径
            # if hasattr(context.commit, 'optimized_patch_path') and context.commit.optimized_patch_path.exists():
            #     patch_path = context.commit.optimized_patch_path
            #     logger.info(f"使用优化后的补丁文件: {patch_path}")
            # else:
            #     patch_path = context.commit.patch_path
            #     logger.info(f"使用原始补丁文件: {patch_path}")
            logger.info(f"context.commit.patch_path: {context.commit.patch_path}")
            patch_path = Path(context.commit.patch_path)
            logger.info(f"使用原始补丁文件: {patch_path}")
                
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
        
        # 检查是否使用增强提示模式（函数级上下文）
        use_enhanced_prompt = context.config.module_configs.get('llm_adapter', {}).get('use_enhanced_prompt', False)
        
        if use_enhanced_prompt:
            # 使用函数级上下文和完整文件内容的增强模式
            logger.info("使用函数级上下文和完整文件内容的增强模式") #1.PATCH CHUNK 函数上下文 2.旧版本完整文件
            prompt_data = self._prepare_enhanced_prompt(context, patch_content)
        else:
            # 获取传统的上下文差异
            logger.info("使用传统上下文差异") #1.PATCH 2.DIFF
            context_diff = self._get_context_diff(context, patch_content)
            
            # 构建标准提示数据
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
    
    def _prepare_enhanced_prompt(self, context: ModuleContext, patch_content: str) -> Dict[str, Any]:
        """
        准备增强的LLM输入数据，包括:
        1. 函数级上下文（从新版本提取修改区块所在的函数）
        2. 旧版本的完整文件
        
        :param context: 模块上下文
        :param patch_content: 原始补丁内容
        :return: 增强的提示数据字典
        """
        repo_path = context.config.repo_path
        
        # 从补丁中提取修改的文件
        modified_files = self._extract_affected_files(patch_content)
        logger.info(f"补丁修改的文件: {modified_files}")
        
        # 为每个修改的文件收集信息
        file_contexts = []
        
        for file_path in modified_files:
            try:
                # 获取修改块的信息
                chunks_info = self._extract_chunk_info(patch_content, file_path)
                
                # 获取新版本的文件（如果存在于本地仓库）
                new_file_content = self._get_file_content_from_upstream(context, file_path)
                
                # 获取旧版本(目标版本)的文件内容
                old_file_content = self._get_file_content_from_target(context, file_path)
                
                # 为每个修改块获取函数级上下文
                function_contexts = []
                if new_file_content:
                    for chunk in chunks_info:
                        func_context = self._extract_function_context(new_file_content, chunk['start_line'], chunk['end_line'])
                        if func_context:
                            function_contexts.append({
                                'lines': f"{chunk['start_line']}-{chunk['end_line']}",
                                'context': func_context
                            })
                
                file_contexts.append({
                    'file_path': file_path,
                    'chunks': chunks_info,
                    'function_contexts': function_contexts,
                    'old_file_content': old_file_content,
                    'exists_in_old_version': old_file_content is not None
                })
                
            except Exception as e:
                logger.error(f"处理文件 {file_path} 时出错: {e}")
                logger.error(traceback.format_exc())
        
        # 构建增强的提示数据
        enhanced_prompt = {
            'patch_content': patch_content,
            'target_version': context.config.target_version,
            'context_diff': self._get_context_diff(context, patch_content),  # 仍然保留传统差异以供参考
            'modified_files': file_contexts,
            'feedback_instruction': '',
            'enhanced_prompt': True
        }
        
        return enhanced_prompt
    
    def _extract_chunk_info(self, patch_content: str, file_path: str) -> List[Dict[str, Any]]:
        """
        从补丁内容中提取特定文件的修改块信息
        
        :param patch_content: 补丁内容
        :param file_path: 文件路径
        :return: 包含修改块信息的列表
        """
        chunks = []
        
        # 找到特定文件的差异部分
        file_diff_pattern = re.compile(r'diff --git a/' + re.escape(file_path) + r' b/' + re.escape(file_path) + r'.*?(?=diff --git|\Z)', re.DOTALL)
        file_diff_match = file_diff_pattern.search(patch_content)
        
        if not file_diff_match:
            logger.warning(f"未找到文件 {file_path} 的差异部分")
            return chunks
        
        file_diff = file_diff_match.group(0)
        
        # 查找所有的@@行，这些行标记了修改块的开始
        hunk_header_pattern = re.compile(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
        for match in hunk_header_pattern.finditer(file_diff):
            old_start = int(match.group(1))
            old_count = int(match.group(2) or 1)
            new_start = int(match.group(3))
            new_count = int(match.group(4) or 1)
            
            # 获取当前块的结束位置
            start_pos = match.end()
            next_match = hunk_header_pattern.search(file_diff, start_pos)
            end_pos = next_match.start() if next_match else len(file_diff)
            
            # 提取当前块内容
            chunk_content = file_diff[start_pos:end_pos]
            
            chunks.append({
                'start_line': new_start,
                'end_line': new_start + new_count - 1,
                'old_start': old_start,
                'old_end': old_start + old_count - 1,
                'content': chunk_content.strip()
            })
        
        return chunks
    
    def _get_file_content_from_upstream(self, context: ModuleContext, file_path: str) -> Optional[str]:
        """
        获取文件在上游(新版本)的内容
        
        :param context: 模块上下文
        :param file_path: 文件路径
        :return: 文件内容，如果文件不存在则返回None
        """
        try:
            # 可以尝试直接从GitHub API获取，或者从本地仓库获取
            # 这里先实现从本地仓库获取的方法
            repo_path = context.config.repo_path
            
            # 获取当前分支
            current_branch = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()
            
            # 创建临时分支来获取最新版本的文件
            temp_branch = f"temp_upstream_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            try:
                # 创建临时分支指向最新的主分支或者特定的上游分支
                # 这里假设'origin/master'是最新的上游分支
                upstream_branch = context.config.module_configs.get('llm_adapter', {}).get('upstream_branch', 'origin/master')
                
                # 尝试创建临时分支
                subprocess.run(
                    ['git', 'checkout', '-b', temp_branch, upstream_branch],
                    cwd=repo_path,
                    capture_output=True,
                    check=True
                )
                
                # 检查文件是否存在
                full_path = os.path.join(repo_path, file_path)
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    return content
                else:
                    logger.warning(f"文件 {file_path} 在上游分支 {upstream_branch} 中不存在")
                    return None
                    
            finally:
                # 切回原始分支
                subprocess.run(
                    ['git', 'checkout', current_branch],
                    cwd=repo_path,
                    capture_output=True,
                    check=True
                )
                
                # 删除临时分支
                subprocess.run(
                    ['git', 'branch', '-D', temp_branch],
                    cwd=repo_path,
                    capture_output=True,
                    check=False  # 忽略错误
                )
                
        except Exception as e:
            logger.error(f"获取上游文件内容时出错: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _get_file_content_from_target(self, context: ModuleContext, file_path: str) -> Optional[str]:
        """
        获取文件在目标版本(旧版本)的内容
        
        :param context: 模块上下文
        :param file_path: 文件路径
        :return: 文件内容，如果文件不存在则返回None
        """
        try:
            repo_path = context.config.repo_path
            target_version = context.config.target_version
            
            # 获取当前分支
            current_branch = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()
            
            # 创建临时分支
            temp_branch = f"temp_target_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            try:
                # 创建临时分支指向目标版本
                subprocess.run(
                    ['git', 'checkout', '-b', temp_branch, target_version],
                    cwd=repo_path,
                    capture_output=True,
                    check=True
                )
                
                # 文件可能在旧版本中有不同的路径，尝试使用backtrack_apply模块中的映射逻辑
                try:
                    from modules.backtrack_apply import BacktrackApplyModule
                    backtrack_module = BacktrackApplyModule(context.config)
                    path_mapping = backtrack_module._map_file_paths(repo_path, [file_path])
                    mapped_path = path_mapping.get(file_path, file_path)
                except ImportError:
                    # 如果无法导入，就使用原路径
                    mapped_path = file_path
                    
                # 检查文件是否存在
                full_path = os.path.join(repo_path, mapped_path)
                if os.path.exists(full_path):
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    return content
                else:
                    logger.warning(f"文件 {mapped_path} 在目标版本 {target_version} 中不存在")
                    return None
                    
            finally:
                # 切回原始分支
                subprocess.run(
                    ['git', 'checkout', current_branch],
                    cwd=repo_path,
                    capture_output=True,
                    check=True
                )
                
                # 删除临时分支
                subprocess.run(
                    ['git', 'branch', '-D', temp_branch],
                    cwd=repo_path,
                    capture_output=True,
                    check=False  # 忽略错误
                )
                
        except Exception as e:
            logger.error(f"获取目标版本文件内容时出错: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _extract_function_context(self, file_content: str, start_line: int, end_line: int) -> Optional[str]:
        """
        提取修改区块所在的函数级上下文
        
        :param file_content: 文件内容
        :param start_line: 修改开始行
        :param end_line: 修改结束行
        :return: 函数上下文，如果无法确定则返回None
        """
        try:
            lines = file_content.split('\n')
            
            # 安全检查
            if start_line < 1 or start_line > len(lines) or end_line < 1 or end_line > len(lines):
                logger.warning(f"行号超出范围: {start_line}-{end_line}，文件总行数: {len(lines)}")
                return None
            
            # 向上查找函数开始（如 "void function_name(" 或 "int function_name{"）
            function_start = start_line - 1
            # 常见函数标记的正则表达式
            function_start_pattern = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(')
            while function_start > 0:
                if function_start_pattern.match(lines[function_start - 1].strip()):
                    break
                if '{' in lines[function_start - 1] and '}' not in lines[function_start - 1]:
                    # 可能找到了函数开始
                    break
                function_start -= 1
                
                # 防止无限循环或搜索过远
                if start_line - function_start > 50:  # 最多向上查找50行
                    function_start = max(1, start_line - 10)  # 如果找不到，就取前10行作为上下文
                    break
            
            # 向下查找函数结束（如 "}" 单独一行）
            function_end = end_line - 1
            # 常见函数结束的正则表达式
            function_end_pattern = re.compile(r'^\s*}\s*$')
            nesting_level = 0
            while function_end < len(lines) - 1:
                line = lines[function_end]
                # 计算大括号嵌套层级
                nesting_level += line.count('{') - line.count('}')
                
                if nesting_level <= 0 and function_end_pattern.match(lines[function_end + 1]):
                    function_end += 1  # 包含结束的大括号
                    break
                    
                function_end += 1
                
                # 防止无限循环或搜索过远
                if function_end - end_line > 100:  # 最多向下查找100行
                    function_end = min(len(lines) - 1, end_line + 20)  # 如果找不到，就取后20行作为上下文
                    break
            
            # 截取函数上下文
            max_context_lines = 500  # 防止函数过长，限制最大行数
            if function_end - function_start > max_context_lines:
                # 如果函数太长，只取修改点周围的代码
                context_start = max(function_start, start_line - max_context_lines // 4)
                context_end = min(function_end, end_line + max_context_lines // 4)
                
                context_lines = lines[context_start:context_end + 1]
                return f"// 函数过长，只显示部分内容（行 {context_start+1} 到 {context_end+1}）...\n" + '\n'.join(context_lines)
            else:
                # 返回完整函数
                return '\n'.join(lines[function_start:function_end + 1])
                
        except Exception as e:
            logger.error(f"提取函数上下文时出错: {e}")
            logger.error(traceback.format_exc())
            # 如果出错，返回行周围的几行作为简单上下文
            try:
                context_start = max(0, start_line - 5 - 1)  # -1是因为行号从1开始，数组从0开始
                context_end = min(len(file_content.split('\n')) - 1, end_line + 5 - 1)
                return '\n'.join(file_content.split('\n')[context_start:context_end + 1])
            except:
                return None
    
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
                logger.info("="*10)
                logger.info(f"patch_processor result: {result}")
                logger.info("="*10)
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
        
        # 检查是否有完整文件模式标记
        full_file_pattern = r"```(?:complete_file|file):(.*?)\n([\s\S]*?)\n```"
        full_file_matches = re.findall(full_file_pattern, response)
        
        if full_file_matches:
            # 找到了完整文件格式，转换为补丁格式
            logger.info(f"检测到完整文件响应，文件数量: {len(full_file_matches)}")
            patch_content = self._convert_files_to_patch(full_file_matches)
            if patch_content:
                return patch_content
        
        # 默认处理方法 - 查找补丁块
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
    
    def _convert_files_to_patch(self, file_matches: List[tuple]) -> Optional[str]:
        """
        将完整文件内容转换为补丁格式
        
        :param file_matches: 文件匹配结果列表，每项是(文件路径, 文件内容)的元组
        :return: 生成的补丁内容，失败则返回None
        """
        try:
            # 创建临时目录
            temp_dir = Path(tempfile.mkdtemp())
            logger.info(f"创建临时目录: {temp_dir}")
            
            # 获取仓库信息
            repo_name = "unknown_repo"
            if hasattr(self, 'config') and hasattr(self.config, 'repo_name'):
                repo_name = self.config.repo_name
            
            # 创建补丁头部
            patch_header = f"""From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: LLM Adapter <llm@example.com>
Date: {datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')}
Subject: [PATCH] Backported changes by LLM

Generated patch from complete file responses
"""

            patch_content = [patch_header]
            
            for file_path, content in file_matches:
                file_path = file_path.strip()
                
                # 创建临时文件目录结构
                file_dir = temp_dir / "original" / Path(file_path).parent
                file_dir.mkdir(parents=True, exist_ok=True)
                
                # 获取原始文件内容
                original_content = ""
                try:
                    # 尝试从目标版本获取原始文件
                    original_file_path = Path(self.config.repo_path) / file_path
                    if original_file_path.exists():
                        with open(original_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            original_content = f.read()
                except:
                    logger.warning(f"无法获取文件 {file_path} 的原始内容")
                
                # 写入原始文件
                with open(temp_dir / "original" / file_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                
                # 写入新文件
                new_file_dir = temp_dir / "modified" / Path(file_path).parent
                new_file_dir.mkdir(parents=True, exist_ok=True)
                with open(temp_dir / "modified" / file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # 使用diff生成补丁
                try:
                    diff_result = subprocess.run(
                        ['diff', '-u', 
                         str(temp_dir / "original" / file_path), 
                         str(temp_dir / "modified" / file_path)],
                        capture_output=True,
                        text=True
                    )
                    
                    # diff命令返回1表示文件有差异，这是正常的
                    if diff_result.returncode not in [0, 1]:
                        logger.warning(f"生成diff时出错: {diff_result.stderr}")
                        continue
                        
                    file_diff = diff_result.stdout
                    
                    # 转换为git格式的补丁
                    if file_diff:
                        # 替换diff头部
                        git_diff = f"diff --git a/{file_path} b/{file_path}\n"
                        git_diff += f"--- a/{file_path}\n"
                        git_diff += f"+++ b/{file_path}\n"
                        
                        # 添加剩余的diff内容（跳过前两行）
                        diff_lines = file_diff.split('\n')[2:]  # 跳过 --- +++ 行
                        git_diff += '\n'.join(diff_lines)
                        
                        patch_content.append(git_diff)
                        
                except Exception as diff_error:
                    logger.error(f"生成文件 {file_path} 的diff时出错: {diff_error}")
            
            # 清理临时目录
            shutil.rmtree(temp_dir)
            
            # 如果没有生成任何差异，返回None
            if len(patch_content) <= 1:  # 只有头部，没有实际diff
                logger.warning("未生成任何差异，无法创建补丁")
                return None
                
            # 合并补丁内容
            return '\n\n'.join(patch_content)
            
        except Exception as e:
            logger.error(f"转换文件到补丁格式时出错: {e}")
            logger.error(traceback.format_exc())
            return None
    
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
