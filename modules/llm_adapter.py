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
    DEFAULT_CONTEXT_LINES = 150 # 回退机制默认上下文行数
    MAX_FUNCTION_LINES_THRESHOLD = 150 # 如果找到的函数超过此长度，则使用回退机制
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._function_context_stats = {
            'total': 0, # 总计处理的块数
            'success': 0, # 成功提取到函数上下文的次数
            'failure_reasons': {}, # 提取失败原因统计
            'fallback_triggered': 0 # 触发回退机制的次数
        }
        # 为了效率，在此处编译正则表达式
        self.py_def_pattern = re.compile(r'^\s*(async\s+)?def\s+[\w_]+\s*\([\s\S]*?\):')
        self.js_func_pattern = re.compile(r'^\s*((async\s+)?function\*?\s+[\w\$]+\s*\(|(const|let|var)\s+[\w\$]+\s*=\s*(async\s*)?(\([\s\S]*?\)|[\w\$]+)\s*=>)')
        self.java_method_pattern = re.compile(r'^\s*(public|private|protected|internal)?\s*(static|final|virtual|override)?\s*([\w\<\>\[\],\s\.\?]+\s+){1,3}[\w_]+\s*\([\s\S]*?\)\s*(\{?|throws)?') # 改进了返回类型和泛型处理
        self.generic_func_pattern = re.compile(r'^\s*([\w\<\>\[\],\s\*\&]+\s+)?[\w\~\*\&\$]+\s*\(.*?\)\s*(\{?|[^;])$', re.IGNORECASE) # 更通用，参数匹配更宽松
        self.patterns = [self.py_def_pattern, self.js_func_pattern, self.java_method_pattern, self.generic_func_pattern]

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
            
            # 输出执行摘要
            execution_time = (datetime.now() - start_time).total_seconds()
            prompt_type = "函数级别补丁" if 'function_level_patch' in prompt_data else "标准上下文差异"
            use_enhanced_prompt = context.config.module_configs.get('llm_adapter', {}).get('use_enhanced_prompt', False)
            
            logger.info("=" * 50)
            logger.info(f"LLM适配器执行完成 - 摘要")
            logger.info(f"提示模式: {'增强模式' if use_enhanced_prompt else '标准模式'}")
            logger.info(f"提示类型: {prompt_type}")
            logger.info(f"函数上下文统计: 总尝试: {self._function_context_stats['total']}, 成功: {self._function_context_stats['success']}, 回退: {self._function_context_stats['fallback_triggered']}")
            if self._function_context_stats['total'] > 0:
                success_rate = (self._function_context_stats['success'] / self._function_context_stats['total']) * 100
                logger.info(f"函数上下文提取成功率: {success_rate:.1f}%")
            logger.info(f"执行时间: {execution_time:.2f} 秒")
            logger.info(f"生成的补丁保存到: {response_path}")
            logger.info("=" * 50)
            
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
                execution_time=execution_time,
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
            
            # 输出错误摘要
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info("=" * 50)
            logger.info(f"LLM适配器执行失败 - 摘要")
            logger.info(f"错误: {str(e)}")
            logger.info(f"执行时间: {execution_time:.2f} 秒")
            logger.info("=" * 50)
            
            # 更新指标
            self._update_metrics(
                success=False,
                error_type='exception',
                execution_time=execution_time
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
        # with open(context.commit.patch_path, 'r') as f:
        #     patch_content = f.read()
        with open(context.commit.optimized_patch_path, 'r') as f:
            patch_content = f.read()
        
        # 检查是否使用增强提示模式（函数级上下文）
        use_enhanced_prompt = context.config.module_configs.get('llm_adapter', {}).get('use_enhanced_prompt', False)
        
        if use_enhanced_prompt:
            # 使用函数级上下文和完整文件内容的增强模式
            logger.info("使用函数级上下文和完整文件内容的增强模式") #1.PATCH CHUNK 函数上下文 2.旧版本完整文件
            prompt_data = self._prepare_enhanced_prompt(context, patch_content)
            import pprint
            pprint.pprint(f"prompt_data:{prompt_data}")
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
        
        # 尝试直接使用git show -W获取整个补丁的函数级上下文
        logger.info("尝试使用git show -W获取整个补丁的函数级上下文")
        function_level_patch = self._generate_function_level_patch(context)
        if function_level_patch:
            logger.info("成功生成函数级别的补丁，将使用函数级别的提示模板")
            
            # 为每个修改的文件收集信息
            file_contexts = []
            
            for file_path in modified_files:
                try:
                    # 获取旧版本(目标版本)的文件内容
                    old_file_content = self._get_file_content_from_target(context, file_path)
                    
                    file_contexts.append({
                        'file_path': file_path,
                        'old_file_content': old_file_content,
                        'exists_in_old_version': old_file_content is not None
                    })
                    
                except Exception as e:
                    logger.error(f"处理文件 {file_path} 时出错: {e}")
                    logger.error(traceback.format_exc())
            
            # 构建增强的提示数据，使用函数级别的补丁
            enhanced_prompt = {
                'patch_content': patch_content,
                'target_version': context.config.target_version,
                'function_level_patch': function_level_patch,  # 添加函数级别的补丁
                'modified_files': file_contexts,  # 添加旧版本文件内容
                'feedback_instruction': '',
                'enhanced_prompt': True
            }
            
            return enhanced_prompt
        
        # 如果无法直接生成函数级别的补丁，回退到逐块提取函数上下文的方法
        logger.info("无法直接生成函数级别的补丁，回退到逐块提取函数上下文的方法")
        
        # 为每个修改的文件收集信息
        file_contexts = []
        
        for file_path in modified_files:
            try:
                # 获取修改块的信息
                chunks_info = self._extract_chunk_info(patch_content, file_path)
                logger.info(f"文件 {file_path} 包含 {len(chunks_info)} 个修改块")
                
                # 获取新版本的文件（如果存在于本地仓库）
                new_file_content = self._get_file_content_from_upstream(context, file_path)
                
                # 获取旧版本(目标版本)的文件内容
                old_file_content = self._get_file_content_from_target(context, file_path)
                
                # 为每个修改块获取函数级上下文
                function_contexts = []
                if new_file_content:
                    for i, chunk in enumerate(chunks_info):
                        # 确保 start_line 对新内容有效。
                        # _extract_chunk_info 中的块 'start_line' 和 'end_line' 是针对 *新* 文件的。
                        if chunk.get('new_count', 0) == 0 and chunk.get('old_count', 0) > 0: # 这是一个纯删除的chunk
                            logger.info(f"跳过文件 {file_path} 中的块 {i+1}/{len(chunks_info)} (行 {chunk['start_line']}-{chunk['end_line']})：纯删除块")
                            continue # 对于纯删除的块，在新文件中没有对应的行来查找函数上下文

                        logger.info(f"处理文件 {file_path} 中的块 {i+1}/{len(chunks_info)} (行 {chunk['start_line']}-{chunk['end_line']})")
                        func_context_str = self._extract_function_context(
                            new_file_content, 
                            chunk['start_line'], 
                            # 确保 end_line 有效，对于0行chunk（例如文件末尾添加空行），end_line可能小于start_line
                            chunk['end_line'] if chunk['end_line'] >= chunk['start_line'] else chunk['start_line'],
                            file_path
                        )
                        
                        if func_context_str:
                            function_contexts.append({
                                'lines': f"{chunk['start_line']}-{chunk['end_line']}",
                                'context': func_context_str
                            })
                            logger.info(f"文件 {file_path} 块 {i+1}/{len(chunks_info)} 成功提取函数上下文，长度: {len(func_context_str.split('\n'))}行")
                        else:
                            logger.warning(f"文件 {file_path} 块 {i+1}/{len(chunks_info)} 未能提取函数上下文")
                else:
                    logger.warning(f"无法获取文件 {file_path} 的新文件内容以提取函数上下文")
                    
                    # 尝试直接使用git show -W获取函数上下文
                    if hasattr(context, 'commit') and hasattr(context.commit, 'commit_sha'):
                        commit_sha = context.commit.commit_sha
                        # 确保commit_sha不包含.patch后缀
                        if commit_sha.endswith('.patch'):
                            commit_sha = commit_sha.replace('.patch', '')
                        
                        try:
                            logger.info(f"直接使用git show -W获取文件 {file_path} 在 {commit_sha} 的函数上下文")
                            result = subprocess.run(
                                ['git', 'show', '-W', f'{commit_sha}:{file_path}'],
                                cwd=repo_path,
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            
                            # 为每个chunk提取函数上下文
                            for i, chunk in enumerate(chunks_info):
                                logger.info(f"从git show -W输出中提取文件 {file_path} 块 {i+1}/{len(chunks_info)} (行 {chunk['start_line']}-{chunk['end_line']}) 的函数上下文")
                                func_context_str = self._extract_function_from_git_show_output(
                                    result.stdout,
                                    chunk['start_line'],
                                    chunk['end_line'] if chunk['end_line'] >= chunk['start_line'] else chunk['start_line']
                                )
                                
                                if func_context_str:
                                    function_contexts.append({
                                        'lines': f"{chunk['start_line']}-{chunk['end_line']}",
                                        'context': func_context_str
                                    })
                                    logger.info(f"文件 {file_path} 块 {i+1}/{len(chunks_info)} 成功从git show -W提取函数上下文，长度: {len(func_context_str.split('\n'))}行")
                                else:
                                    logger.warning(f"文件 {file_path} 块 {i+1}/{len(chunks_info)} 未能从git show -W提取函数上下文")
                        except Exception as e:
                            logger.warning(f"直接使用git show -W获取文件 {file_path} 函数上下文时出错: {e}")
                    pass

                # 打印函数上下文提取统计信息
                logger.info(f"文件 {file_path} 的函数上下文提取统计: 总块数: {len(chunks_info)}, 成功提取: {len(function_contexts)}")
                
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
        logger.info(f"共处理 {len(modified_files)} 个文件，提取了 {sum(len(fc['function_contexts']) for fc in file_contexts)} 个函数上下文")
        enhanced_prompt = {
            'patch_content': patch_content,
            'target_version': context.config.target_version,
            'modified_files': file_contexts,
            'feedback_instruction': '',
            'enhanced_prompt': True
        }
        
        return enhanced_prompt
        
    def _generate_function_level_patch(self, context: ModuleContext) -> Optional[str]:
        """
        使用git show -W直接生成整个补丁的函数级别上下文
        
        :param context: 模块上下文
        :return: 函数级别的补丁内容，如果失败则返回None
        """
        try:
            if not hasattr(context, 'commit') or not hasattr(context.commit, 'commit_sha'):
                logger.warning("无法获取commit_sha，无法生成函数级别的补丁")
                return None
                
            commit_sha = context.commit.commit_sha
            # 确保commit_sha不包含.patch后缀
            if commit_sha.endswith('.patch'):
                commit_sha = commit_sha.replace('.patch', '')
                logger.info(f"移除commit_sha的.patch后缀: {commit_sha}")
                
            repo_path = context.config.repo_path
            
            # 使用git show -W生成函数级别的补丁
            logger.info(f"使用git show -W生成函数级别的补丁，commit_sha: {commit_sha}, repo_path: {repo_path}")
            start_time = datetime.now()
            result = subprocess.run(
                ['git', 'show', '-W', commit_sha],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 检查结果
            if result.stdout:
                # 分析输出内容
                output_lines = result.stdout.split('\n')
                function_count = output_lines.count('@@ ')  # 估算函数数量
                
                # 保存函数级别的补丁到文件，便于调试
                function_level_patch_path = context.commit.base_dir / "function_level_patch.diff"
                with open(function_level_patch_path, 'w', encoding='utf-8') as f:
                    f.write(result.stdout)
                
                # 计算补丁大小
                patch_size_kb = len(result.stdout) / 1024
                
                logger.info(f"函数级别的补丁生成成功: {function_level_patch_path}")
                logger.info(f"补丁统计: 大小: {patch_size_kb:.2f} KB, 估计函数数量: {function_count}, 生成耗时: {execution_time:.2f} 秒")
                return result.stdout
            else:
                logger.warning(f"git show -W命令执行成功，但没有输出 (耗时: {execution_time:.2f} 秒)")
                return None
                
        except subprocess.CalledProcessError as e:
            logger.error(f"生成函数级别的补丁时出错: {e.stderr}")
            if hasattr(e, 'stdout') and e.stdout:
                logger.debug(f"命令输出: {e.stdout[:500]}..." if len(e.stdout) > 500 else e.stdout)
            return None
        except Exception as e:
            logger.error(f"生成函数级别的补丁时出错: {e}")
            logger.error(traceback.format_exc())
            return None
            
    def _extract_function_from_git_show_output(self, git_output: str, start_line: int, end_line: int) -> Optional[str]:
        """
        从git show -W的输出中提取包含指定行范围的函数。
        
        :param git_output: git show -W命令的输出
        :param start_line: 目标起始行
        :param end_line: 目标结束行
        :return: 提取的函数上下文，如果没有找到则返回None
        """
        try:
            # git show -W的输出格式为：
            # @@ -start,count +start,count @@ function signature
            # 函数内容...
            
            # 解析输出，查找包含目标行的函数
            functions = []
            current_function = []
            current_start_line = -1
            
            lines = git_output.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i]
                # 查找函数头部
                if line.startswith("@@ "):
                    # 如果已经在处理一个函数，保存它
                    if current_function:
                        functions.append((current_start_line, current_function))
                        current_function = []
                    
                    # 解析新函数的起始行
                    match = re.search(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
                    if match:
                        current_start_line = int(match.group(1))
                        # 包含函数签名行
                        current_function.append(line)
                else:
                    # 添加函数内容
                    if current_start_line != -1:
                        current_function.append(line)
                
                i += 1
            
            # 保存最后一个函数
            if current_function:
                functions.append((current_start_line, current_function))
            
            # 查找包含目标行的函数
            for func_start_line, func_content in functions:
                # 计算函数的结束行
                func_end_line = func_start_line + len(func_content) - 1
                
                # 检查目标行是否在此函数范围内
                if (func_start_line <= start_line <= func_end_line or 
                    func_start_line <= end_line <= func_end_line or
                    (start_line <= func_start_line and end_line >= func_end_line)):
                    # 返回函数内容，跳过第一行（函数签名行）
                    return '\n'.join(func_content[1:])
            
            # 如果没有找到包含目标行的函数
            return None
        
        except Exception as e:
            logger.warning(f"解析git show -W输出时出错: {e}")
            return None
    
    def _extract_fallback_context(self, lines: List[str], chunk_start_line: int, chunk_end_line: int, max_lines: int) -> Optional[str]:
        """
        提取围绕代码块的回退上下文。
        1. 定义一个最多 `max_lines` 行的初始窗口，以代码块为中心。
        2. 在此窗口内，从代码块向外扩展至最近的空行，或扩展至窗口边界。
        chunk_start_line 和 chunk_end_line 是基于1的行号。
        """
        num_total_lines = len(lines) # 文件总行数
        chunk_start_idx = chunk_start_line - 1  # 0-based 索引
        chunk_end_idx = chunk_end_line - 1    # 0-based 索引

        if not (0 <= chunk_start_idx < num_total_lines and 0 <= chunk_end_idx < num_total_lines and chunk_start_idx <= chunk_end_idx):
            # logger.warning(f"回退机制的块索引无效: {chunk_start_idx+1}-{chunk_end_idx+1} (文件总行数: {num_total_lines})。")
            if 0 <= chunk_start_idx < num_total_lines: # 如果可能，返回最小上下文
                 return lines[chunk_start_idx] 
            return None

        # 1. 定义初始搜索窗口 (max_lines 行，尝试将块居中)
        chunk_actual_length = chunk_end_idx - chunk_start_idx + 1 # 块的实际长度
        
        # 为达到 max_lines，理想情况下在块前后添加的行数
        lines_to_add = max_lines - chunk_actual_length
        
        if lines_to_add < 0: # 如果块本身就比 max_lines 长
            # 将 max_lines 窗口置于块的中心
            chunk_center_idx = chunk_start_idx + chunk_actual_length // 2
            window_start_idx = max(0, chunk_center_idx - max_lines // 2)
            window_end_idx = min(num_total_lines - 1, window_start_idx + max_lines - 1)
        else:
            lines_before = lines_to_add // 2 # 块前添加的行数
            lines_after = lines_to_add - lines_before # 块后添加的行数 (处理奇数情况)

            window_start_idx = max(0, chunk_start_idx - lines_before)
            window_end_idx = min(num_total_lines - 1, chunk_end_idx + lines_after)

            # 如果窗口碰触到文件边界并且还有剩余预算，则进行调整
            current_len = window_end_idx - window_start_idx + 1
            if current_len < max_lines:
                remaining_budget = max_lines - current_len
                if window_start_idx == 0 and window_end_idx < num_total_lines - 1: # 碰触到文件顶部
                    window_end_idx = min(num_total_lines - 1, window_end_idx + remaining_budget)
                elif window_end_idx == num_total_lines - 1 and window_start_idx > 0: # 碰触到文件底部
                    window_start_idx = max(0, window_start_idx - remaining_budget)
        
        # 确保窗口大小正确 (特别是在原始块非常大的情况下)
        if (window_end_idx - window_start_idx + 1) > max_lines:
            window_end_idx = window_start_idx + max_lines - 1


        # 2. 从块向空行扩展，但保持在 [window_start_idx, window_end_idx] 窗口内
        # 向上搜索空行或窗口边界
        final_start_idx = chunk_start_idx
        for i in range(chunk_start_idx - 1, window_start_idx - 1, -1): # 从块的上一行向上搜索到窗口顶
            if not lines[i].strip(): # 找到空行
                final_start_idx = i + 1 # 上下文在此空行之后开始
                break
            final_start_idx = i # 此非空行为当前可能的起始点
        
        # 向下搜索空行或窗口边界
        final_end_idx = chunk_end_idx
        for i in range(chunk_end_idx + 1, window_end_idx + 1): # 从块的下一行向下搜索到窗口底
            if not lines[i].strip(): # 找到空行
                final_end_idx = i - 1 # 上下文在此空行之前结束
                break
            final_end_idx = i # 此非空行为当前可能的结束点

        # 确保最终选择包含块并且在初始确定的窗口内
        final_start_idx = max(window_start_idx, min(final_start_idx, chunk_start_idx))
        final_end_idx = min(window_end_idx, max(final_end_idx, chunk_end_idx))

        if final_start_idx > final_end_idx: # 仅当窗口格式错误或非常小时才应发生
            # logger.warning(f"回退上下文导致起始大于结束。使用块本身或小窗口。")
            # 默认为块周围的一个小区域，在 max_lines 限制内
            final_start_idx = max(0, chunk_start_idx - max_lines // 4 )
            final_end_idx = min(num_total_lines -1, chunk_end_idx + max_lines // 4)
            if (final_end_idx - final_start_idx +1) > max_lines:
                final_end_idx = final_start_idx + max_lines -1


        # logger.info(f"块 {chunk_start_line}-{chunk_end_line} 的回退上下文: "
        #             f"窗口 [{window_start_idx+1}-{window_end_idx+1}], "
        #             f"最终行 [{final_start_idx+1}-{final_end_idx+1}]")
        return '\n'.join(lines[final_start_idx : final_end_idx + 1])
    
    def _add_failure_reason(self, reason: str):
        """增加失败原因统计"""
        if not hasattr(self, '_function_context_stats'):
            return
        
        if 'failure_reasons' not in self._function_context_stats:
            self._function_context_stats['failure_reasons'] = {}
        
        self._function_context_stats['failure_reasons'][reason] = self._function_context_stats['failure_reasons'].get(reason, 0) + 1
        logger.debug(f"上下文提取失败: {reason}")

    def _extract_function_context(self, file_content: str, start_line: int, end_line: int, file_path: str = "untitled") -> Optional[str]:
        """
        为一个修改过的代码块提取函数级别的上下文。
        使用git show -W命令获取函数级别的上下文，如果失败则回退到基于窗口的上下文。
        start_line 和 end_line 是基于1的行号。
        """
        self._function_context_stats['total'] += 1
        
        try:
            lines = file_content.split('\n')
            num_total_lines = len(lines)

            if not (1 <= start_line <= num_total_lines and 1 <= end_line <= num_total_lines and start_line <= end_line):
                # logger.warning(f"行号 [{start_line}-{end_line}] 超出文件 '{file_path}' ({num_total_lines} 行) 的范围。使用回退。")
                self._add_failure_reason('line_out_of_range')
                self._function_context_stats['fallback_triggered'] += 1
                return self._extract_fallback_context(lines, start_line, end_line, self.DEFAULT_CONTEXT_LINES)

            chunk_start_idx = start_line - 1 # 0-based 内部使用
            # chunk_end_idx = end_line - 1   # 0-based, 不直接用于函数搜索的起始点

            func_def_line_idx = -1 # 函数定义行的索引
            func_def_indent = -1   # 函数定义行的缩进级别
            is_python_like = False # 是否为类Python（基于缩进）的语言
            
            # 从 chunk_start_idx 向上搜索函数定义
            # 将搜索限制在合理的行数内，例如 chunk_start_idx 之上100行
            search_limit_up = max(-1, chunk_start_idx - 100) # -1 是因为 range 对于结束值是 exclusives
            for i in range(chunk_start_idx, search_limit_up, -1):
                line_text_with_indent = lines[i] # 带缩进的原始行文本
                # 优化：如果行太短不可能是定义，或者相对于块的缩进过深，则跳过。
                # 这需要仔细考虑，以免过早排除有效情况。

                for pattern_idx, pattern in enumerate(self.patterns):
                    match = pattern.search(line_text_with_indent)
                    if match:
                        func_def_line_idx = i
                        func_def_indent = len(line_text_with_indent) - len(line_text_with_indent.lstrip())
                        if pattern_idx == 0: # py_def_pattern
                            is_python_like = True
                        # else if pattern_idx == 1 and "=>" in line_text_with_indent: # JS箭头函数可能不像典型括号语言那样使用大括号
                            # 可能需要不同处理或确保括号逻辑的健壮性
                        break  # 找到模式匹配，跳出内部循环
                if func_def_line_idx != -1:
                    break # 找到函数定义行，跳出外部循环
            
            if func_def_line_idx == -1:
                # logger.info(f"在文件 '{file_path}' 的行 {start_line} 之上未找到函数定义。使用回退。")
                self._add_failure_reason('no_func_def_found_upwards')
                self._function_context_stats['fallback_triggered'] += 1
                return self._extract_fallback_context(lines, start_line, end_line, self.DEFAULT_CONTEXT_LINES)

            # 找到了一个潜在的函数定义。现在包含其正上方的注释。
            actual_func_start_idx = func_def_line_idx
            for i in range(func_def_line_idx - 1, max(-1, func_def_line_idx - 25), -1): # 向上检查最多25行以查找注释
                line_text_stripped = lines[i].strip()
                if not line_text_stripped or line_text_stripped.startswith(('#', '//', '/*', '*', '"""', "'''")):
                    actual_func_start_idx = i
                else: # 找到非注释、非空行，停止。
                    break 

            # 现在找到函数结束的位置
            actual_func_end_idx = -1
            if is_python_like:
                # 类Python语言：结束位置由缩进减少到 func_def_indent 或更少，或文件结束（EOF）决定
                for i in range(actual_func_start_idx + 1, num_total_lines):
                    current_line_text = lines[i]
                    current_line_stripped = current_line_text.strip()
                    
                    if not current_line_stripped or current_line_stripped.startswith('#'): # 跳过空行或注释行
                        if i == num_total_lines - 1: # 在注释/空行上到达EOF
                            actual_func_end_idx = i
                        continue # 处理下一行
                    
                    current_indent = len(current_line_text) - len(current_line_text.lstrip())
                    if current_indent <= func_def_indent:
                        actual_func_end_idx = i - 1 # 前一行是函数的结尾
                        break
                    if i == num_total_lines - 1: # 到达文件末尾且仍然缩进
                        actual_func_end_idx = i
                
                if actual_func_end_idx == -1: # 例如单行函数或在EOF之前只找到def行
                     actual_func_end_idx = max(actual_func_start_idx, num_total_lines -1 if actual_func_start_idx < num_total_lines else actual_func_start_idx)
                     if actual_func_start_idx == num_total_lines -1 : actual_func_end_idx = actual_func_start_idx


            else: # 基于大括号的语言 (启发式方法)
                brace_count = 0 # 大括号计数器
                found_initial_brace = False # 是否找到初始的开大括号
                # 从函数定义行开始搜索第一个 '{'。
                # 它可能在定义行本身，或在下面几行 (K&R 风格)。
                start_brace_search_from_idx = func_def_line_idx 
                
                for i in range(start_brace_search_from_idx, min(num_total_lines, start_brace_search_from_idx + 10)): # 在10行内寻找 '{'
                    line_str = lines[i]
                    open_brace_col = line_str.find('{') # 查找开大括号的位置
                    if open_brace_col != -1:
                        found_initial_brace = True
                        # 处理此行上从第一个 '{' 开始的所有大括号
                        for char_scan_idx in range(open_brace_col, len(line_str)):
                            char_val = line_str[char_scan_idx]
                            if char_val == '{': brace_count += 1
                            elif char_val == '}': brace_count -= 1
                        
                        if brace_count == 0: # 函数在包含 '{' 的同一行结束
                            actual_func_end_idx = i
                            break 
                        start_brace_search_from_idx = i + 1 # 从此行的 *下一* 行继续完整扫描
                        break # 找到初始大括号，进入下一扫描阶段
                
                if not found_initial_brace:
                    # logger.info(f"在文件 '{file_path}' 的行 {func_def_line_idx+1} 处未找到假定基于括号的函数的开括号。使用回退。")
                    self._add_failure_reason('no_opening_brace')
                    self._function_context_stats['fallback_triggered'] += 1
                    return self._extract_fallback_context(lines, start_line, end_line, self.DEFAULT_CONTEXT_LINES)

                if actual_func_end_idx == -1: # 如果不是在初始括号行结束的单行函数
                    for i in range(start_brace_search_from_idx, num_total_lines):
                        for char_val in lines[i]:
                            if char_val == '{': brace_count += 1
                            elif char_val == '}': brace_count -= 1
                        if brace_count == 0 and found_initial_brace : # 找到匹配的闭大括号
                            actual_func_end_idx = i
                            break
                    if actual_func_end_idx == -1 and found_initial_brace: # 大括号不平衡，假设扩展到EOF
                        # logger.debug(f"文件 '{file_path}' 中行 {func_def_line_idx+1} 处的函数大括号不平衡。假设EOF为结尾。")
                        actual_func_end_idx = num_total_lines - 1 # 假设在文件末尾结束
            
            if actual_func_end_idx == -1 :
                # logger.info(f"无法确定文件 '{file_path}' 中行 {actual_func_start_idx+1} 处定义的函数结尾。使用回退。")
                self._add_failure_reason('func_end_not_determined')
                self._function_context_stats['fallback_triggered'] += 1
                return self._extract_fallback_context(lines, start_line, end_line, self.DEFAULT_CONTEXT_LINES)

            actual_func_end_idx = max(actual_func_start_idx, actual_func_end_idx) # 确保结束不先于开始

            func_length = actual_func_end_idx - actual_func_start_idx + 1
            if func_length > self.MAX_FUNCTION_LINES_THRESHOLD:
                # logger.info(f"文件 '{file_path}' 中位于 [{actual_func_start_idx+1}-{actual_func_end_idx+1}] ({func_length} 行) 的函数 "
                #             f"超过阈值 {self.MAX_FUNCTION_LINES_THRESHOLD}。使用回退。")
                self._add_failure_reason('func_too_long')
                self._function_context_stats['fallback_triggered'] += 1
                return self._extract_fallback_context(lines, start_line, end_line, self.DEFAULT_CONTEXT_LINES)
            
            self._function_context_stats['success'] += 1
            return '\n'.join(lines[actual_func_start_idx : actual_func_end_idx + 1])

        except Exception as e:
            # logger.error(f"提取文件 '{file_path}' [{start_line}-{end_line}] 的函数上下文时出错: {e}")
            # logger.error(traceback.format_exc()) # 详细错误信息
            self._add_failure_reason('exception_in_extract_func')
            self._function_context_stats['fallback_triggered'] += 1
            if 'lines' in locals() and isinstance(lines, list): # 检查 'lines' 是否已定义
                 return self._extract_fallback_context(lines, start_line, end_line, self.DEFAULT_CONTEXT_LINES)
            return None # 如果 file_content 始终是有效字符串，则理想情况下不应到达此处
   
    
    # def _add_failure_reason(self, reason):
    #     """增加失败原因统计"""
    #     if not hasattr(self, '_function_context_stats'):
    #         return
        
    #     if 'failure_reasons' not in self._function_context_stats:
    #         self._function_context_stats['failure_reasons'] = {}
        
    #     self._function_context_stats['failure_reasons'][reason] = self._function_context_stats['failure_reasons'].get(reason, 0) + 1
    
    def _get_context_diff(self, context: ModuleContext, patch_content: str) -> str:
        """获取上下文差异"""
        try:
            # 从commit目录中直接读取diff文件
            diff_file = context.commit.base_dir / 'diff'
            logger.info(f"diff_file: {diff_file.absolute()}")
            # logger.info(f"absolute diff_file: {diff_file.absolute()}")
            if diff_file.exists():
                clean_diff_content = html.unescape(diff_file.read_text(encoding='utf-8', errors='replace'))
                logger.info(f"diff_content: {clean_diff_content}")
                return clean_diff_content
                
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
                    return html.unescape(diff_file.read_text(encoding='utf-8', errors='replace'))
                elif result and "prompt_values" in result and result["prompt_values"]:
                    return result["prompt_values"][0]["diffCode"]
                else:
                    logger.warning("无法获取diff内容，使用原始补丁作为差异")
                    return f"无法获取上下文差异，使用原始补丁作为差异：\n{patch_content}"
            except Exception as inner_e:
                logger.error(f"执行patch_processor失败: {inner_e}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
                # 尝试回退到替代方法
                if hasattr(context.commit, 'patch_path'):
                    patch_path = context.commit.patch_path
                    # 确保patch_path是Path对象
                    if isinstance(patch_path, str):
                        patch_path = Path(patch_path)
                    
                    if patch_path.exists():
                        logger.info("使用patch文件作为diff内容")
                        return patch_path.read_text(encoding='utf-8', errors='replace')
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
        # 配置LLMAssistant所需的参数
        extra_values = {
            'patchCode': prompt_data['patch_content'],
        }
        
        # 确定使用哪种提示模板
        prompt_id = "backport-diff"  # 默认使用标准的diff模板
        
        # 如果有函数级别的补丁，添加到prompt_values中并使用function_level模板
        if 'function_level_patch' in prompt_data:
            # 使用新的backport-func模板
            prompt_id = "backport-func"
            
            # 准备旧版本文件内容
            old_version_files = {}
            if 'modified_files' in prompt_data:
                for file_info in prompt_data['modified_files']:
                    file_path = file_info.get('file_path', '')
                    old_content = file_info.get('old_file_content', '')
                    if file_path and old_content:
                        old_version_files[file_path] = old_content
            
            # 格式化旧版本文件内容
            old_version_files_str = ""
            for file_path, content in old_version_files.items():
                file_ext = os.path.splitext(file_path)[1][1:] or "txt"  # 获取文件扩展名，默认为txt
                old_version_files_str += f"File: {file_path}\n```{file_ext}\n{content}\n```\n\n"
            
            # 设置函数级别补丁和旧版本文件内容
            extra_values = {
                'functionLevelPatch': prompt_data['function_level_patch'],
                'oldVersionFiles': old_version_files_str
            }
            
            logger.info(f"使用函数级别的补丁，切换到提示模板: {prompt_id}")
            logger.info(f"准备了 {len(old_version_files)} 个旧版本文件内容")
            
        elif 'context_diff' in prompt_data:
            extra_values['diffCode'] = prompt_data['context_diff']
            # 检查是否使用增强提示模式
            use_enhanced_prompt = context.config.module_configs.get('llm_adapter', {}).get('use_enhanced_prompt', False)
            if use_enhanced_prompt:
                prompt_id = "backport-diff"  # 使用标准diff模板
                logger.info(f"使用增强提示模式，但没有函数级别的补丁，使用标准diff模板: {prompt_id}")
            else:
                prompt_id = "backport-diff"  # 使用标准diff模板
                logger.info(f"使用标准提示模式，使用diff模板: {prompt_id}")
        
        llm_config = {
            'prompt_template_file': context.config.prompt_template_file,
            'prompt_id': prompt_id,  # 使用确定的prompt_id
            'extra_config': {
                'prompt_values': [extra_values]
            }
        }
        
        # 创建新的ModuleContext，使用原始配置并添加新的配置
        llm_context = ModuleContext(
            config=context.config.model_copy(update=llm_config),  # 使用pydantic的model_copy方法
            commit=context.commit
        )
        
        # 初始化LLMAssistant
        llm = LLMAssistant(llm_context)
        
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

    def _save_evaluation_info(self, context: ModuleContext):
        """
        保存美观易读的输入/输出评估信息，特别关注函数上下文提取相关的信息
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
            
            # 保存原始补丁内容
            patch_content = ""
            if context.commit.patch_path and Path(context.commit.patch_path).exists():
                try:
                    with open(context.commit.patch_path, 'r', encoding='utf-8') as f:
                        patch_content = f.read()
                    
                    patch_file = details_dir / "original_patch.diff"
                    with open(patch_file, 'w', encoding='utf-8') as f:
                        f.write(patch_content)
                except Exception as e:
                    logger.error(f"保存原始补丁时出错: {e}")
            
            # 保存提取的函数上下文信息
            self._save_function_context_info(context, details_dir, patch_content)
            
            # 保存LLM输入输出信息
            self._save_llm_io_info(context, details_dir)
            
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
            
            logger.info(f"LLM适配器评估信息已保存到: {details_dir}")
            
        except Exception as e:
            logger.error(f"保存评估信息失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    def _save_function_context_info(self, context: ModuleContext, details_dir: Path, patch_content: str):
        """保存函数上下文提取的详细信息"""
        try:
            # 提取补丁中的块信息
            chunks_info = []
            if patch_content:
                file_chunks = self._extract_chunk_info(patch_content, "")
                
                # 为每个块提取函数上下文
                for i, chunk in enumerate(file_chunks):
                    file_path = chunk.get('file_path', 'unknown_file')
                    start_line = chunk.get('start_line', 0)
                    end_line = chunk.get('end_line', 0)
                    
                    # 从上游获取文件内容
                    file_content = self._get_file_content_from_upstream(context, file_path)
                    if not file_content:
                        file_content = self._get_file_content_from_target(context, file_path)
                    
                    if file_content:
                        # 提取上下50行
                        lines = file_content.split('\n')
                        total_lines = len(lines)
                        
                        context_start = max(1, start_line - 50)
                        context_end = min(total_lines, end_line + 50)
                        
                        surrounding_lines = '\n'.join(lines[context_start-1:context_end])
                        
                        # 提取函数上下文
                        function_context = self._extract_function_context(file_content, start_line, end_line)
                        
                        chunk_info = {
                            'chunk_index': i,
                            'file_path': file_path,
                            'start_line': start_line,
                            'end_line': end_line,
                            'surrounding_lines': surrounding_lines,
                            'surrounding_range': f"{context_start}-{context_end}",
                            'function_context': function_context
                        }
                        chunks_info.append(chunk_info)
                
                # 保存块信息
                chunks_file = details_dir / "chunks_function_context.json"
                with open(chunks_file, 'w', encoding='utf-8') as f:
                    json.dump(chunks_info, f, indent=2, ensure_ascii=False)
                
                # 为每个块创建单独的文件，便于查看
                chunks_dir = details_dir / "chunks"
                chunks_dir.mkdir(parents=True, exist_ok=True)
                
                for i, chunk in enumerate(chunks_info):
                    # 保存周围行
                    surrounding_file = chunks_dir / f"chunk_{i}_surrounding_lines.txt"
                    with open(surrounding_file, 'w', encoding='utf-8') as f:
                        f.write(f"文件: {chunk['file_path']}\n")
                        f.write(f"行范围: {chunk['surrounding_range']}\n")
                        f.write("-" * 80 + "\n")
                        f.write(chunk['surrounding_lines'])
                    
                    # 保存函数上下文
                    if chunk['function_context']:
                        function_file = chunks_dir / f"chunk_{i}_function_context.txt"
                        with open(function_file, 'w', encoding='utf-8') as f:
                            f.write(f"文件: {chunk['file_path']}\n")
                            f.write(f"补丁行范围: {chunk['start_line']}-{chunk['end_line']}\n")
                            f.write("-" * 80 + "\n")
                            f.write(chunk['function_context'])
        
        except Exception as e:
            logger.error(f"保存函数上下文信息失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    def _save_llm_io_info(self, context: ModuleContext, details_dir: Path):
        """保存LLM输入输出的详细信息"""
        try:
            if context.llm_output:
                llm_dir = details_dir / "llm_io"
                llm_dir.mkdir(parents=True, exist_ok=True)
                
                # 保存提示词
                if 'prompt' in context.llm_output:
                    prompt_file = llm_dir / "prompt.txt"
                    with open(prompt_file, 'w', encoding='utf-8') as f:
                        f.write(context.llm_output['prompt'])
                
                # 保存LLM响应
                if 'response' in context.llm_output:
                    sresponse_file = llm_dir / "response.txt"
                    with open(response_file, 'w', encoding='utf-8') as f:
                        f.write(context.llm_output['response'])
                
                # 保存增强模式数据
                if 'enhanced_data' in context.llm_output:
                    enhanced_file = llm_dir / "enhanced_data.json"
                    with open(enhanced_file, 'w', encoding='utf-8') as f:
                        json.dump(context.llm_output['enhanced_data'], f, indent=2, ensure_ascii=False)
        
        except Exception as e:
            logger.error(f"保存LLM IO信息失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    def _collect_input_info(self, context: ModuleContext) -> Dict[str, Any]:
        """收集输入信息"""
        input_info = {
            "原始补丁路径": str(context.commit.patch_path) if hasattr(context.commit, "patch_path") else "未知",
            "代码仓库路径": str(context.config.repo_path) if hasattr(context.config, "repo_path") else "未知",
            "目标版本": context.config.target_version,
            "使用函数级上下文": self.config.get('use_function_context', True),
            "使用增强模式": self.config.get('use_enhanced_mode', False),
            "LLM模型": context.config.model
        }
        
        # 添加补丁分析信息
        if context.commit.patch_path and Path(context.commit.patch_path).exists():
            try:
                with open(context.commit.patch_path, 'r', encoding='utf-8') as f:
                    patch_content = f.read()
                
                file_chunks = self._extract_chunk_info(patch_content, "")
                input_info["补丁修改块数"] = len(file_chunks)
                input_info["修改文件列表"] = list(set(chunk['file_path'] for chunk in file_chunks if 'file_path' in chunk))
            except Exception as e:
                logger.error(f"收集补丁信息时出错: {e}")
        
        return input_info
    
    def _collect_output_info(self, context: ModuleContext) -> Dict[str, Any]:
        """收集输出信息"""
        output_info = {
            "状态": "成功" if context.llm_output and context.llm_output.get('success', False) else "失败",
            "生成补丁路径": str(context.llm_output.get('patch_path', 'N/A')) if context.llm_output else "N/A",
            "函数上下文提取成功率": "N/A",
            "补丁应用测试结果": "N/A"
        }
        
        # 函数上下文提取成功率
        if hasattr(self, '_function_context_stats'):
            stats = getattr(self, '_function_context_stats', {})
            total = stats.get('total', 0)
            success = stats.get('success', 0)
            if total > 0:
                output_info["函数上下文提取成功率"] = f"{success}/{total} ({success/total*100:.1f}%)"
            output_info["函数上下文提取失败理由"] = stats.get('failure_reasons', {})
        
        # 补丁应用测试结果
        if context.llm_output and 'test_result' in context.llm_output:
            test_result = context.llm_output['test_result']
            output_info["补丁应用测试结果"] = "成功" if test_result.get('success', False) else "失败"
            if not test_result.get('success', False):
                output_info["补丁应用失败原因"] = test_result.get('error_type', 'unknown')
        
        return output_info
    
    def _generate_additional_html_sections(self, context: ModuleContext) -> str:
        """生成额外的HTML报告部分"""
        additional_sections = ""
        
        # 函数上下文提取部分
        additional_sections += """
        <div class="card">
          <h2>函数上下文提取结果</h2>
          <p>下面列出了从修改块中提取的函数上下文信息。这些信息用于为LLM提供足够的语义上下文。</p>
          <div class="accordion">
        """
        
        # 尝试从评估目录中读取chunks_function_context.json
        eval_dir = context.base_dir / "evaluations" / self.name
        latest_dir = None
        
        # 查找最新的评估目录
        try:
            dirs = [d for d in eval_dir.iterdir() if d.is_dir() and d.name.startswith("details_")]
            if dirs:
                latest_dir = max(dirs, key=lambda d: d.stat().st_mtime)
        except Exception:
            pass
        
        # 读取chunks信息
        chunks_info = []
        if latest_dir and (latest_dir / "chunks_function_context.json").exists():
            try:
                with open(latest_dir / "chunks_function_context.json", 'r', encoding='utf-8') as f:
                    chunks_info = json.load(f)
            except Exception:
                pass
        
        # 为每个chunk生成HTML部分
        for i, chunk in enumerate(chunks_info):
            file_path = chunk.get('file_path', 'unknown_file')
            start_line = chunk.get('start_line', 0)
            end_line = chunk.get('end_line', 0)
            surrounding_range = chunk.get('surrounding_range', 'N/A')
            has_function_context = chunk.get('function_context') is not None
            
            additional_sections += f"""
            <div class="accordion-item">
              <div class="accordion-header" onclick="toggleAccordion(this)">
                <h3>块 {i+1}: {file_path} (行 {start_line}-{end_line})</h3>
                <span class="tag {
                    'tag-success' if has_function_context else 'tag-error'
                }">{
                    '已提取函数上下文' if has_function_context else '未提取函数上下文'
                }</span>
              </div>
              <div class="accordion-content">
                <div class="tabs">
                  <div class="tab-header">
                    <button class="tab-button active" onclick="openTab(event, 'function-context-{i}')">函数上下文</button>
                    <button class="tab-button" onclick="openTab(event, 'surrounding-lines-{i}')">周围行 ({surrounding_range})</button>
                  </div>
                  
                  <div id="function-context-{i}" class="tab-content" style="display:block;">
                    <pre>{
                        chunk.get('function_context', '未能提取函数上下文').replace('<', '&lt;').replace('>', '&gt;')
                    }</pre>
                  </div>
                  
                  <div id="surrounding-lines-{i}" class="tab-content">
                    <pre>{
                        chunk.get('surrounding_lines', '未能提取周围行').replace('<', '&lt;').replace('>', '&gt;')
                    }</pre>
                  </div>
                </div>
              </div>
            </div>
            """
        
        additional_sections += """
          </div>
        </div>
        
        <div class="card">
          <h2>LLM输入输出</h2>
          <p>下面是发送给LLM的提示词以及LLM返回的响应。</p>
          <div class="tabs">
            <div class="tab-header">
              <button class="tab-button active" onclick="openTab(event, 'llm-prompt')">提示词</button>
              <button class="tab-button" onclick="openTab(event, 'llm-response')">响应</button>
            </div>
            
            <div id="llm-prompt" class="tab-content" style="display:block;">
              <pre>"""
        
        # 添加提示词内容
        if context.llm_output and 'prompt' in context.llm_output:
            additional_sections += context.llm_output['prompt'].replace('<', '&lt;').replace('>', '&gt;')
        else:
            additional_sections += "未找到提示词"
        
        additional_sections += """</pre>
            </div>
            
            <div id="llm-response" class="tab-content">
              <pre>"""
        
        # 添加响应内容
        if context.llm_output and 'response' in context.llm_output:
            additional_sections += context.llm_output['response'].replace('<', '&lt;').replace('>', '&gt;')
        else:
            additional_sections += "未找到响应"
        
        additional_sections += """</pre>
            </div>
          </div>
        </div>
        
        <script>
        function toggleAccordion(element) {
          element.parentElement.classList.toggle("active");
          var content = element.nextElementSibling;
          if (content.style.maxHeight) {
            content.style.maxHeight = null;
          } else {
            content.style.maxHeight = content.scrollHeight + "px";
          }
        }
        
        function openTab(evt, tabName) {
          var i, tabcontent, tabbuttons;
          
          // 隐藏所有标签内容
          tabcontent = evt.currentTarget.parentElement.parentElement.getElementsByClassName("tab-content");
          for (i = 0; i < tabcontent.length; i++) {
            tabcontent[i].style.display = "none";
          }
          
          // 移除所有标签按钮的active类
          tabbuttons = evt.currentTarget.parentElement.getElementsByClassName("tab-button");
          for (i = 0; i < tabbuttons.length; i++) {
            tabbuttons[i].className = tabbuttons[i].className.replace(" active", "");
          }
          
          // 显示当前标签并添加active类到按钮
          document.getElementById(tabName).style.display = "block";
          evt.currentTarget.className += " active";
        }
        </script>
        
        <style>
        .accordion {
          width: 100%;
        }
        
        .accordion-item {
          margin-bottom: 10px;
          border: 1px solid #ddd;
          border-radius: 5px;
          overflow: hidden;
        }
        
        .accordion-header {
          background-color: #f8f9fa;
          padding: 15px;
          cursor: pointer;
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        
        .accordion-header h3 {
          margin: 0;
          font-size: 16px;
        }
        
        .accordion-content {
          padding: 0;
          max-height: 0;
          overflow: hidden;
          transition: max-height 0.3s ease-out;
        }
        
        .accordion-item.active .accordion-content {
          max-height: 1000px;
        }
        
        .tabs {
          width: 100%;
        }
        
        .tab-header {
          overflow: hidden;
          border-bottom: 1px solid #ccc;
          background-color: #f1f1f1;
        }
        
        .tab-button {
          background-color: inherit;
          float: left;
          border: none;
          outline: none;
          cursor: pointer;
          padding: 12px 16px;
          transition: 0.3s;
          font-size: 14px;
        }
        
        .tab-button:hover {
          background-color: #ddd;
        }
        
        .tab-button.active {
          background-color: #3498db;
          color: white;
        }
        
        .tab-content {
          display: none;
          padding: 15px;
          border-top: none;
        }
        </style>
        """
        
        return additional_sections
    
    def _generate_readme(self, details_dir: Path, context: ModuleContext, evaluation_info: Dict[str, Any]):
        """生成评估信息的README文件"""
        readme_file = details_dir / "README.md"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(f"# LLM适配器模块评估信息\n\n")
            
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
            
            # 函数上下文提取
            f.write(f"\n## 函数上下文提取\n\n")
            f.write("函数上下文提取是LLM适配的关键步骤，能够为大模型提供充分的代码语义理解环境。\n")
            f.write("详细的提取结果可以在以下目录中查看：\n\n")
            f.write("- chunks/: 包含每个修改块的函数上下文提取结果\n")
            f.write("- chunks_function_context.json: 所有块的函数上下文信息\n\n")
            
            # LLM输入输出
            f.write(f"## LLM输入输出\n\n")
            f.write("LLM的输入和输出保存在以下目录：\n\n")
            f.write("- llm_io/prompt.txt: 发送给LLM的提示词\n")
            f.write("- llm_io/response.txt: LLM的响应\n")
            
            # 目录说明
            f.write(f"\n## 目录内容说明\n\n")
            f.write(f"- summary.json: 评估信息摘要\n")
            f.write(f"- original_patch.diff: 原始补丁文件\n")
            f.write(f"- report.html: HTML格式评估报告\n")
            f.write(f"- chunks/: 每个修改块的详细信息\n")
            f.write(f"- llm_io/: LLM输入输出信息\n")

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
                    logger.info(f"成功获取文件 {mapped_path} 在目标版本 {target_version} 的内容，大小: {len(content)} 字节")
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
                    logger.info(f"成功获取文件 {file_path} 在上游分支 {upstream_branch} 的内容，大小: {len(content)} 字节")
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
