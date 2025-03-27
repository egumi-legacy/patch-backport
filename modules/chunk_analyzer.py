from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import re
import os
import subprocess
import tempfile
from datetime import datetime
from loguru import logger
import json
import shutil
import uuid

from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext

class ChunkAnalyzerModule(BaseModule):
    """补丁分块分析模块 - 将补丁分解为独立的chunk以便利用git的模糊匹配功能"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.CHUNK_ANALYZER
        self.name = "chunk_analyzer"
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行补丁分块分析"""
        if not self._should_run(context):
            return context
            
        start_time = datetime.now()
        
        try:
            # 只有当direct_apply失败时才进行处理
            if not context.direct_apply_result or context.direct_apply_result.get('success', True):
                logger.info("直接应用成功或未执行，跳过补丁分块分析")
                return context
                
            # 获取补丁文件路径
            patch_path = None
            if context.direct_apply_result.get('patch_path'):
                patch_path = Path(context.direct_apply_result.get('patch_path'))
                if not patch_path.exists():
                    logger.warning(f"补丁文件不存在: {patch_path}，尝试使用commit.patch_path")
                    patch_path = None
            
            if not patch_path:
                patch_path = Path(context.commit.patch_path)
                if not patch_path or not patch_path.exists():
                    raise ValueError("没有找到有效的补丁文件路径")
            
            # 确保使用绝对路径
            patch_path = Path(patch_path.absolute())
            logger.info(f"开始分析补丁: {patch_path}")
            
            # 1. 将补丁分解为块
            chunks = self._split_patch_into_chunks(patch_path)
            logger.info(f"补丁被分解为 {len(chunks)} 个块")
            
            # 2. 为每个chunk创建单独的补丁文件
            chunk_patches = self._create_chunk_patches(chunks, context)
            logger.info(f"已为 {len(chunk_patches)} 个块创建单独的补丁文件")
            
            # 3. 尝试应用每个单独的chunk补丁
            applied_chunks = self._apply_chunk_patches(chunk_patches, context)
            logger.info(f"成功应用了 {len(applied_chunks)} 个块补丁，总共 {len(chunk_patches)} 个")
            
            # 4. 为剩余的未应用成功的块创建一个合并补丁
            remaining_patch = None
            if len(applied_chunks) < len(chunk_patches):
                remaining_patch = self._create_remaining_patch(chunk_patches, applied_chunks, context)
                if remaining_patch:
                    remaining_patch = remaining_patch.absolute()
                    logger.info(f"创建了包含 {len(chunk_patches) - len(applied_chunks)} 个未应用块的剩余补丁: {remaining_patch}")
                else:
                    logger.warning("没有创建剩余补丁，可能所有块都已应用或出现错误")
            else:
                logger.info("所有块补丁都已成功应用，无需创建剩余补丁")
            
            # 5. 保存分析结果
            analysis_result = {
                'original_patch': str(patch_path),
                'total_chunks': len(chunks),
                'applied_chunks': len(applied_chunks),
                'applied_chunk_patches': [str(p.absolute()) for p in applied_chunks],
                'remaining_patch': str(remaining_patch) if remaining_patch else None,
                'timestamp': datetime.now().isoformat()
            }
            
            # 将结果写入上下文
            context.chunk_analyzer_result = analysis_result
            
            # 将剩余补丁路径存储到上下文中，供后续模块使用
            if remaining_patch:
                context.commit.optimized_patch_path = remaining_patch
                logger.info(f"已将剩余补丁路径存储到上下文: {remaining_patch}")
            
            # 更新指标
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"补丁分块分析完成，耗时: {execution_time:.2f}秒")
            self._update_metrics(
                success=True,
                execution_time=execution_time
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
        
        # 保存评估信息
        self._save_evaluation_info(context)
        
        return context
    
    def _split_patch_into_chunks(self, patch_path: Path) -> List[Dict[str, Any]]:
        """
        将补丁文件分解为独立的代码块
        
        返回格式:
        [
            {
                'file_path': 'path/to/file',
                'chunk_type': 'modification/addition/deletion',
                'old_start': line_number,
                'old_count': lines_count,
                'new_start': line_number,
                'new_count': lines_count,
                'content': 'chunk content with @@ header'
            },
            ...
        ]
        """
        chunks = []
        current_file = None
        current_chunk = None
        chunk_content = []
        file_header_lines = []
        in_file_header = False
        
        try:
            # 确保使用绝对路径
            abs_patch_path = patch_path.absolute()
            logger.info(f"开始分解补丁文件: {abs_patch_path}")
            
            with open(abs_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            logger.info(f"补丁文件包含 {len(lines)} 行内容")
            
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
                        logger.info(f"发现修改文件: {current_file}")
                    
                    current_chunk = None
                    file_header_lines = [line]
                    in_file_header = True
                
                # 收集文件头部信息（index行、mode行等）
                elif in_file_header and (line.startswith('index ') or 
                                       line.startswith('new file mode') or 
                                       line.startswith('deleted file mode') or
                                       line.startswith('old mode') or
                                       line.startswith('new mode') or
                                       line.startswith('--- ') or
                                       line.startswith('+++ ')):
                    file_header_lines.append(line)
                
                # 检测hunk头
                elif line.startswith('@@'):
                    # 结束文件头收集
                    in_file_header = False
                    
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
                            'file_header': ''.join(file_header_lines)
                        }
                        
                        logger.info(f"发现修改块: {current_file} @@ -{old_start},{old_count} +{new_start},{new_count} @@ ({chunk_type})")
                    
                    # 将hunk头添加到chunk内容
                    chunk_content.append(line)
                
                # 收集chunk内容
                elif current_chunk:
                    chunk_content.append(line)
            
            # 保存最后一个chunk
            if current_chunk:
                current_chunk['content'] = ''.join(chunk_content)
                chunks.append(current_chunk)
        
        except Exception as e:
            logger.error(f"分割补丁出错: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            raise
        
        logger.info(f"补丁分解完成，共找到 {len(chunks)} 个修改块")
        return chunks
    
    def _create_chunk_patches(self, chunks: List[Dict[str, Any]], context: ModuleContext) -> List[Path]:
        """
        为每个chunk创建单独的补丁文件
        
        :param chunks: 分解后的补丁块列表
        :param context: 模块上下文
        :return: 创建的补丁文件路径列表
        """
        output_dir = context.commit.base_dir / "chunk_patches"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        chunk_patches = []
        
        # 补丁头部（从原始补丁提取）
        patch_header = ""
        original_patch_path = Path(context.commit.patch_path).absolute()
        logger.info(f"从原始补丁提取头部信息: {original_patch_path}")
        
        with open(original_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith('diff --git'):
                    break
                patch_header += line
        
        # 为每个chunk创建独立的补丁文件
        for i, chunk in enumerate(chunks):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            chunk_id = f"{i+1:03d}"
            patch_path = output_dir / f"chunk_{chunk_id}_{timestamp}.patch"
            abs_patch_path = patch_path.absolute()
            
            with open(abs_patch_path, 'w', encoding='utf-8') as f:
                # 写入补丁头部
                f.write(patch_header)
                
                # 写入文件头部
                f.write(chunk['file_header'])
                
                # 写入chunk内容
                f.write(chunk['content'])
            
            chunk_patches.append(patch_path)
            logger.info(f"创建块补丁文件: {abs_patch_path} (修改文件: {chunk['file_path']})")
        
        return chunk_patches
    
    def _apply_chunk_patches(self, chunk_patches: List[Path], context: ModuleContext) -> List[Path]:
        """
        尝试应用每个chunk补丁
        
        :param chunk_patches: chunk补丁文件路径列表
        :param context: 模块上下文
        :return: 成功应用的补丁文件路径列表
        """
        repo_path = context.config.repo_path
        applied_patches = []
        
        # 获取当前分支
        current_branch = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)
        logger.info(f"当前分支: {current_branch}")
        
        # 创建测试分支
        test_branch = f"chunk_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        try:
            # 创建测试分支
            self._run_git_command(["checkout", "-b", test_branch], repo_path)
            logger.info(f"创建测试分支: {test_branch}")
            
            # 尝试应用每个chunk补丁
            for patch_path in chunk_patches:
                # 确保使用绝对路径
                abs_patch_path = patch_path.absolute()
                logger.info(f"尝试应用补丁块: {abs_patch_path}")
                
                # 1. 首先尝试使用git apply --ignore-space-change（更灵活的空白处理）
                try:
                    logger.info("方法1: 尝试 git apply --ignore-space-change")
                    self._run_git_command(["apply", "--ignore-space-change", "--ignore-whitespace", str(abs_patch_path)], repo_path)
                    
                    # 应用成功
                    applied_patches.append(patch_path)
                    logger.info(f"成功应用块补丁(方法1): {patch_path.name}")
                    
                    # 提交更改
                    self._run_git_command(["add", "."], repo_path)
                    self._run_git_command(["commit", "-m", f"Applied chunk patch: {patch_path.name}"], repo_path)
                    continue  # 成功应用，继续下一个补丁
                except Exception as e:
                    logger.info(f"方法1失败: {e}")
                    # 恢复到干净状态
                    self._run_git_command(["reset", "--hard"], repo_path)
                
                # 2. 尝试使用git apply --reject（允许部分应用）
                try:
                    logger.info("方法2: 尝试 git apply --reject")
                    self._run_git_command(["apply", "--reject", "--ignore-whitespace", "--ignore-space-change", str(abs_patch_path)], repo_path)
                    # 检查是否有拒绝文件
                    reject_files = list(Path(repo_path).glob("**/*.rej"))
                    
                    if not reject_files:
                        # 完全应用成功
                        applied_patches.append(patch_path)
                        logger.info(f"成功应用块补丁(方法2): {patch_path.name}")
                        
                        # 提交更改
                        self._run_git_command(["add", "."], repo_path)
                        self._run_git_command(["commit", "-m", f"Applied chunk patch: {patch_path.name}"], repo_path)
                        continue  # 成功应用，继续下一个补丁
                    else:
                        # 有拒绝部分，清理并恢复
                        logger.info(f"块补丁 {patch_path.name} 有拒绝部分，发现 {len(reject_files)} 个拒绝文件")
                        self._run_git_command(["reset", "--hard"], repo_path)
                        
                        # 删除拒绝文件
                        for reject_file in reject_files:
                            os.remove(reject_file)
                except Exception as e:
                    logger.info(f"方法2失败: {e}")
                    # 恢复到干净状态
                    self._run_git_command(["reset", "--hard"], repo_path)
                
                # 3. 尝试使用git am
                try:
                    logger.info("方法3: 尝试 git am --3way")
                    result = subprocess.run(
                        ["git", "am", "--3way", str(abs_patch_path)],
                        cwd=repo_path,
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        # git am 成功
                        applied_patches.append(patch_path)
                        logger.info(f"成功应用块补丁(方法3): {patch_path.name}")
                        continue  # 成功应用，继续下一个补丁
                    else:
                        # 中止 git am
                        subprocess.run(
                            ["git", "am", "--abort"],
                            cwd=repo_path,
                            capture_output=True
                        )
                        logger.info(f"方法3失败: {result.stderr}")
                except Exception as am_error:
                    logger.info(f"方法3异常: {am_error}")
                    # 中止 git am
                    try:
                        subprocess.run(
                            ["git", "am", "--abort"],
                            cwd=repo_path,
                            capture_output=True
                        )
                    except:
                        pass
                
                # 4. 尝试使用系统patch命令（通常有更好的模糊匹配能力）
                try:
                    logger.info("方法4: 尝试系统 patch 命令")
                    
                    # 解析补丁块，获取文件路径
                    with open(abs_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                        patch_content = f.read()
                    
                    # 提取文件路径
                    file_match = re.search(r'diff --git a/(.*) b/', patch_content)
                    if not file_match:
                        logger.warning(f"无法从补丁提取文件路径: {patch_path.name}")
                        continue
                    
                    target_file = file_match.group(1)
                    target_file_path = Path(repo_path) / target_file
                    
                    # 检查目标文件是否存在
                    if not target_file_path.exists():
                        logger.warning(f"目标文件不存在: {target_file}，尝试查找匹配文件")
                        
                        # 提取文件名，尝试查找文件
                        file_name = Path(target_file).name
                        logger.info(f"尝试查找文件: {file_name}")
                        
                        # 使用find命令查找文件
                        find_result = subprocess.run(
                            ["find", ".", "-name", file_name],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if find_result.returncode == 0 and find_result.stdout.strip():
                            # 找到可能的文件
                            possible_files = find_result.stdout.strip().split('\n')
                            logger.info(f"找到可能的匹配文件: {possible_files}")
                            
                            if len(possible_files) == 1:
                                # 只有一个匹配，使用它
                                target_file = possible_files[0].lstrip('./\\')
                                target_file_path = Path(repo_path) / target_file
                                logger.info(f"使用找到的文件: {target_file}")
                            elif len(possible_files) > 1:
                                # 多个匹配，尝试找到最相似的
                                max_similarity = 0
                                best_match = None
                                
                                for found_file in possible_files:
                                    similarity = self._path_similarity(target_file, found_file.lstrip('./\\'))
                                    if similarity > max_similarity:
                                        max_similarity = similarity
                                        best_match = found_file.lstrip('./\\')
                                
                                if best_match:
                                    target_file = best_match
                                    target_file_path = Path(repo_path) / target_file
                                    logger.info(f"使用最相似的文件: {target_file} (相似度: {max_similarity:.2f})")
                                else:
                                    logger.warning(f"找不到合适的匹配文件")
                                    continue
                            else:
                                logger.warning(f"找不到匹配的文件")
                                continue
                        else:
                            logger.warning(f"找不到匹配的文件")
                            continue
                    
                    # 创建临时补丁文件（只包含hunk部分，不包含git头信息）
                    temp_dir = tempfile.mkdtemp()
                    temp_patch = Path(temp_dir) / "temp.patch"
                    
                    # 提取第一个hunk
                    hunk_match = re.search(r'(@@ .+?@@.*?)(?=\n@@|\Z)', patch_content, re.DOTALL)
                    if not hunk_match:
                        logger.warning(f"无法从补丁提取hunk: {patch_path.name}")
                        shutil.rmtree(temp_dir)
                        continue
                    
                    # 写入临时补丁文件
                    with open(temp_patch, 'w', encoding='utf-8') as f:
                        f.write(hunk_match.group(1))
                    
                    # 使用系统patch命令（增加模糊搜索范围，-F参数表示模糊程度）
                    logger.info(f"准备对文件 {target_file} 应用补丁 {temp_patch}")
                    
                    # 直接以二进制模式读取补丁内容，避免编码/解码问题
                    with open(temp_patch, 'rb') as patch_file:
                        patch_binary_content = patch_file.read()
                    
                    # 使用系统patch命令，使用更高的fuzz值（100）来增强模糊匹配能力
                    # 使用--ignore-whitespace忽略空白差异
                    patch_result = subprocess.run(
                        ["patch", "-p1", "-F", "100", "--fuzz=100", "--ignore-whitespace", "-f", target_file],
                        cwd=repo_path,
                        input=patch_binary_content,  # 直接使用二进制数据
                        capture_output=True,
                        text=True
                    )
                    
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    
                    if patch_result.returncode == 0:
                        # patch 命令成功
                        applied_patches.append(patch_path)
                        logger.info(f"成功应用块补丁(方法4): {patch_path.name}")
                        logger.info(f"Patch命令输出: {patch_result.stdout}")
                        
                        # 提交更改
                        self._run_git_command(["add", "."], repo_path)
                        self._run_git_command(["commit", "-m", f"Applied chunk patch with patch command: {patch_path.name}"], repo_path)
                    else:
                        logger.info(f"方法4失败: {patch_result.stderr}")
                        # 恢复到干净状态
                        self._run_git_command(["reset", "--hard"], repo_path)
                except Exception as patch_error:
                    logger.info(f"方法4异常: {patch_error}")
                    # 恢复到干净状态
                    self._run_git_command(["reset", "--hard"], repo_path)
                
                # 5. 最后的尝试：调整补丁行号
                try:
                    logger.info("方法5: 尝试调整补丁行号")
                    
                    # 解析补丁块，获取文件路径和行号信息
                    with open(abs_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                        patch_content = f.read()
                    
                    # 提取文件路径
                    file_match = re.search(r'diff --git a/(.*) b/', patch_content)
                    if not file_match:
                        logger.warning(f"无法从补丁提取文件路径: {patch_path.name}")
                        continue
                    
                    target_file = file_match.group(1)
                    target_file_path = Path(repo_path) / target_file
                    
                    # 检查目标文件是否存在，必要时查找匹配文件
                    if not target_file_path.exists():
                        file_name = Path(target_file).name
                        
                        # 使用find命令查找文件
                        find_result = subprocess.run(
                            ["find", ".", "-name", file_name],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if find_result.returncode == 0 and find_result.stdout.strip():
                            # 找到可能的文件
                            possible_files = find_result.stdout.strip().split('\n')
                            
                            if len(possible_files) == 1:
                                target_file = possible_files[0].lstrip('./\\')
                                target_file_path = Path(repo_path) / target_file
                            elif len(possible_files) > 1:
                                # 多个匹配，尝试找到最相似的
                                max_similarity = 0
                                best_match = None
                                
                                for found_file in possible_files:
                                    similarity = self._path_similarity(target_file, found_file.lstrip('./\\'))
                                    if similarity > max_similarity:
                                        max_similarity = similarity
                                        best_match = found_file.lstrip('./\\')
                                
                                if best_match:
                                    target_file = best_match
                                    target_file_path = Path(repo_path) / target_file
                                else:
                                    continue
                            else:
                                continue
                        else:
                            continue
                    
                    # 读取目标文件内容
                    if target_file_path.exists():
                        with open(target_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            target_lines = f.readlines()
                    else:
                        continue
                    
                    # 提取补丁中的修改行（不带+/-）
                    hunk_match = re.search(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@(.*?)(?=\n@@|\Z)', patch_content, re.DOTALL)
                    if not hunk_match:
                        continue
                    
                    old_start = int(hunk_match.group(1))
                    old_count = int(hunk_match.group(2))
                    new_start = int(hunk_match.group(3))
                    new_count = int(hunk_match.group(4))
                    hunk_content = hunk_match.group(5)
                    
                    # 提取要删除的行
                    removed_lines = []
                    for line in hunk_content.splitlines():
                        if line.startswith('-') and not line.startswith('---'):
                            removed_lines.append(line[1:].strip())
                    
                    # 在目标文件中查找这些行
                    for start_line in range(1, len(target_lines) + 1):
                        match_count = 0
                        for i, line in enumerate(removed_lines):
                            if start_line + i <= len(target_lines) and line.strip() == target_lines[start_line + i - 1].strip():
                                match_count += 1
                        
                        # 如果找到匹配，创建调整行号的补丁
                        if match_count >= len(removed_lines) * 0.8:  # 80%匹配就认为是相同的块
                            logger.info(f"找到匹配行，原始行号: {old_start}，新行号: {start_line}")
                            
                            # 创建新的补丁内容
                            adjusted_patch_content = patch_content.replace(
                                f"@@ -{old_start},{old_count} +{new_start},{new_count} @@",
                                f"@@ -{start_line},{old_count} +{start_line},{new_count} @@"
                            )
                            
                            # 创建临时补丁文件
                            temp_dir = tempfile.mkdtemp()
                            adjusted_patch_path = Path(temp_dir) / "adjusted.patch"
                            
                            with open(adjusted_patch_path, 'w', encoding='utf-8') as f:
                                f.write(adjusted_patch_content)
                            
                            # 尝试应用调整后的补丁
                            try:
                                logger.info(f"尝试应用调整行号后的补丁: {adjusted_patch_path}")
                                self._run_git_command(["apply", "--ignore-space-change", "--ignore-whitespace", str(adjusted_patch_path)], repo_path)
                                
                                # 应用成功
                                applied_patches.append(patch_path)
                                logger.info(f"成功应用块补丁(方法5): {patch_path.name}")
                                
                                # 提交更改
                                self._run_git_command(["add", "."], repo_path)
                                self._run_git_command(["commit", "-m", f"Applied chunk patch with adjusted line numbers: {patch_path.name}"], repo_path)
                                
                                # 清理临时目录
                                shutil.rmtree(temp_dir)
                                break
                            except Exception as e:
                                logger.info(f"尝试调整行号失败: {e}")
                                # 恢复到干净状态
                                self._run_git_command(["reset", "--hard"], repo_path)
                                
                                # 清理临时目录
                                shutil.rmtree(temp_dir)
                    
                except Exception as adjust_error:
                    logger.info(f"方法5异常: {adjust_error}")
                    # 恢复到干净状态
                    self._run_git_command(["reset", "--hard"], repo_path)
                
                # 6. 最后的尝试：使用更强大的patch选项组合
                try:
                    logger.info("方法6: 尝试使用更多patch选项组合")
                    
                    # 解析补丁块，获取文件路径
                    with open(abs_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                        patch_content = f.read()
                    
                    # 提取文件路径
                    file_match = re.search(r'diff --git a/(.*) b/', patch_content)
                    if not file_match:
                        logger.warning(f"无法从补丁提取文件路径: {patch_path.name}")
                        continue
                    
                    target_file = file_match.group(1)
                    target_file_path = Path(repo_path) / target_file
                    
                    # 检查目标文件是否存在，必要时查找匹配文件
                    if not target_file_path.exists():
                        file_name = Path(target_file).name
                        
                        # 使用grep进行更广泛的搜索
                        grep_cmd = ["grep", "-r", "--include", f"*{file_name}*", "--files-with-matches", ".", "."]
                        logger.info(f"使用grep搜索相似文件: {' '.join(grep_cmd)}")
                        
                        grep_result = subprocess.run(
                            grep_cmd,
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if grep_result.returncode == 0 and grep_result.stdout.strip():
                            # 找到可能的文件
                            possible_files = grep_result.stdout.strip().split('\n')
                            logger.info(f"grep找到可能的匹配文件: {possible_files}")
                            
                            # 使用相似度找出最佳匹配
                            max_similarity = 0
                            best_match = None
                            
                            for found_file in possible_files:
                                similarity = self._path_similarity(target_file, found_file.lstrip('./\\'))
                                if similarity > max_similarity:
                                    max_similarity = similarity
                                    best_match = found_file.lstrip('./\\')
                            
                            if best_match:
                                target_file = best_match
                                target_file_path = Path(repo_path) / target_file
                                logger.info(f"使用最相似的文件: {target_file} (相似度: {max_similarity:.2f})")
                            else:
                                logger.warning(f"找不到合适的匹配文件")
                                continue
                        else:
                            logger.warning(f"grep未找到匹配的文件")
                            continue
                    
                    # 创建临时目录和修改过的补丁文件
                    temp_dir = tempfile.mkdtemp()
                    adapted_patch = Path(temp_dir) / "adapted.patch"
                    
                    # 修改补丁内容，调整路径和扩大上下文
                    modified_content = patch_content.replace(
                        f"diff --git a/{file_match.group(1)} b/{file_match.group(1)}", 
                        f"diff --git a/{target_file} b/{target_file}"
                    )
                    
                    # 替换所有的a/旧路径和b/旧路径
                    modified_content = modified_content.replace(f"--- a/{file_match.group(1)}", f"--- a/{target_file}")
                    modified_content = modified_content.replace(f"+++ b/{file_match.group(1)}", f"+++ b/{target_file}")
                    
                    # 写入修改后的补丁
                    with open(adapted_patch, 'w', encoding='utf-8') as f:
                        f.write(modified_content)
                    
                    # 尝试使用多种参数组合应用补丁
                    patch_options = [
                        ["patch", "-p1", "-F", "100", "--fuzz=100", "--ignore-whitespace", "-f", "-l", target_file],
                        ["patch", "-p1", "-F", "100", "--fuzz=100", "--ignore-whitespace", "-f", "-l", "-t", target_file],
                        ["patch", "-p1", "-F", "100", "--fuzz=100", "--ignore-whitespace", "-f", "-l", "-N", target_file]
                    ]
                    
                    success = False
                    for options in patch_options:
                        try:
                            # 使用当前选项组合
                            logger.info(f"尝试patch选项: {' '.join(options)}")
                            
                            # 直接从文件读取内容，避免任何中间变量和不必要的类型转换
                            # 因为方法6的目的是使用更强大的补丁选项，我们直接打开文件并获取字节数据
                            with open(adapted_patch, 'rb') as f:
                                patch_binary_content = f.read()
                            
                            # 直接使用二进制数据，避免任何编码/解码操作
                            patch_result = subprocess.run(
                                options,
                                cwd=repo_path,
                                input=patch_binary_content,  # 直接使用二进制数据，不需要编码
                                capture_output=True,
                                text=True  # 输出仍然希望是文本
                            )
                            
                            if patch_result.returncode == 0:
                                # 成功应用
                                success = True
                                logger.info(f"成功应用块补丁(方法6): {patch_path.name}")
                                logger.info(f"使用的选项: {' '.join(options)}")
                                logger.info(f"Patch命令输出: {patch_result.stdout}")
                                
                                # 提交更改
                                self._run_git_command(["add", "."], repo_path)
                                self._run_git_command(["commit", "-m", f"Applied chunk patch with advanced patch options: {patch_path.name}"], repo_path)
                                break
                            else:
                                logger.info(f"选项 {' '.join(options)} 失败: {patch_result.stderr}")
                                # 恢复到干净状态
                                self._run_git_command(["reset", "--hard"], repo_path)
                        except Exception as e:
                            logger.info(f"尝试选项 {' '.join(options)} 异常: {e}")
                            import traceback
                            logger.info(f"错误堆栈: {traceback.format_exc()}")
                            # 恢复到干净状态
                            self._run_git_command(["reset", "--hard"], repo_path)
                    
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    
                    if success:
                        applied_patches.append(patch_path)
                
                except Exception as advanced_error:
                    logger.info(f"方法6异常: {advanced_error}")
                    # 恢复到干净状态
                    self._run_git_command(["reset", "--hard"], repo_path)
                
                # 7. 最后的方法：使用git diff的内容差异检测
                try:
                    logger.info("方法7: 尝试使用git diff内容差异检测")
                    
                    # 解析补丁块，获取文件路径
                    with open(abs_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                        patch_content = f.read()
                    
                    # 提取文件路径
                    file_match = re.search(r'diff --git a/(.*) b/', patch_content)
                    if not file_match:
                        logger.warning(f"无法从补丁提取文件路径: {patch_path.name}")
                        continue
                    
                    target_file = file_match.group(1)
                    target_file_path = Path(repo_path) / target_file
                    
                    # 检查目标文件是否存在
                    if not target_file_path.exists():
                        # 尝试查找同名文件
                        file_name = Path(target_file).name
                        find_result = subprocess.run(
                            ["find", ".", "-type", "f", "-name", file_name],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if find_result.returncode == 0 and find_result.stdout.strip():
                            # 找到可能的文件
                            possible_files = find_result.stdout.strip().split('\n')
                            
                            # 优先选择路径最相似的文件
                            max_similarity = 0
                            best_match = None
                            for found_file in possible_files:
                                similarity = self._path_similarity(target_file, found_file.lstrip('./\\'))
                                if similarity > max_similarity:
                                    max_similarity = similarity
                                    best_match = found_file.lstrip('./\\')
                            
                            if best_match:
                                target_file = best_match
                                target_file_path = Path(repo_path) / target_file
                                logger.info(f"使用最相似的文件: {target_file} (相似度: {max_similarity:.2f})")
                            else:
                                logger.warning(f"找不到合适的匹配文件")
                                continue
                        else:
                            logger.warning(f"找不到匹配的文件")
                            continue
                    
                    # 创建临时目录和文件
                    temp_dir = tempfile.mkdtemp()
                    
                    # 从补丁中提取修改内容
                    # 先提取所有删除的行（以-开头，但不是---开头）
                    removed_lines = []
                    added_lines = []
                    for line in patch_content.splitlines():
                        if line.startswith('-') and not line.startswith('---'):
                            removed_lines.append(line[1:])
                        elif line.startswith('+') and not line.startswith('+++'):
                            added_lines.append(line[1:])
                    
                    # 读取目标文件内容
                    with open(target_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        target_content = f.readlines()
                    
                    # 尝试定位修改位置
                    # 1. 寻找连续的删除行在文件中的位置
                    if len(removed_lines) >= 3:  # 需要至少3行才有足够的上下文
                        # 提取前3行作为模式
                        pattern = '\n'.join([line.strip() for line in removed_lines[:3]])
                        
                        # 在目标文件中搜索这个模式
                        target_content_str = ''.join(target_content)
                        position = target_content_str.find(pattern)
                        
                        if position != -1:
                            # 找到匹配位置
                            logger.info(f"在文件中找到匹配内容的位置: 偏移 {position}")
                            
                            # 计算行号
                            line_number = target_content_str[:position].count('\n') + 1
                            logger.info(f"匹配内容在第 {line_number} 行附近")
                            
                            # 创建临时修改后的文件
                            modified_file = Path(temp_dir) / "modified_file"
                            
                            # 复制文件前半部分
                            with open(modified_file, 'w', encoding='utf-8') as f:
                                f.writelines(target_content[:line_number-1])
                                
                                # 添加新内容
                                for line in added_lines:
                                    f.write(line + '\n')
                                
                                # 添加剩余内容（跳过原来应该删除的行）
                                f.writelines(target_content[line_number+len(removed_lines)-1:])
                            
                            # 使用修改后的文件替换原始文件
                            shutil.copy(modified_file, target_file_path)
                            
                            # 提交更改
                            self._run_git_command(["add", target_file], repo_path)
                            self._run_git_command(["commit", "-m", f"Applied chunk patch using content diff detection: {patch_path.name}"], repo_path)
                            
                            # 添加到成功应用的补丁列表
                            applied_patches.append(patch_path)
                            logger.info(f"成功应用块补丁(方法7): {patch_path.name}")
                        else:
                            logger.info("在文件中找不到匹配的内容位置")
                    else:
                        logger.info("删除行不足以确定准确位置")
                    
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    
                except Exception as diff_error:
                    logger.info(f"方法7异常: {diff_error}")
                    # 恢复到干净状态
                    self._run_git_command(["reset", "--hard"], repo_path)
                
                # 8. 额外尝试：直接使用shell命令尝试更多方式应用补丁
                try:
                    logger.info("方法8: 尝试使用外部shell命令应用补丁")
                    
                    # 解析补丁块，获取文件路径
                    with open(abs_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                        patch_content = f.read()
                    
                    # 提取文件路径
                    file_match = re.search(r'diff --git a/(.*) b/', patch_content)
                    if not file_match:
                        logger.warning(f"无法从补丁提取文件路径: {patch_path.name}")
                        continue
                    
                    target_file = file_match.group(1)
                    target_file_path = Path(repo_path) / target_file
                    
                    # 检查目标文件是否存在
                    if not target_file_path.exists():
                        # 尝试查找同名文件
                        file_name = Path(target_file).name
                        find_result = subprocess.run(
                            ["find", ".", "-name", file_name, "-type", "f"],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if find_result.returncode == 0 and find_result.stdout.strip():
                            # 找到可能的文件
                            possible_files = find_result.stdout.strip().split('\n')
                            
                            # 选择最相似的路径
                            max_similarity = 0
                            best_match = None
                            for found_file in possible_files:
                                similarity = self._path_similarity(target_file, found_file.lstrip('./\\'))
                                if similarity > max_similarity:
                                    max_similarity = similarity
                                    best_match = found_file.lstrip('./\\')
                            
                            if best_match:
                                target_file = best_match
                                target_file_path = Path(repo_path) / target_file
                                logger.info(f"使用最相似的文件: {target_file} (相似度: {max_similarity:.2f})")
                            else:
                                logger.warning(f"找不到合适的匹配文件")
                                continue
                        else:
                            logger.warning(f"找不到匹配的文件")
                            continue
                    
                    # 创建一个临时脚本来运行patch命令，以便使用更多的shell特性
                    temp_dir = tempfile.mkdtemp()
                    script_path = Path(temp_dir) / "apply_patch.sh"
                    abs_patch_path_str = str(abs_patch_path.absolute())
                    
                    # 创建shell脚本
                    with open(script_path, 'w') as f:
                        f.write(f"""#!/bin/bash
                        set -e
                        cd {repo_path}
                        
                        # 尝试方法1：使用patch命令的最大模糊匹配
                        if cat {abs_patch_path_str} | patch -p1 -F 100 --fuzz=100 --ignore-whitespace -f --verbose {target_file}; then
                            echo "方法8.1成功：使用patch -p1 -F 100"
                            exit 0
                        fi
                        
                        # 尝试方法2：将补丁转换为上下文差异格式
                        if cat {abs_patch_path_str} | patch -p1 -F 100 --fuzz=100 -c -f --verbose {target_file}; then
                            echo "方法8.2成功：使用patch -p1 -F 100 -c"
                            exit 0
                        fi
                        
                        # 尝试方法3：直接编辑目标文件，使用ed命令
                        if cat {abs_patch_path_str} | patch -p1 -F 100 --fuzz=100 -e -f --verbose {target_file}; then
                            echo "方法8.3成功：使用patch -p1 -F 100 -e"
                            exit 0
                        fi
                        
                        # 尝试方法4：使用--dry-run模式先检查
                        if cat {abs_patch_path_str} | patch -p1 -F 100 --fuzz=100 --ignore-whitespace --dry-run {target_file} && cat {abs_patch_path_str} | patch -p1 -F 100 --fuzz=100 --ignore-whitespace {target_file}; then
                            echo "方法8.4成功：使用--dry-run先检查"
                            exit 0
                        fi
                        
                        # 失败
                        echo "所有shell尝试都失败"
                        exit 1
                        """)
                    
                    # 设置脚本可执行权限
                    os.chmod(script_path, 0o755)
                    
                    # 执行脚本
                    result = subprocess.run(
                        [str(script_path)],
                        shell=True,
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        # 成功应用
                        applied_patches.append(patch_path)
                        logger.info(f"成功应用块补丁(方法8): {patch_path.name}")
                        logger.info(f"Shell脚本输出: {result.stdout}")
                        
                        # 提交更改
                        self._run_git_command(["add", "."], repo_path)
                        self._run_git_command(["commit", "-m", f"Applied chunk patch with shell script: {patch_path.name}"], repo_path)
                    else:
                        logger.info(f"方法8失败: {result.stderr}")
                        # 恢复到干净状态
                        self._run_git_command(["reset", "--hard"], repo_path)
                    
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    
                except Exception as shell_error:
                    logger.info(f"方法8异常: {shell_error}")
                    import traceback
                    logger.info(f"错误堆栈: {traceback.format_exc()}")
                    # 恢复到干净状态
                    self._run_git_command(["reset", "--hard"], repo_path)
        
        finally:
            # 清理：切回原始分支，删除测试分支
            try:
                self._run_git_command(["checkout", current_branch], repo_path)
                self._run_git_command(["branch", "-D", test_branch], repo_path)
                logger.info(f"清理测试分支: {test_branch}")
            except Exception as e:
                logger.error(f"清理测试分支失败: {e}")
        
        return applied_patches
    
    def _create_remaining_patch(self, all_patches: List[Path], applied_patches: List[Path], context: ModuleContext) -> Optional[Path]:
        """
        为未成功应用的chunk创建一个合并补丁
        
        :param all_patches: 所有chunk补丁文件路径
        :param applied_patches: 已成功应用的补丁文件路径
        :param context: 模块上下文
        :return: 合并的剩余补丁文件路径
        """
        # 找出未应用的补丁
        remaining_patches = [p for p in all_patches if p not in applied_patches]
        if not remaining_patches:
            return None
            
        output_dir = context.commit.base_dir / "chunk_patches"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remaining_patch_path = output_dir / f"remaining_chunks_{timestamp}.patch"
        
        # 补丁头部（从原始补丁提取）
        patch_header = ""
        with open(Path(context.commit.patch_path).absolute(), 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if line.startswith('diff --git'):
                    break
                patch_header += line
        
        # 合并剩余的补丁块
        with open(remaining_patch_path, 'w', encoding='utf-8') as out_file:
            # 写入补丁头部
            out_file.write(patch_header)
            
            # 按文件组织补丁块
            file_chunks = {}
            
            for patch_path in remaining_patches:
                # 确保使用绝对路径
                abs_patch_path = patch_path.absolute()
                with open(abs_patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    # 提取文件路径和diff部分
                    diff_match = re.search(r'(diff --git a/(.*?) b/.*?)(?=diff --git|\Z)', content, re.DOTALL)
                    if diff_match:
                        file_path = diff_match.group(2)
                        diff_content = diff_match.group(1)
                        
                        if file_path not in file_chunks:
                            file_chunks[file_path] = []
                        
                        # 只保存diff部分（不包括补丁头部）
                        file_chunks[file_path].append(diff_content)
            
            # 为每个文件合并chunks
            for file_path, chunks in file_chunks.items():
                # 只写入第一个chunk的文件头部
                first_chunk = chunks[0]
                header_end = first_chunk.find('@@')
                if header_end > 0:
                    file_header = first_chunk[:header_end]
                    out_file.write(file_header)
                
                # 写入所有chunks的@@部分
                for chunk in chunks:
                    hunk_start = chunk.find('@@')
                    if hunk_start > 0:
                        out_file.write(chunk[hunk_start:])
        
        logger.info(f"创建剩余块补丁文件: {remaining_patch_path.absolute()}")
        return remaining_patch_path
    
    def _run_git_command(self, args: List[str], cwd: Path) -> str:
        """运行git命令并返回输出"""
        try:
            logger.info(f"运行git命令: {' '.join(args)}")
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

    def _path_similarity(self, path1: str, path2: str) -> float:
        """
        计算两个文件路径的相似度（0-1之间的值，1表示完全相同）
        使用最长公共子序列算法
        """
        path1_parts = Path(path1).parts
        path2_parts = Path(path2).parts
        
        # 如果文件名不同，直接返回0
        if path1_parts[-1] != path2_parts[-1]:
            return 0
        
        # 计算目录部分的相似度
        path1_dirs = path1_parts[:-1]
        path2_dirs = path2_parts[:-1]
        
        # 如果没有目录部分，文件名相同就返回1
        if not path1_dirs and not path2_dirs:
            return 1
        
        # 计算最长公共子序列长度
        lcs_length = self._longest_common_subsequence(path1_dirs, path2_dirs)
        
        # 计算相似度
        max_length = max(len(path1_dirs), len(path2_dirs))
        if max_length == 0:
            return 1
        
        return lcs_length / max_length
    
    def _longest_common_subsequence(self, seq1, seq2):
        """计算两个序列的最长公共子序列长度"""
        m, n = len(seq1), len(seq2)
        
        # 创建二维数组来保存中间结果
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        # 填充dp表格
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i-1] == seq2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        
        return dp[m][n] 

    def _save_evaluation_info(self, context: ModuleContext):
        """
        保存美观易读的输入/输出评估信息，用于单元测试和调试
        
        保存的信息包括：
        1. 原始补丁内容
        2. 分解后的补丁块信息
        3. 应用成功的补丁块信息
        4. 使用的各种命令和参数
        5. 操作过程中的关键输出
        """
        # 首先调用父类方法创建基本结构
        super()._save_evaluation_info(context)
        
        try:
            # 获取最新创建的评估信息目录
            eval_dir = context.base_dir / "evaluations" / self.name
            if not eval_dir.exists():
                return
                
            # 查找最新的details目录
            detail_dirs = list(eval_dir.glob("details_*"))
            if not detail_dirs:
                return
                
            details_dir = max(detail_dirs, key=lambda p: p.stat().st_mtime)
            
            # 复制特定于chunk_analyzer的文件
            
            # 复制原始补丁文件
            if hasattr(context.commit, "patch_path") and Path(context.commit.patch_path).exists():
                original_patch_dest = details_dir / "original_patch.diff"
                shutil.copy(context.commit.patch_path, original_patch_dest)
            
            # 复制剩余补丁文件（如果有）
            if context.chunk_analyzer_result and context.chunk_analyzer_result.get("remaining_patch"):
                remaining_patch = Path(context.chunk_analyzer_result.get("remaining_patch"))
                if remaining_patch.exists():
                    remaining_patch_dest = details_dir / "remaining_patch.diff"
                    shutil.copy(remaining_patch, remaining_patch_dest)
            
            # 保存应用成功的补丁信息
            if context.chunk_analyzer_result and context.chunk_analyzer_result.get("applied_chunk_patches"):
                applied_chunks_info = []
                for i, chunk_path in enumerate(context.chunk_analyzer_result.get("applied_chunk_patches", []), 1):
                    chunk_file = Path(chunk_path)
                    if chunk_file.exists():
                        # 复制应用成功的补丁
                        chunk_dest = details_dir / f"applied_chunk_{i}.diff"
                        shutil.copy(chunk_file, chunk_dest)
                        
                        # 读取补丁内容
                        with open(chunk_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        # 提取修改文件信息
                        file_match = re.search(r'diff --git a/(.*) b/', content)
                        file_path = file_match.group(1) if file_match else "未知"
                        
                        # 提取修改位置信息
                        hunk_match = re.search(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', content)
                        position = f"{hunk_match.group(1)}-{hunk_match.group(3)}" if hunk_match else "未知"
                        
                        applied_chunks_info.append({
                            "索引": i,
                            "补丁路径": str(chunk_path),
                            "修改文件": file_path,
                            "修改位置": position
                        })
                
                # 保存应用成功的补丁信息
                applied_chunks_file = details_dir / "applied_chunks.json"
                with open(applied_chunks_file, 'w', encoding='utf-8') as f:
                    json.dump(applied_chunks_info, f, indent=2, ensure_ascii=False)
            
            # 更新README文件
            readme_file = details_dir / "README.md"
            if readme_file.exists():
                with open(readme_file, 'a', encoding='utf-8') as f:
                    f.write("\n## 补丁分块文件\n\n")
                    f.write("- original_patch.diff: 原始补丁文件\n")
                    f.write("- remaining_patch.diff: 剩余未应用补丁文件（如果有）\n")
                    f.write("- applied_chunk_*.diff: 成功应用的补丁块\n")
                    f.write("- applied_chunks.json: 成功应用的补丁块详细信息\n")
            
        except Exception as e:
            logger.error(f"保存chunk_analyzer特定评估信息失败: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
    def _collect_output_info(self, context: ModuleContext) -> Dict[str, Any]:
        """重写收集输出信息方法，提供chunk_analyzer特有的输出信息"""
        # 首先获取基本输出信息
        output_info = super()._collect_output_info(context)
        
        # 添加chunk_analyzer特有的信息
        if hasattr(context, "chunk_analyzer_result") and context.chunk_analyzer_result:
            # 如果不是错误状态，添加详细信息
            if context.chunk_analyzer_result.get("status") != "error":
                chunk_info = {
                    "总块数": context.chunk_analyzer_result.get("total_chunks", 0),
                    "成功应用块数": context.chunk_analyzer_result.get("applied_chunks", 0),
                    "成功率": f"{context.chunk_analyzer_result.get('applied_chunks', 0) / max(1, context.chunk_analyzer_result.get('total_chunks', 1)) * 100:.2f}%",
                    "剩余补丁路径": context.chunk_analyzer_result.get("remaining_patch", "无")
                }
                output_info.update(chunk_info)
            else:
                # 添加错误信息
                output_info["错误信息"] = context.chunk_analyzer_result.get("error", "未知错误")
        
        return output_info
        
    def _generate_additional_html_sections(self, context: ModuleContext) -> str:
        """生成额外的HTML报告部分，添加chunk_analyzer特有的内容"""
        
        if not hasattr(context, "chunk_analyzer_result") or not context.chunk_analyzer_result:
            return ""
            
        # 如果是错误状态，不添加额外内容
        if context.chunk_analyzer_result.get("status") == "error":
            return ""
            
        # 生成块应用统计部分
        chunks_html = f"""
        <div class="card">
          <h2>补丁块应用统计</h2>
          
          <div class="progress-container">
            <div class="progress-bar success-bg" style="width: {
                int(context.chunk_analyzer_result.get("applied_chunks", 0) / max(1, context.chunk_analyzer_result.get("total_chunks", 1)) * 100)
            }%"></div>
          </div>
          <p>
            成功应用 <strong class="success">{context.chunk_analyzer_result.get("applied_chunks", 0)}</strong> 个块，
            总共 <strong>{context.chunk_analyzer_result.get("total_chunks", 0)}</strong> 个块
            (成功率: <strong>{
                context.chunk_analyzer_result.get("applied_chunks", 0) / max(1, context.chunk_analyzer_result.get("total_chunks", 1)) * 100
            :.1f}%</strong>)
          </p>
        </div>
        """
        
        # 如果有已应用的补丁块，生成应用成功的补丁块列表
        applied_chunks_html = ""
        if context.chunk_analyzer_result.get("applied_chunk_patches"):
            applied_chunks = []
            for i, chunk_path in enumerate(context.chunk_analyzer_result.get("applied_chunk_patches", [])):
                chunk_file = Path(chunk_path)
                if chunk_file.exists():
                    try:
                        with open(chunk_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        # 提取修改文件信息
                        file_match = re.search(r'diff --git a/(.*) b/', content)
                        file_path = file_match.group(1) if file_match else "未知"
                        
                        # 提取修改位置信息
                        hunk_match = re.search(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', content)
                        position = f"{hunk_match.group(1)}-{hunk_match.group(3)}" if hunk_match else "未知"
                        
                        applied_chunks.append({
                            "index": i+1,
                            "file": file_path,
                            "position": position
                        })
                    except Exception:
                        # 如果处理某个文件出错，跳过它
                        continue
            
            if applied_chunks:
                applied_chunks_rows = "\n".join([
                    f"""
                    <tr>
                      <td>{chunk['index']}</td>
                      <td>{chunk['file']}</td>
                      <td>{chunk['position']}</td>
                      <td><a href="applied_chunk_{chunk['index']}.diff" target="_blank">查看</a></td>
                    </tr>
                    """
                    for chunk in applied_chunks
                ])
                
                applied_chunks_html = f"""
                <div class="card">
                  <h2>应用成功的补丁块</h2>
                  <table>
                    <tr>
                      <th>块索引</th>
                      <th>修改文件</th>
                      <th>修改位置</th>
                      <th>操作</th>
                    </tr>
                    {applied_chunks_rows}
                  </table>
                </div>
                """
        
        # 如果有剩余补丁，生成剩余补丁部分
        remaining_patch_html = ""
        if context.chunk_analyzer_result.get("remaining_patch"):
            remaining_patch_html = f"""
            <div class="card">
              <h2>剩余补丁</h2>
              <p>有 <strong class="info">{
                  context.chunk_analyzer_result.get("total_chunks", 0) - context.chunk_analyzer_result.get("applied_chunks", 0)
              }</strong> 个块未成功应用，已生成剩余补丁:</p>
              <p><code>{context.chunk_analyzer_result.get("remaining_patch", "无")}</code></p>
              <p><a href="remaining_patch.diff" target="_blank">查看剩余补丁</a></p>
            </div>
            """
        
        # 组合所有部分
        return chunks_html + applied_chunks_html + remaining_patch_html 