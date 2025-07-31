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
import pprint

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
            for i, chunk_patch in enumerate(chunk_patches):
                logger.info(f"第 {i+1} 个补丁文件为：")
                with open(chunk_patch, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    text = ''.join(lines)
                    logger.info(text)
            
            # 3. 尝试应用每个独立的补丁块
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
            print("analysis_result:")
            pprint.pprint(analysis_result)
            
            # 将结果写入上下文
            context.chunk_analyzer_result = analysis_result
            
            # 将剩余补丁路径存储到上下文中，供后续模块使用
            if remaining_patch:
                context.commit.optimized_patch_path = remaining_patch
                logger.info(f"已将剩余补丁路径存储到上下文: {remaining_patch}")
            
            # 添加标记，当所有块都应用成功时，记录成功信息用于跳过后续步骤
            if len(applied_chunks) == len(chunks) and len(chunks) > 0:
                # 所有块都应用成功
                context.chunk_analyzer_result['success'] = True
                # 设置适配状态，使后续模块可以跳过
                context.need_adapt = True
                context.adapt_success = True
                logger.info("所有补丁块应用成功，标记为完全成功，后续模块可跳过")
            else:
                context.chunk_analyzer_result['success'] = False
                
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
        在测试分支中尝试应用每个独立的补丁块，完成后删除测试分支
        
        Args:
            chunk_patches: 补丁块文件路径列表
            context: 处理上下文
        
        Returns:
            成功应用的补丁块文件路径列表
        """
        applied_patches = []
        
        # 获取repo_path
        repo_path = Path(context.config.repo_path)
        if not repo_path.exists():
            raise ValueError(f"仓库路径不存在: {repo_path}")
        
        # 确保总是使用绝对路径
        repo_path = repo_path.absolute()
        
        # 更新统计信息
        context.chunks_detailed_info["total_chunks"] = len(chunk_patches)
        context.chunks_detailed_info["no_conflict_chunks"] = 0
        context.chunks_detailed_info["adapt_succeeded_chunks"] = 0
        context.chunks_detailed_info["adapt_failed_chunks"] = 0
        
        # 创建测试分支
        import uuid
        test_branch = f"test_chunk_apply_{uuid.uuid4().hex[:8]}"
        
        # 确定目标版本
        target_version = context.config.target_version
        if isinstance(target_version, list):
            target_version = target_version[0]  # 取第一个元素作为字符串
        
        try:
            # 先切换到目标版本
            logger.info(f"切换到目标版本: {target_version}")
            checkout_result = subprocess.run(
                ['git', 'checkout', target_version],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if checkout_result.returncode != 0:
                raise ValueError(f"切换到目标版本失败: {checkout_result.stderr}")
            
            # 创建测试分支
            logger.info(f"创建测试分支: {test_branch}")
            branch_result = subprocess.run(
                ['git', 'checkout', '-b', test_branch],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if branch_result.returncode != 0:
                raise ValueError(f"创建测试分支失败: {branch_result.stderr}")
            
            # 清理工作区
            subprocess.run(['git', 'reset', '--hard', 'HEAD'], cwd=repo_path)
            subprocess.run(['git', 'clean', '-fd'], cwd=repo_path)
            
            # 尝试应用每个chunk补丁
            for i, patch_file in enumerate(chunk_patches):
                # 确保使用补丁文件的绝对路径
                abs_patch_file = Path(patch_file).absolute()
                logger.info(f"尝试应用第 {i+1}/{len(chunk_patches)} 个块补丁: {patch_file.name}")
                
                try:
                    # 应用补丁（允许模糊匹配）
                    result = subprocess.run(
                        ['git', 'apply', '--ignore-whitespace', '--allow-overlap', str(abs_patch_file)],
                        cwd=repo_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        logger.info(f"成功应用块补丁: {patch_file.name}")
                        applied_patches.append(patch_file)
                        context.chunks_detailed_info["no_conflict_chunks"] += 1
                    else:
                        error = result.stderr
                        # 尝试反向应用，如果能反向应用，说明可能已经修改过了
                        reverse_result = subprocess.run(
                            ['git', 'apply', '--ignore-whitespace', '--allow-overlap', '--reverse', str(abs_patch_file)],
                            cwd=repo_path,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True
                        )
                        
                        if reverse_result.returncode == 0:
                            logger.warning(f"块补丁 {patch_file.name} 可以反向应用，可能已经被应用过")
                            applied_patches.append(patch_file)
                            context.chunks_detailed_info["no_conflict_chunks"] += 1
                        else:
                            logger.warning(f"块补丁 {patch_file.name} 应用失败: {error}")
                            # 这里记录一个失败的块
                            context.chunks_detailed_info["adapt_failed_chunks"] += 1
                
                except Exception as e:
                    logger.error(f"应用块补丁 {patch_file.name} 时出错: {e}")
                    # 这里记录一个失败的块
                    context.chunks_detailed_info["adapt_failed_chunks"] += 1
            
            # 输出统计信息
            logger.info(f"块补丁应用统计信息:")
            logger.info(f"- 总块数: {context.chunks_detailed_info['total_chunks']}")
            logger.info(f"- 无冲突块数: {context.chunks_detailed_info['no_conflict_chunks']}")
            logger.info(f"- 适配失败块数: {context.chunks_detailed_info['adapt_failed_chunks']}")
            
        finally:
            # 清理：切换回目标版本并删除测试分支
            try:
                logger.info(f"切换回目标版本: {target_version}")
                subprocess.run(
                    ['git', 'checkout', target_version],
                    cwd=repo_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                logger.info(f"删除测试分支: {test_branch}")
                subprocess.run(
                    ['git', 'branch', '-D', test_branch],
                    cwd=repo_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            except Exception as e:
                logger.warning(f"清理测试分支时发生错误: {e}")
        
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
            
            # 创建补丁内容目录
            patches_dir = details_dir / "patches"
            patches_dir.mkdir(exist_ok=True)
            
            # 复制特定于chunk_analyzer的文件
            
            # 复制原始补丁文件
            original_patch_content = ""
            if hasattr(context.commit, "patch_path") and Path(context.commit.patch_path).exists():
                original_patch_dest = details_dir / "original_patch.diff"
                shutil.copy(context.commit.patch_path, original_patch_dest)
                
                # 读取原始补丁内容用于显示
                with open(context.commit.patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                    original_patch_content = f.read()
                
                # 保存原始补丁内容的文本文件
                with open(patches_dir / "original_patch.txt", 'w', encoding='utf-8') as f:
                    f.write(original_patch_content)
            
            # 复制剩余补丁文件（如果有）
            remaining_patch_content = ""
            if context.chunk_analyzer_result and context.chunk_analyzer_result.get("remaining_patch"):
                remaining_patch = Path(context.chunk_analyzer_result.get("remaining_patch"))
                if remaining_patch.exists():
                    remaining_patch_dest = details_dir / "remaining_patch.diff"
                    shutil.copy(remaining_patch, remaining_patch_dest)
                    
                    # 读取剩余补丁内容用于显示
                    with open(remaining_patch, 'r', encoding='utf-8', errors='ignore') as f:
                        remaining_patch_content = f.read()
                    
                    # 保存剩余补丁内容的文本文件
                    with open(patches_dir / "remaining_patch.txt", 'w', encoding='utf-8') as f:
                        f.write(remaining_patch_content)
            
            # 保存应用成功的补丁信息
            applied_chunks_content = []
            if context.chunk_analyzer_result and context.chunk_analyzer_result.get("applied_chunk_patches"):
                applied_chunks_info = []
                all_applied_content = ""
                
                for i, chunk_path in enumerate(context.chunk_analyzer_result.get("applied_chunk_patches", []), 1):
                    chunk_file = Path(chunk_path)
                    if chunk_file.exists():
                        # 检查是否有应用细节信息
                        patch_info = {}
                        precise_patch = None
                        specific_patch = None
                        actual_patch = None
                        
                        if hasattr(self, '_patch_application_info') and str(chunk_path) in self._patch_application_info:
                            patch_info = self._patch_application_info[str(chunk_path)]
                            logger.info(f"找到补丁应用细节信息: {patch_info}")
                            
                            # 尝试使用从实际commit生成的补丁
                            for patch_type in ['precise_patch', 'specific_patch', 'actual_patch']:
                                if patch_type in patch_info and patch_info[patch_type] and Path(patch_info[patch_type]).exists():
                                    if patch_type == 'precise_patch':
                                        precise_patch = Path(patch_info[patch_type])
                                    elif patch_type == 'specific_patch':
                                        specific_patch = Path(patch_info[patch_type])
                                    else:
                                        actual_patch = Path(patch_info[patch_type])
                        
                        # 确定使用哪个补丁文件 - 优先使用更精确的
                        final_patch_file = None
                        content = None
                        
                        if precise_patch and precise_patch.exists():
                            final_patch_file = precise_patch
                            logger.info(f"使用精确生成的补丁文件: {precise_patch}")
                            with open(precise_patch, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                        elif specific_patch and specific_patch.exists():
                            final_patch_file = specific_patch
                            logger.info(f"使用特定文件的补丁文件: {specific_patch}")
                            with open(specific_patch, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                        elif actual_patch and actual_patch.exists():
                            final_patch_file = actual_patch
                            logger.info(f"使用实际提交的补丁文件: {actual_patch}")
                            with open(actual_patch, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                        elif chunk_file.exists():
                            final_patch_file = chunk_file
                            with open(chunk_file, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                        
                        if final_patch_file is None or content is None:
                            logger.warning(f"未找到有效的补丁文件: {chunk_path}")
                            continue
                        
                        # 复制应用成功的补丁
                        chunk_dest = details_dir / f"applied_chunk_{i}.diff"
                        shutil.copy(final_patch_file, chunk_dest)
                        
                        # 添加到所有应用成功的内容中
                        all_applied_content += f"\n\n# ===== 应用成功的补丁块 {i} =====\n\n"
                        if patch_info:
                            # 添加应用细节信息
                            all_applied_content += f"# 应用方法: {patch_info.get('method', '未知')}\n"
                            if patch_info.get('actual_line'):
                                all_applied_content += f"# 实际应用行号: {patch_info.get('actual_line')}\n"
                            if patch_info.get('offset'):
                                all_applied_content += f"# 行号偏移: {patch_info.get('offset')}\n"
                            all_applied_content += f"# 目标文件: {patch_info.get('target_file', '未知')}\n"
                            if patch_info.get('commit_hash'):
                                all_applied_content += f"# 提交哈希: {patch_info.get('commit_hash')}\n"
                            all_applied_content += "\n"
                        
                        all_applied_content += content
                        
                        # 保存单个应用成功的补丁内容，添加应用细节信息
                        detailed_content = content
                        if patch_info:
                            header = f"# 应用方法: {patch_info.get('method', '未知')}\n"
                            if patch_info.get('actual_line'):
                                header += f"# 实际应用行号: {patch_info.get('actual_line')}\n"
                            if patch_info.get('offset'):
                                header += f"# 行号偏移: {patch_info.get('offset')}\n"
                            header += f"# 目标文件: {patch_info.get('target_file', '未知')}\n"
                            if patch_info.get('commit_hash'):
                                header += f"# 提交哈希: {patch_info.get('commit_hash')}\n"
                            if final_patch_file != chunk_file:
                                header += f"# 实际补丁文件: {final_patch_file}\n"
                            header += "\n"
                            detailed_content = header + content
                        
                        with open(patches_dir / f"applied_chunk_{i}.txt", 'w', encoding='utf-8') as f:
                            f.write(detailed_content)
                        
                        # 提取修改文件信息
                        file_match = re.search(r'diff --git a/(.*) b/', content)
                        file_path = file_match.group(1) if file_match else patch_info.get('target_file', "未知")
                        
                        # 提取修改位置信息 - 优先使用实际应用的行号
                        position = "未知"
                        if patch_info.get('actual_line'):
                            position = f"{patch_info.get('actual_line')}"
                        else:
                            # 尝试从补丁内容中提取
                            hunk_match = re.search(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@', content)
                            if hunk_match:
                                position = f"{hunk_match.group(1)}-{hunk_match.group(3)}"
                        
                        # 添加应用细节到信息中
                        chunk_info = {
                            "索引": i,
                            "补丁路径": str(chunk_path),
                            "实际补丁": str(final_patch_file) if final_patch_file != chunk_file else None,
                            "修改文件": file_path,
                            "修改位置": position,
                            "内容": content
                        }
                        
                        if patch_info:
                            chunk_info.update({
                                "应用方法": patch_info.get('method', '未知'),
                                "实际应用行号": patch_info.get('actual_line'),
                                "行号偏移": patch_info.get('offset'),
                                "目标文件": patch_info.get('target_file', '未知'),
                                "提交哈希": patch_info.get('commit_hash')
                            })
                        
                        applied_chunks_info.append(chunk_info)
                        
                        # 添加到应用成功的补丁列表
                        applied_chunk_content = {
                            "index": i,
                            "file": file_path,
                            "position": position,
                            "content": content
                        }
                        
                        if patch_info:
                            applied_chunk_content.update({
                                "method": patch_info.get('method', '未知'),
                                "actual_line": patch_info.get('actual_line'),
                                "offset": patch_info.get('offset'),
                                "target_file": patch_info.get('target_file', '未知'),
                                "commit_hash": patch_info.get('commit_hash')
                            })
                        
                        applied_chunks_content.append(applied_chunk_content)
                
                # 保存所有应用成功的补丁内容
                with open(patches_dir / "all_applied_chunks.txt", 'w', encoding='utf-8') as f:
                    f.write(all_applied_content)
                
                # 保存应用成功的补丁信息
                applied_chunks_file = details_dir / "applied_chunks.json"
                with open(applied_chunks_file, 'w', encoding='utf-8') as f:
                    json.dump(applied_chunks_info, f, indent=2, ensure_ascii=False)
            
            # 保存所有补丁内容到一个JSON文件供HTML使用
            patches_json = {
                "original_patch": original_patch_content,
                "applied_chunks": applied_chunks_content,
                "remaining_patch": remaining_patch_content
            }
            
            with open(details_dir / "patches_content.json", 'w', encoding='utf-8') as f:
                json.dump(patches_json, f, indent=2, ensure_ascii=False)
            
            # 更新README文件
            readme_file = details_dir / "README.md"
            if readme_file.exists():
                with open(readme_file, 'a', encoding='utf-8') as f:
                    f.write("\n## 补丁分块文件\n\n")
                    f.write("- original_patch.diff: 原始补丁文件\n")
                    f.write("- remaining_patch.diff: 剩余未应用补丁文件（如果有）\n")
                    f.write("- applied_chunk_*.diff: 成功应用的补丁块\n")
                    f.write("- applied_chunks.json: 成功应用的补丁块详细信息\n")
                    f.write("\n## 补丁内容文本文件\n\n")
                    f.write("- patches/original_patch.txt: 原始补丁内容\n")
                    f.write("- patches/remaining_patch.txt: 剩余未应用补丁内容\n")
                    f.write("- patches/applied_chunk_*.txt: 单个成功应用的补丁块内容\n")
                    f.write("- patches/all_applied_chunks.txt: 所有成功应用的补丁块内容\n")
                    f.write("\n## 实际应用补丁文件\n\n")
                    f.write("- 精确补丁文件 (*_precise.patch): 使用git diff命令从实际提交中生成的精确补丁\n")
                    f.write("- 特定文件补丁 (*_specific.patch): 使用git show命令从实际提交中获取特定文件的变更\n")
                    f.write("- 实际提交补丁 (*_actual.patch): 实际提交生成的完整补丁\n")
            
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

        # 查找或创建当前评估目录路径
        eval_dir = context.base_dir / "evaluations" / self.name
        if not eval_dir.exists():
            logger.warning(f"评估目录不存在: {eval_dir}")
            return ""
        
        # 查找当前评估的details目录
        details_dir = None
        try:
            # 先尝试查找当前会话最新创建的目录
            timestamp = datetime.now().strftime("%Y%m%d")  # 使用当天日期匹配
            commit_sha = context.commit.commit_sha[:6]
            current_details_dirs = list(eval_dir.glob(f"details_{commit_sha}_{timestamp}*"))
            
            if current_details_dirs:
                # 如果找到匹配当前提交和日期的目录，使用最新的
                details_dir = max(current_details_dirs, key=lambda p: p.stat().st_mtime)
                logger.info(f"找到当前评估会话目录: {details_dir}")
            else:
                # 如果没找到，使用所有目录中最新的
                all_details_dirs = list(eval_dir.glob("details_*"))
                if all_details_dirs:
                    details_dir = max(all_details_dirs, key=lambda p: p.stat().st_mtime)
                    logger.info(f"使用最新评估目录: {details_dir}")
                else:
                    logger.warning("未找到任何评估详情目录")
                    return ""
        except Exception as e:
            logger.error(f"查找评估目录时出错: {e}")
            return ""
        
        # 存储当前评估目录路径供_get_patch_content方法使用
        self._current_details_dir = details_dir
            
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
        
        # 补丁内容展示部分（原始补丁、应用成功的补丁、剩余补丁）
        patches_html = """
        <div class="card">
          <h2>补丁内容详情</h2>
          <div class="tabs">
            <div class="tab-header">
              <button class="tab-button active" onclick="openTab(event, 'original-patch')">原始补丁</button>
              <button class="tab-button" onclick="openTab(event, 'applied-patches')">应用成功的补丁</button>
              <button class="tab-button" onclick="openTab(event, 'remaining-patch')">未应用成功的补丁</button>
            </div>
            
            <div id="original-patch" class="tab-content" style="display:block;">
              <h3>原始补丁内容</h3>
              <div class="code-container">
                <pre class="code-block">"""
        
        # 添加原始补丁内容
        patches_html += self._get_patch_content(context, "original")
                
        patches_html += """</pre>
              </div>
            </div>
            
            <div id="applied-patches" class="tab-content">
              <h3>应用成功的补丁内容</h3>
              <div class="code-container">
                <pre class="code-block">"""
        
        # 添加应用成功的补丁内容
        patches_html += self._get_patch_content(context, "applied")
                
        patches_html += """</pre>
              </div>
            </div>
            
            <div id="remaining-patch" class="tab-content">
              <h3>未应用成功的补丁内容</h3>
              <div class="code-container">
                <pre class="code-block">"""
        
        # 添加剩余补丁内容
        patches_html += self._get_patch_content(context, "remaining")
                
        patches_html += """</pre>
              </div>
            </div>
          </div>
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
                    except Exception as e:
                        # 如果处理某个文件出错，记录错误并跳过它
                        logger.error(f"处理应用成功的补丁块{i+1}时出错: {e}")
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
        
        # 添加CSS样式
        style_html = """
        <style>
        .code-container {
          max-height: 500px;
          overflow-y: auto;
          background-color: #f8f9fa;
          border-radius: 5px;
          border: 1px solid #eee;
        }
        
        .code-block {
          padding: 15px;
          margin: 0;
          white-space: pre-wrap;
          font-family: monospace;
          font-size: 13px;
          line-height: 1.4;
        }
        
        /* 为补丁内容添加语法高亮 */
        .code-block .add {
          background-color: #e6ffed;
          color: #22863a;
        }
        
        .code-block .remove {
          background-color: #ffeef0;
          color: #cb2431;
        }
        
        .code-block .hunk {
          color: #0366d6;
          background-color: #f1f8ff;
        }
        
        .code-block .header {
          color: #6f42c1;
          font-weight: bold;
        }
        </style>
        
        <script>
        // 对补丁内容应用简单的语法高亮
        document.addEventListener('DOMContentLoaded', function() {
          const codeBlocks = document.querySelectorAll('.code-block');
          codeBlocks.forEach(function(block) {
            let html = block.innerHTML;
            
            // 替换添加的行
            html = html.replace(/^(\+[^+].*)/gm, '<span class="add">$1</span>');
            
            // 替换删除的行
            html = html.replace(/^(-[^-].*)/gm, '<span class="remove">$1</span>');
            
            // 替换区块头
            html = html.replace(/^(@@.*@@)/gm, '<span class="hunk">$1</span>');
            
            // 替换diff头 - 修复无效转义序列
            html = html.replace(/^(diff --git.*|index.*|---.*|\+\+\+.*)/gm, '<span class="header">$1</span>');
            
            block.innerHTML = html;
          });
        });
        </script>
        """
        
        # 组合所有部分
        return chunks_html + patches_html + applied_chunks_html + remaining_patch_html + style_html
    
    def _get_patch_content(self, context: ModuleContext, patch_type: str) -> str:
        """获取不同类型的补丁内容"""
        try:
            # 使用当前评估会话的目录（从_generate_additional_html_sections方法中获取）
            if hasattr(self, '_current_details_dir') and self._current_details_dir:
                details_dir = self._current_details_dir
                logger.info(f"使用当前会话评估目录: {details_dir}")
            else:
                # 尝试找到当前评估的details目录
                eval_dir = context.base_dir / "evaluations" / self.name
                # 使用当前提交的SHA和当天日期匹配
                timestamp = datetime.now().strftime("%Y%m%d")
                commit_sha = context.commit.commit_sha[:6]
                matched_dirs = list(eval_dir.glob(f"details_{commit_sha}_{timestamp}*"))
                
                if matched_dirs:
                    details_dir = max(matched_dirs, key=lambda p: p.stat().st_mtime)
                    logger.info(f"找到匹配当前提交的评估目录: {details_dir}")
                else:
                    # 如果没找到匹配的，使用最新的
                    all_dirs = list(eval_dir.glob("details_*"))
                    if not all_dirs:
                        logger.warning("未找到任何评估目录")
                        return "未找到评估信息目录"
                    
                    details_dir = max(all_dirs, key=lambda p: p.stat().st_mtime)
                    logger.info(f"使用最新的评估目录: {details_dir}")
            
            # 创建一个函数来从patches_content.json文件获取补丁内容
            def get_content_from_json():
                json_file = details_dir / "patches_content.json"
                if json_file.exists():
                    try:
                        with open(json_file, 'r', encoding='utf-8', errors='ignore') as f:
                            json_data = json.load(f)
                        
                        if patch_type == "original" and "original_patch" in json_data:
                            logger.info(f"从JSON文件获取原始补丁内容: {json_file}")
                            return json_data["original_patch"].replace('<', '&lt;').replace('>', '&gt;')
                        
                        elif patch_type == "applied" and "applied_chunks" in json_data:
                            content = ""
                            for chunk in json_data["applied_chunks"]:
                                content += f"\n\n# ===== 应用成功的补丁块 {chunk.get('index', '?')} =====\n\n"
                                content += chunk.get("content", "")
                            
                            if content:
                                logger.info(f"从JSON文件获取应用成功的补丁内容: {json_file}")
                                return content.replace('<', '&lt;').replace('>', '&gt;')
                        
                        elif patch_type == "remaining" and "remaining_patch" in json_data:
                            logger.info(f"从JSON文件获取剩余补丁内容: {json_file}")
                            return json_data["remaining_patch"].replace('<', '&lt;').replace('>', '&gt;')
                    
                    except Exception as e:
                        logger.error(f"读取JSON文件出错: {e}")
                
                return None
            
            # 检查补丁目录存在性
            patches_dir = details_dir / "patches"
            if not patches_dir.exists():
                logger.warning(f"补丁目录不存在: {patches_dir}")
                
                # 尝试创建patches目录
                try:
                    patches_dir.mkdir(exist_ok=True, parents=True)
                    logger.info(f"成功创建补丁目录: {patches_dir}")
                except Exception as e:
                    logger.error(f"创建补丁目录失败: {e}")
                
                # 首先尝试从patches_content.json获取内容
                json_content = get_content_from_json()
                if json_content:
                    return json_content
                
                # 再尝试直接从context获取补丁内容作为备选方案
                if patch_type == "original" and hasattr(context.commit, "patch_path") and Path(context.commit.patch_path).exists():
                    with open(context.commit.patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                        # 尝试保存到新创建的patches目录
                        try:
                            with open(patches_dir / "original_patch.txt", 'w', encoding='utf-8') as out_f:
                                out_f.write(content)
                            logger.info(f"已将原始补丁内容保存到: {patches_dir / 'original_patch.txt'}")
                        except Exception as e:
                            logger.error(f"保存补丁内容失败: {e}")
                        
                        return content.replace('<', '&lt;').replace('>', '&gt;')
                
                # 针对不同类型的补丁返回特定信息
                if patch_type == "original":
                    return f"补丁目录不存在，且未找到原始补丁内容: {patches_dir}"
                elif patch_type == "applied":
                    return f"补丁目录不存在，且未找到应用成功的补丁内容: {patches_dir}"
                else:
                    return f"补丁目录不存在，且未找到剩余补丁内容: {patches_dir}"
            
            # 尝试从patches_content.json获取内容
            json_content = get_content_from_json()
            if json_content:
                return json_content
            
            # 根据补丁类型获取不同内容
            if patch_type == "original":
                # 获取原始补丁内容
                original_file = patches_dir / "original_patch.txt"
                if original_file.exists():
                    with open(original_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    logger.info(f"成功读取原始补丁内容: {original_file}")
                    return content.replace('<', '&lt;').replace('>', '&gt;')
                else:
                    # 尝试直接从原始补丁文件读取
                    original_patch_diff = details_dir / "original_patch.diff"
                    if original_patch_diff.exists():
                        with open(original_patch_diff, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        logger.info(f"从diff文件读取原始补丁内容: {original_patch_diff}")
                        return content.replace('<', '&lt;').replace('>', '&gt;')
                    
                    logger.warning(f"原始补丁文件不存在: {original_file} 和 {original_patch_diff}")
                    
                    # 尝试从context直接获取
                    if hasattr(context.commit, "patch_path") and Path(context.commit.patch_path).exists():
                        with open(context.commit.patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            
                            # 尝试保存到patches目录
                            try:
                                with open(patches_dir / "original_patch.txt", 'w', encoding='utf-8') as out_f:
                                    out_f.write(content)
                                logger.info(f"已将原始补丁内容保存到: {patches_dir / 'original_patch.txt'}")
                            except Exception as e:
                                logger.error(f"保存补丁内容失败: {e}")
                            
                        logger.info(f"从context获取原始补丁内容: {context.commit.patch_path}")
                        return content.replace('<', '&lt;').replace('>', '&gt;')
                    
                    return "未找到原始补丁内容"
            
            elif patch_type == "applied":
                # 获取应用成功的补丁内容
                applied_file = patches_dir / "all_applied_chunks.txt"
                if applied_file.exists():
                    with open(applied_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    logger.info(f"成功读取应用成功的补丁内容: {applied_file}")
                    return content.replace('<', '&lt;').replace('>', '&gt;')
                else:
                    # 尝试读取各个应用成功的补丁并合并
                    content = ""
                    applied_files = list(patches_dir.glob("applied_chunk_*.txt"))
                    
                    if not applied_files:
                        # 尝试读取diff文件
                        applied_diffs = list(details_dir.glob("applied_chunk_*.diff"))
                        for file in sorted(applied_diffs):
                            with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                                chunk_content = f.read()
                                content += f"\n\n# ===== {file.stem} =====\n\n"
                                content += chunk_content
                                
                                # 尝试保存到patches目录
                                try:
                                    with open(patches_dir / f"{file.stem}.txt", 'w', encoding='utf-8') as out_f:
                                        out_f.write(chunk_content)
                                    logger.info(f"已将补丁块内容保存到: {patches_dir / f'{file.stem}.txt'}")
                                except Exception as e:
                                    logger.error(f"保存补丁块内容失败: {e}")
                        
                        if content:
                            logger.info(f"从diff文件读取应用成功的补丁内容")
                            return content.replace('<', '&lt;').replace('>', '&gt;')
                    
                        # 尝试从context直接获取
                        if context.chunk_analyzer_result and context.chunk_analyzer_result.get("applied_chunk_patches"):
                            for i, chunk_path in enumerate(context.chunk_analyzer_result.get("applied_chunk_patches", []), 1):
                                chunk_file = Path(chunk_path)
                                if chunk_file.exists():
                                    with open(chunk_file, 'r', encoding='utf-8', errors='ignore') as f:
                                        chunk_content = f.read()
                                        content += f"\n\n# ===== 应用成功的补丁块 {i} =====\n\n"
                                        content += chunk_content
                                        
                                        # 尝试保存到patches目录
                                        try:
                                            with open(patches_dir / f"applied_chunk_{i}.txt", 'w', encoding='utf-8') as out_f:
                                                out_f.write(chunk_content)
                                            logger.info(f"已将补丁块内容保存到: {patches_dir / f'applied_chunk_{i}.txt'}")
                                        except Exception as e:
                                            logger.error(f"保存补丁块内容失败: {e}")
                            
                            if content:
                                # 尝试保存合并的内容
                                try:
                                    with open(patches_dir / "all_applied_chunks.txt", 'w', encoding='utf-8') as out_f:
                                        out_f.write(content)
                                    logger.info(f"已将合并的补丁块内容保存到: {patches_dir / 'all_applied_chunks.txt'}")
                                except Exception as e:
                                    logger.error(f"保存合并补丁块内容失败: {e}")
                                
                                logger.info(f"从context获取应用成功的补丁内容")
                                return content.replace('<', '&lt;').replace('>', '&gt;')
                        
                        logger.warning(f"未找到任何应用成功的补丁文件")
                        return "没有应用成功的补丁块"
                    
                    logger.info(f"从各个txt文件读取应用成功的补丁内容")
                    for file in sorted(applied_files):
                        with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                            content += f"\n\n# ===== {file.stem} =====\n\n"
                            content += f.read()
                    
                    return content.replace('<', '&lt;').replace('>', '&gt;')
            
            elif patch_type == "remaining":
                # 获取剩余补丁内容
                remaining_file = patches_dir / "remaining_patch.txt"
                if remaining_file.exists():
                    with open(remaining_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    logger.info(f"成功读取剩余补丁内容: {remaining_file}")
                    return content.replace('<', '&lt;').replace('>', '&gt;')
                else:
                    # 尝试从diff文件读取
                    remaining_diff = details_dir / "remaining_patch.diff"
                    if remaining_diff.exists():
                        with open(remaining_diff, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            
                            # 尝试保存到patches目录
                            try:
                                with open(patches_dir / "remaining_patch.txt", 'w', encoding='utf-8') as out_f:
                                    out_f.write(content)
                                logger.info(f"已将剩余补丁内容保存到: {patches_dir / 'remaining_patch.txt'}")
                            except Exception as e:
                                logger.error(f"保存剩余补丁内容失败: {e}")
                            
                        logger.info(f"从diff文件读取剩余补丁内容: {remaining_diff}")
                        return content.replace('<', '&lt;').replace('>', '&gt;')
                    
                    # 尝试从context直接获取
                    if context.chunk_analyzer_result and context.chunk_analyzer_result.get("remaining_patch"):
                        remaining_patch = Path(context.chunk_analyzer_result.get("remaining_patch"))
                        if remaining_patch.exists():
                            with open(remaining_patch, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                                
                                # 尝试保存到patches目录
                                try:
                                    with open(patches_dir / "remaining_patch.txt", 'w', encoding='utf-8') as out_f:
                                        out_f.write(content)
                                    logger.info(f"已将剩余补丁内容保存到: {patches_dir / 'remaining_patch.txt'}")
                                except Exception as e:
                                    logger.error(f"保存剩余补丁内容失败: {e}")
                                
                            logger.info(f"从context获取剩余补丁内容: {remaining_patch}")
                            return content.replace('<', '&lt;').replace('>', '&gt;')
                    
                    logger.warning(f"未找到剩余补丁文件")
                    return "没有剩余未应用的补丁内容"
            
            return f"未识别的补丁类型: {patch_type}"
            
        except Exception as e:
            logger.error(f"获取补丁内容时出错: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return f"获取补丁内容时出错: {str(e)}"