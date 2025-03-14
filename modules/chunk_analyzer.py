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
import shutil
import uuid

from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext
from .patch_adapter import PatchAdapterModule


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
            
            # 2. 分类块为简单行号修改和需要LLM处理的复杂修改
            simple_chunks, complex_chunks = self._classify_chunks(chunks, context)
            logger.info(f"简单行号修改块: {len(simple_chunks)}, 需要LLM处理的块: {len(complex_chunks)}")
            
            # 3. 为简单块创建适配后的补丁
            simple_patch_path = None
            if simple_chunks:
                simple_patch_path = self._process_simple_chunks(simple_chunks, context)
                logger.info(f"简单块生成的补丁: {simple_patch_path}")
            
            # 4. 为复杂块创建需要LLM处理的补丁
            complex_patch_path = None
            if complex_chunks:
                complex_patch_path = self._generate_complex_patch(complex_chunks, context)
                logger.info(f"复杂块生成的补丁: {complex_patch_path}")
                
                # 更新上下文中的补丁路径，以便LLM适配器使用
                context.commit.optimized_patch_path = complex_patch_path
            
            # 5. 保存分析结果
            analysis_result = {
                'original_patch': str(patch_path),
                'simple_patch': str(simple_patch_path) if simple_patch_path else None,
                'complex_patch': str(complex_patch_path) if complex_patch_path else None,
                'total_chunks': len(chunks),
                'simple_chunks': len(simple_chunks),
                'complex_chunks': len(complex_chunks),
                'optimization_rate': (len(simple_chunks) / len(chunks)) if chunks else 0,
                'timestamp': datetime.now().isoformat()
            }
            
            # 将结果写入上下文
            context.chunk_analyzer_result = analysis_result
            
            # 存储简单补丁路径，以便后续合并
            if simple_patch_path:
                context.simple_patch_path = simple_patch_path
            
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
    
    def _classify_chunks(self, chunks: List[Dict[str, Any]], context: ModuleContext) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        将补丁块分类为简单行号修改和需要LLM处理的复杂修改
        
        返回两个列表:
        1. 简单行号修改的chunks
        2. 需要LLM处理的复杂chunks
        """
        simple_chunks = []
        complex_chunks = []
        
        repo_path = context.config.repo_path  # 目标仓库路径
        
        # 从上下文获取新旧版本的commit ID
        target_commit = context.commit.commit_sha  # 目标版本(旧版本)
        upstream_commit = context.commit.upstream_commit  # 上游版本(新版本)
        
        logger.info(f"分析补丁块，目标版本: {target_commit}，上游版本: {upstream_commit}")
        
        for chunk in chunks:
            file_path = chunk['file_path']
            
            # 检查文件是否是新增或删除的情况
            is_new_file = chunk.get('chunk_type') == 'new_file'
            is_deleted_file = chunk.get('chunk_type') == 'deleted_file'
            
            if is_new_file or is_deleted_file:
                complex_chunks.append(chunk)
                continue
            
            try:
                # 使用git命令获取新旧版本的文件内容
                old_content = self._get_file_content_at_commit(file_path, target_commit, repo_path)
                new_content = self._get_file_content_at_commit(file_path, upstream_commit, repo_path)
                
                if old_content is None or new_content is None:
                    logger.warning(f"无法获取文件内容: {file_path}")
                    complex_chunks.append(chunk)
                    continue
                
                # 创建临时文件来存储内容
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.old') as old_file, \
                     tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.new') as new_file:
                    old_file.write(old_content)
                    new_file.write(new_content)
                    old_file_path = Path(old_file.name)
                    new_file_path = Path(new_file.name)
                
                try:
                    # 判断函数上下文是否只有行号变化
                    is_line_change_only = self._is_line_number_change_only(
                        chunk, old_file_path, new_file_path)
                    
                    if is_line_change_only:
                        logger.info(f"发现简单行号修改: {file_path} at {chunk.get('old_start')}-{chunk.get('old_start') + chunk.get('old_count')}")
                        simple_chunks.append(chunk)
                    else:
                        logger.info(f"发现复杂修改需要LLM处理: {file_path} at {chunk.get('old_start')}-{chunk.get('old_start') + chunk.get('old_count')}")
                        complex_chunks.append(chunk)
                finally:
                    # 清理临时文件
                    if old_file_path.exists():
                        os.unlink(old_file_path)
                    if new_file_path.exists():
                        os.unlink(new_file_path)
            
            except Exception as e:
                logger.error(f"分析块时出错: {e}, 文件: {file_path}")
                import traceback
                logger.error(traceback.format_exc())
                complex_chunks.append(chunk)  # 出错时视为复杂修改
        
        return simple_chunks, complex_chunks
    
    def _get_file_content_at_commit(self, file_path: str, commit: str, repo_path: Path) -> Optional[str]:
        """
        获取特定提交中文件的内容
        
        Args:
            file_path: 文件路径
            commit: 提交ID
            repo_path: 仓库路径
            
        Returns:
            文件内容，如果文件不存在则返回None
        """
        try:
            command = ["git", "show", f"{commit}:{file_path}"]
            result = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                if "fatal: path" in result.stderr and "does not exist" in result.stderr:
                    logger.warning(f"文件在提交 {commit} 中不存在: {file_path}")
                    return None
                logger.error(f"获取文件内容时出错: {result.stderr}")
                return None
            
            return result.stdout
            
        except Exception as e:
            logger.error(f"执行git命令出错: {e}")
            return None
    
    # TODO
    def _is_line_number_change_only(self, chunk: Dict[str, Any], target_file_path: Path, upstream_file_path: Path) -> bool:
        """
        判断chunk是否只是行号变化
        
        1. 提取修改所在的内容
        2. 在目标文件中找到匹配的内容位置
        3. 判断修改是否仅为行号变化
        """
        # 如果是文件模式变化或二进制文件，直接认为是复杂修改
        if chunk.get('chunk_type') in ['binary', 'new_file', 'deleted_file']:
            return False
        
        # 提取修改内容
        removed_lines, added_lines = self._extract_chunk_changes(chunk)
        
        # 如果不是纯删除或纯添加，可能是内容变化，不是简单行号修改
        if removed_lines and added_lines:
            return False
        
        try:
            # 读取目标文件(旧版本)和上游文件(新版本)
            with open(target_file_path, 'r', encoding='utf-8') as f:
                target_lines = f.readlines()
            
            with open(upstream_file_path, 'r', encoding='utf-8') as f:
                upstream_lines = f.readlines()
            
            # 处理删除行的情况
            if removed_lines and not added_lines:
                # 在目标文件中查找要删除的内容
                target_position = self._find_content_position(target_lines, removed_lines)
                if target_position < 0:
                    logger.warning(f"在目标文件中未找到要删除的内容: {target_file_path}")
                    return False
                
                # 在上游文件中确认内容已被删除
                upstream_position = self._find_content_position(upstream_lines, removed_lines)
                return upstream_position < 0  # 如果上游找不到这些行，说明确实被删除了
            
            # 处理添加行的情况
            elif added_lines and not removed_lines:
                # 在上游文件中确认内容存在
                upstream_position = self._find_content_position(upstream_lines, added_lines)
                if upstream_position < 0:
                    logger.warning(f"在上游文件中未找到添加的内容: {upstream_file_path}")
                    return False
                
                # 在目标文件中确认内容不存在
                target_position = self._find_content_position(target_lines, added_lines)
                return target_position < 0  # 如果目标中找不到这些行，说明确实是新增
            
            return False
        
        except Exception as e:
            logger.error(f"判断行号变化时出错: {e}")
            return False
    
    def _extract_chunk_changes(self, chunk: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """
        从补丁块中提取删除和添加的行
        返回: (删除的行列表, 添加的行列表)
        """
        removed_lines = []
        added_lines = []
        
        # 跳过hunk头
        content_lines = chunk.get('content', '').splitlines()[1:]
        
        for line in content_lines:
            if line.startswith('-') and not line.startswith('---'):
                removed_lines.append(line[1:])
            elif line.startswith('+') and not line.startswith('+++'):
                added_lines.append(line[1:])
        
        return removed_lines, added_lines
    
    def _find_content_position(self, file_lines: List[str], content_lines: List[str]) -> int:
        """
        在文件中查找内容的位置
        返回: 找到的行号(0-based)，如果未找到则返回-1
        """
        if not content_lines:
            return -1
        
        # 清理内容行（移除尾部空白）
        cleaned_content = [line.rstrip() for line in content_lines]
        
        # 在文件中搜索匹配内容
        for i in range(len(file_lines) - len(cleaned_content) + 1):
            match = True
            for j, content_line in enumerate(cleaned_content):
                file_line = file_lines[i + j].rstrip()
                if file_line != content_line:
                    match = False
                    break
            
            if match:
                return i
        
        return -1
    
    def _process_simple_chunks(self, simple_chunks: List[Dict[str, Any]], context: ModuleContext) -> Path:
        """
        处理简单行号修改的chunks，生成适配后的补丁
        
        步骤:
        1. 创建临时分支
        2. 应用行号修改到目标仓库
        3. 提交并生成补丁
        4. 清理临时分支
        """
        repo_path = context.config.repo_path
        output_dir = context.commit.base_dir / "chunk_analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成临时分支名
        branch_name = f"chunk_analyzer_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        try:
            # 创建临时分支
            self._run_git_command(["checkout", "-b", branch_name], repo_path)
            logger.info(f"已创建临时分支: {branch_name}")
            
            # 应用每个简单块的修改
            for chunk in simple_chunks:
                self._apply_simple_chunk(chunk, context)
            
            # 提交修改
            self._run_git_command(["add", "."], repo_path)
            commit_msg = f"Apply simple line number changes from upstream patch"
            self._run_git_command(["commit", "-m", commit_msg], repo_path)
            
            # 生成补丁
            patch_path = output_dir / f"simple_changes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.patch"
            self._run_git_command(["format-patch", "-1", "--stdout"], repo_path, stdout=patch_path)
            
            logger.info(f"生成简单修改补丁: {patch_path}")
            return patch_path
            
        except Exception as e:
            logger.error(f"处理简单块时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
            
        finally:
            # 清理临时分支
            try:
                self._run_git_command(["checkout", context.config.target_version], repo_path)
                self._run_git_command(["branch", "-D", branch_name], repo_path)
                logger.info(f"已清理临时分支: {branch_name}")
            except Exception as e:
                logger.error(f"清理临时分支时出错: {e}")
    
    def _apply_simple_chunk(self, chunk: Dict[str, Any], context: ModuleContext) -> None:
        """应用简单行号修改的块到目标文件"""
        file_path = chunk['file_path']
        target_file_path = Path(context.config.repo_path) / file_path
        
        # 提取修改内容
        removed_lines, added_lines = self._extract_chunk_changes(chunk)
        
        # 确保目标目录存在
        target_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取原始文件
        if target_file_path.exists():
            with open(target_file_path, 'r', encoding='utf-8') as f:
                file_lines = f.readlines()
        else:
            # 如果文件不存在，可能是新文件
            logger.warning(f"目标文件不存在，可能是新文件: {file_path}")
            file_lines = []
        
        # 处理删除行
        if removed_lines and not added_lines:
            # 在目标文件中找到要删除的行
            position = self._find_content_position(file_lines, removed_lines)
            if position >= 0:
                # 删除这些行
                file_lines = file_lines[:position] + file_lines[position + len(removed_lines):]
                logger.info(f"从文件 {file_path} 的第 {position+1} 行删除了 {len(removed_lines)} 行")
            else:
                logger.warning(f"在文件 {file_path} 中未找到要删除的内容")
        
        # 处理添加行
        elif added_lines and not removed_lines:
            # 根据chunk的上下文确定添加位置
            context_before, context_after = self._extract_chunk_context(chunk)
            insert_position = 0
            
            # 基于前置上下文确定位置
            if context_before:
                position = self._find_content_position(file_lines, context_before)
                if position >= 0:
                    insert_position = position + len(context_before)
            
            # 基于后置上下文确定位置
            elif context_after:
                position = self._find_content_position(file_lines, context_after)
                if position >= 0:
                    insert_position = position
            
            # 如果没有找到匹配的上下文，尝试根据hunk头中的行号定位
            if insert_position == 0 and file_lines:
                old_start = chunk.get('old_start', 1)
                if 1 <= old_start <= len(file_lines):
                    insert_position = old_start - 1
                    logger.info(f"根据行号定位插入点: {insert_position+1}")
            
            # 添加内容
            if insert_position >= 0:
                file_lines = file_lines[:insert_position] + [line + '\n' for line in added_lines] + file_lines[insert_position:]
                logger.info(f"在文件 {file_path} 的第 {insert_position+1} 行添加了 {len(added_lines)} 行")
            else:
                logger.warning(f"无法在文件 {file_path} 中找到合适的插入位置，尝试追加到文件末尾")
                file_lines.extend([line + '\n' for line in added_lines])
        
        # 写入修改后的文件
        with open(target_file_path, 'w', encoding='utf-8') as f:
            f.writelines(file_lines)
        
        logger.info(f"已应用简单块修改到: {file_path}")
    
    def _extract_chunk_context(self, chunk: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """
        从补丁块中提取上下文行
        返回: (前置上下文行, 后置上下文行)
        """
        context_before = []
        context_after = []
        content_lines = chunk.get('content', '').splitlines()[1:]  # 跳过hunk头
        
        in_before_context = True
        
        for line in content_lines:
            # 处理前置上下文
            if in_before_context and not (line.startswith('+') or line.startswith('-')):
                context_before.append(line[1:] if line.startswith(' ') else line)
            # 遇到修改行后，开始收集后置上下文
            elif line.startswith('+') or line.startswith('-'):
                in_before_context = False
            # 收集后置上下文
            elif not in_before_context:
                context_after.append(line[1:] if line.startswith(' ') else line)
        
        return context_before, context_after
    
    def _generate_complex_patch(self, complex_chunks: List[Dict[str, Any]], context: ModuleContext) -> Path:
        """
        根据复杂块生成需要LLM处理的补丁文件
        """
        # 创建临时目录来保存需要LLM处理的补丁
        output_dir = context.commit.base_dir / "chunk_analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"complex_{timestamp}.patch"
        
        # 按照文件组织chunks
        file_chunks = {}
        for chunk in complex_chunks:
            file_path = chunk['file_path']
            if file_path not in file_chunks:
                file_chunks[file_path] = []
            file_chunks[file_path].append(chunk)
        
        # 生成需要LLM处理的补丁内容
        with open(output_path, 'w', encoding='utf-8') as f:
            # 写入补丁头部信息
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
                for chunk in sorted(chunks, key=lambda x: x.get('old_start', 0)):
                    f.write(chunk['content'])
        
        logger.info(f"生成需要LLM处理的补丁文件: {output_path}")
        return output_path
    
    def _extract_function_context(self, file_path: Path, start_line: int, end_line: int) -> str:
        """
        提取给定文件中指定行范围所在函数的上下文
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if start_line <= 0 or start_line > len(lines):
                return ""
                
            # 向上查找函数开始
            function_start = start_line - 1  # 转为0-indexed
            for i in range(function_start, -1, -1):
                line = lines[i].strip()
                # 判断函数开始（支持C/C++风格函数声明）
                if re.search(r'^\s*(?:static\s+)?(?:\w+\s+)+\w+\s*\([^)]*\)\s*(?:{|$)', line):
                    function_start = i
                    break
                # 如果遇到另一个函数结束，说明不在函数内
                if line == '}':
                    return ""
            
            # 向下查找函数结束
            function_end = min(end_line - 1, len(lines) - 1)  # 转为0-indexed
            brace_count = 0
            in_function = False
            
            # 从函数声明开始扫描
            for i in range(function_start, len(lines)):
                line = lines[i].strip()
                
                # 检测函数体开始
                if '{' in line:
                    in_function = True
                
                if in_function:
                    brace_count += line.count('{') - line.count('}')
                    if brace_count <= 0 and i >= function_end:
                        function_end = i
                        break
            
            # 检查是否找到了完整函数
            if not in_function or brace_count > 0:
                return ""
                
            # 返回函数上下文
            return ''.join(lines[function_start:function_end+1])
            
        except Exception as e:
            logger.error(f"提取函数上下文失败: {e}")
            return ""
    
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
    
    def _run_git_command(self, args: List[str], cwd: Path, stdout=None) -> str:
        """运行git命令并返回输出"""
        try:
            if stdout:
                with open(stdout, 'w') as f:
                    subprocess.run(
                        ["git"] + args,
                        cwd=cwd,
                        check=True,
                        stdout=f,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                return ""
            else:
                result = subprocess.run(
                    ["git"] + args,
                    cwd=cwd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Git命令执行失败: {e.stderr}")
            raise
    
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