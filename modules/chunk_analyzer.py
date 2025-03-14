from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import re
import os
import subprocess
import tempfile
from datetime import datetime
from loguru import logger
import difflib
import json

from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext


class ChunkAnalyzerModule(BaseModule):
    """补丁分块分析和优化模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.CHUNK_ANALYZER
        self.name = "chunk_analyzer"
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行补丁分块分析和优化"""
        if not self._should_run(context):
            return context
            
        start_time = datetime.now()
        
        try:
            # 只有当direct_apply失败时才进行处理
            if not context.direct_apply_result or context.direct_apply_result.get('success', True):
                logger.info("直接应用成功或未执行，跳过补丁分块分析")
                return context
                
            # 获取补丁文件路径
            patch_path = Path(context.direct_apply_result.get('patch_path', ''))
            if not patch_path.exists():
                patch_path = context.commit.patch_path
                if not patch_path.exists():
                    raise ValueError("没有找到有效的补丁文件路径")
            
            logger.info(f"开始分析补丁: {patch_path}")
            
            # 1. 将补丁分解为块
            chunks = self._split_patch_into_chunks(patch_path)
            logger.info(f"补丁被分解为 {len(chunks)} 个块")
            
            # 2. 分析每个块，确定是否是有价值的块
            valuable_chunks, skipped_chunks = self._analyze_chunks(chunks, context)
            logger.info(f"有价值的块: {len(valuable_chunks)}, 跳过的块: {len(skipped_chunks)}")
            
            # 3. 生成精简的补丁
            optimized_patch_path = self._generate_optimized_patch(valuable_chunks, context)
            
            # 4. 保存分析结果
            analysis_result = {
                'original_patch': str(patch_path),
                'optimized_patch': str(optimized_patch_path),
                'total_chunks': len(chunks),
                'valuable_chunks': len(valuable_chunks),
                'skipped_chunks': len(skipped_chunks),
                'optimization_rate': (len(skipped_chunks) / len(chunks)) if chunks else 0,
                'timestamp': datetime.now().isoformat()
            }
            
            # 将结果写入上下文
            context.chunk_analyzer_result = analysis_result
            
            # 更新补丁路径，以便后续模块使用优化后的补丁
            context.commit.optimized_patch_path = optimized_patch_path
            
            # 更新指标
            self._update_metrics(
                success=True,
                execution_time=(datetime.now() - start_time).total_seconds()
            )
            
        except Exception as e:
            logger.error(f"补丁分析过程发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            context.chunk_analyzer_result = {
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
    
    def _should_run(self, context: ModuleContext) -> bool:
        """判断是否应该运行此模块"""
        # 检查模块是否启用
        if self.name not in context.config.enabled_modules:
            logger.info(f"模块 {self.name} 未启用，跳过")
            return False
        
        # 只有当direct_apply模块执行失败时才执行本模块
        if not context.direct_apply_result:
            logger.info("直接应用未执行，跳过补丁分块分析")
            return False
            
        if context.direct_apply_result.get('success', False):
            logger.info("直接应用成功，跳过补丁分块分析")
            return False
        
        return True
    
    def _split_patch_into_chunks(self, patch_path: Path) -> List[Dict[str, Any]]:
        """
        将补丁文件分解为独立的代码块
        
        返回格式:
        [
            {
                'file_path': 'path/to/file',
                'chunk_type': 'modification/addition/deletion',
                'start_line': line_number,
                'end_line': line_number,
                'content': 'chunk content'
            },
            ...
        ]
        """
        chunks = []
        current_file = None
        current_chunk = None
        chunk_content = []
        
        try:
            with open(patch_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for i, line in enumerate(lines):
                # 检测文件头
                if line.startswith('diff --git'):
                    # 保存之前的chunk
                    if current_chunk:
                        current_chunk['content'] = ''.join(chunk_content)
                        chunks.append(current_chunk)
                        chunk_content = []
                    
                    # 提取文件路径
                    match = re.search(r'diff --git a/(.*) b/(.*)', line)
                    if match:
                        current_file = match.group(1)
                    current_chunk = None
                
                # 检测hunk头
                elif line.startswith('@@'):
                    # 保存之前的chunk
                    if current_chunk:
                        current_chunk['content'] = ''.join(chunk_content)
                        chunks.append(current_chunk)
                        chunk_content = []
                    
                    # 解析hunk头
                    match = re.search(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                    if match:
                        old_start = int(match.group(1))
                        old_count = int(match.group(2)) if match.group(2) else 1
                        new_start = int(match.group(3))
                        new_count = int(match.group(4)) if match.group(4) else 1
                        
                        chunk_type = 'modification'
                        if old_count == 0:
                            chunk_type = 'addition'
                        elif new_count == 0:
                            chunk_type = 'deletion'
                        
                        current_chunk = {
                            'file_path': current_file,
                            'chunk_type': chunk_type,
                            'old_start': old_start,
                            'old_count': old_count,
                            'new_start': new_start,
                            'new_count': new_count,
                            'hunk_header': line
                        }
                
                # 收集chunk内容
                if current_chunk:
                    chunk_content.append(line)
            
            # 保存最后一个chunk
            if current_chunk:
                current_chunk['content'] = ''.join(chunk_content)
                chunks.append(current_chunk)
        
        except Exception as e:
            logger.error(f"分割补丁出错: {e}")
            raise
        
        return chunks
    
    def _analyze_chunks(self, chunks: List[Dict[str, Any]], context: ModuleContext) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        分析每个chunk，判断其是否为有价值的修改
        
        返回两个列表:
        1. 有价值的chunks
        2. 跳过的chunks
        """
        valuable_chunks = []
        skipped_chunks = []
        
        repo_path = context.config.repo_path
        target_version = context.config.target_version
        
        for chunk in chunks:
            file_path = chunk['file_path']
            target_file_path = Path(repo_path) / file_path
            
            # 如果文件在目标仓库中不存在，则认为是有价值的chunk
            if not target_file_path.exists():
                valuable_chunks.append(chunk)
                continue
            
            # 分析chunk是否只是行号变动或空白字符变化
            is_valuable = self._is_valuable_chunk(chunk, target_file_path)
            
            if is_valuable:
                valuable_chunks.append(chunk)
            else:
                skipped_chunks.append(chunk)
        
        return valuable_chunks, skipped_chunks
    
    def _is_valuable_chunk(self, chunk: Dict[str, Any], target_file_path: Path) -> bool:
        """
        判断chunk是否有价值
        
        判断逻辑：
        1. 如果是新增或删除文件，则认为有价值
        2. 如果只是行号变动或空白字符变化，则认为无价值
        3. 尝试提取修改所在的函数上下文，比较函数在新旧版本中的差异
        """
        # 如果是新增或删除文件，认为有价值
        if chunk['chunk_type'] in ['addition', 'deletion'] and (
            chunk['old_count'] == 0 or chunk['new_count'] == 0):
            return True
        
        # 读取chunk内容，提取实际修改的行
        content_lines = chunk['content'].splitlines()
        has_real_changes = False
        
        for line in content_lines[1:]:  # 跳过hunk头
            if line.startswith('+') and not line.startswith('++'):
                # 去除空白字符后比较
                stripped_line = re.sub(r'\s+', '', line[1:])
                if stripped_line:  # 如果非空，则有实际内容变化
                    has_real_changes = True
                    break
            elif line.startswith('-') and not line.startswith('--'):
                # 去除空白字符后比较
                stripped_line = re.sub(r'\s+', '', line[1:])
                if stripped_line:  # 如果非空，则有实际内容变化
                    has_real_changes = True
                    break
        
        # 如果没有实际内容变化，认为无价值
        if not has_real_changes:
            return False
        
        # TODO: 进一步优化: 提取函数上下文进行比较
        # 这部分可以根据实际需求扩展
        
        return True
    
    def _generate_optimized_patch(self, valuable_chunks: List[Dict[str, Any]], context: ModuleContext) -> Path:
        """
        根据有价值的块生成优化后的补丁文件
        """
        # 创建临时目录来保存优化后的补丁
        output_dir = context.commit.base_dir / "chunk_analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"optimized_{timestamp}.patch"
        
        # 按照文件组织chunks
        file_chunks = {}
        for chunk in valuable_chunks:
            file_path = chunk['file_path']
            if file_path not in file_chunks:
                file_chunks[file_path] = []
            file_chunks[file_path].append(chunk)
        
        # 生成优化后的补丁内容
        with open(output_path, 'w', encoding='utf-8') as f:
            # 写入补丁头部信息
            logger.info(f"context.commit.patch_path: {context.commit.patch_path}")
            with open(context.commit.patch_path, 'r', encoding='utf-8') as original:
                # 复制前几行直到第一个diff
                for line in original:
                    if line.startswith('diff --git'):
                        break
                    f.write(line)
            
            # 为每个文件生成diff
            for file_path, chunks in file_chunks.items():
                # 写入文件头
                f.write(f"diff --git a/{file_path} b/{file_path}\n")
                
                # 查找原始补丁中的文件模式行
                with open(context.commit.patch_path, 'r', encoding='utf-8') as original:
                    found_file = False
                    for line in original:
                        if f"diff --git a/{file_path} b/{file_path}" in line:
                            found_file = True
                            continue
                        
                        if found_file and (line.startswith('new file') or 
                                          line.startswith('deleted file') or
                                          line.startswith('index')):
                            f.write(line)
                        
                        if found_file and line.startswith('diff --git'):
                            break
                
                # 写入文件修改块
                f.write(f"--- a/{file_path}\n")
                f.write(f"+++ b/{file_path}\n")
                
                # 写入每个块
                for chunk in chunks:
                    f.write(chunk['content'])
        
        logger.info(f"生成优化后的补丁文件: {output_path}")
        return output_path
    
    def _extract_function_context(self, file_path: Path, start_line: int, end_line: int) -> str:
        """
        提取给定文件中指定行范围所在函数的上下文
        """
        # 这个方法可以扩展，用于提取函数级上下文
        # 可以使用语言特定的解析器（如ctags）或简单的启发式方法
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 简单示例：向上查找函数开始
            function_start = start_line
            for i in range(start_line - 1, -1, -1):
                if i >= len(lines):
                    continue
                line = lines[i]
                # 简单判断函数开始（这里仅作示例，实际应根据语言特性调整）
                if re.search(r'^\s*(?:static\s+)?(?:\w+\s+)+\w+\s*\([^)]*\)\s*{', line):
                    function_start = i
                    break
            
            # 向下查找函数结束
            function_end = end_line
            brace_count = 0
            for i in range(function_start, len(lines)):
                if i >= len(lines):
                    break
                line = lines[i]
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and i >= end_line:
                    function_end = i
                    break
            
            # 返回函数上下文
            return ''.join(lines[function_start:function_end+1])
        
        except Exception as e:
            logger.error(f"提取函数上下文失败: {e}")
            return ""
    
    def _compare_function_contexts(self, old_context: str, new_context: str) -> bool:
        """
        比较两个函数上下文，判断是否有实质性差异
        """
        # 使用difflib计算差异
        differ = difflib.Differ()
        diff = list(differ.compare(old_context.splitlines(), new_context.splitlines()))
        
        # 检查是否有实质性变化（不仅仅是空白字符）
        for line in diff:
            if line.startswith('+ ') or line.startswith('- '):
                # 去除空白字符后比较
                stripped_line = re.sub(r'\s+', '', line[2:])
                if stripped_line:  # 如果非空，则有实际内容变化
                    return True
        
        return False 