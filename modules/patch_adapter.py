# from typing import Dict, Any
# from pathlib import Path
# from loguru import logger
# from .base_module import BaseModule, ModuleType
# from patch_processor import PatchProcessor

from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from loguru import logger
import json
import os
import re
import subprocess
import traceback
import difflib
from datetime import datetime
from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext
import unidiff
from difflib import SequenceMatcher

class PatchAdapterModule(BaseModule):
    """补丁适配模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.PATCH_ADAPTER
        self.name = "patch_adapter"
        self.metrics = {
            'total_attempts': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'execution_time': 0,
            'error_types': {},
            'apply_success': False,
            'apply_errors': []
        }
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行补丁适配"""
        if not self._should_run(context):
            return context
            
        start_time = datetime.now()
        
        try:
            # 获取LLM生成的补丁内容
            llm_patch_content = context.llm_output.get('content')
            if not llm_patch_content:
                raise ValueError("没有找到LLM生成的补丁内容")
            
            # 保存LLM生成的原始补丁
            raw_patch_path = self._save_raw_patch(context, llm_patch_content)
            
            # 解析补丁内容
            parsed_patches = self._parse_patch_content(llm_patch_content)
            
            # 创建适配目录
            adapted_dir = context.commit.base_dir / f"adapted_{context.config.target_version}"
            adapted_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建测试分支
            branch_name = self._prepare_test_branch(context)
            if not branch_name:
                raise ValueError("准备测试分支失败")
            
            try:
                # 适配并应用补丁
                adapted_patches = self._adapt_and_apply_patches(context, parsed_patches, branch_name, adapted_dir)
                
                # 如果适配成功，导出最终补丁
                if adapted_patches:
                    final_patch_path = self._export_final_patch(context, branch_name)
                    
                    # 测试补丁是否可以应用
                    apply_result = self._test_patch_apply(context, final_patch_path)
                    
                    # 更新上下文
                    # 确保context支持动态属性设置
                    if hasattr(context, '__dict__'):
                        context.patch_adapter_result = {
                            'success': True,
                            'message': '补丁适配成功',
                            'adapted_patches': adapted_patches,
                            'final_patch_path': str(final_patch_path),
                            'apply_result': apply_result,
                            'timestamp': datetime.now().isoformat()
                        }
                    else:
                        # 将结果存储在现有字段中
                        if not hasattr(context, 'results'):
                            setattr(context, 'results', {})
                        context.results['patch_adapter_result'] = {
                            'success': True,
                            'message': '补丁适配成功',
                            'adapted_patches': adapted_patches,
                            'final_patch_path': str(final_patch_path),
                            'apply_result': apply_result,
                            'timestamp': datetime.now().isoformat()
                        }
                    
                    # 更新指标
                    self._update_metrics(
                        success=True,
                        apply_success=apply_result.get('success', False),
                        apply_error=apply_result.get('error'),
                        execution_time=(datetime.now() - start_time).total_seconds()
                    )
                else:
                    # 更新上下文
                    if hasattr(context, '__dict__'):
                        context.patch_adapter_result = {
                            'success': False,
                            'message': '没有成功适配的补丁',
                            'timestamp': datetime.now().isoformat()
                        }
                    else:
                        if not hasattr(context, 'results'):
                            setattr(context, 'results', {})
                        context.results['patch_adapter_result'] = {
                            'success': False,
                            'message': '没有成功适配的补丁',
                            'timestamp': datetime.now().isoformat()
                        }
                    
                    # 更新指标
                    self._update_metrics(
                        success=False,
                        error_type='no_adapted_patches',
                        execution_time=(datetime.now() - start_time).total_seconds()
                    )
                
            finally:
                # 清理测试分支
                self._cleanup_test_branch(context, branch_name)
            
        except Exception as e:
            logger.error(f"补丁适配过程发生错误: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            # 安全地设置结果
            if hasattr(context, '__dict__'):
                context.patch_adapter_result = {
                    'success': False,
                    'message': '处理过程发生错误',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                if not hasattr(context, 'results'):
                    setattr(context, 'results', {})
                context.results['patch_adapter_result'] = {
                    'success': False,
                    'message': '处理过程发生错误',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
            
            if hasattr(context, 'last_error'):
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
    
    def _save_raw_patch(self, context: ModuleContext, patch_content: str) -> Path:
        """保存LLM生成的原始补丁"""
        # 创建目录
        patch_dir = context.commit.base_dir / "adapted_patches"
        patch_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"raw_patch_{timestamp}.patch"
        
        # 保存补丁
        patch_path = patch_dir / filename
        with open(patch_path, 'w') as f:
            f.write(patch_content)
        
        logger.info(f"原始补丁已保存到: {patch_path}")
        return patch_path
    
    def _parse_patch_content(self, patch_content: str) -> List[Dict[str, Any]]:
        """解析补丁内容"""
        try:
            # 使用unidiff解析补丁
            patch_set = unidiff.PatchSet.from_string(patch_content)
            
            # 转换为我们自己的结构
            parsed_patches = []
            for patched_file in patch_set:
                file_patch = {
                    'source_file': patched_file.source_file,
                    'target_file': patched_file.target_file,
                    'hunks': []
                }
                
                for hunk in patched_file:
                    parsed_hunk = {
                        'source_start': hunk.source_start,
                        'source_length': hunk.source_length,
                        'target_start': hunk.target_start,
                        'target_length': hunk.target_length,
                        'section_header': hunk.section_header,
                        'lines': []
                    }
                    
                    for line in hunk:
                        if line.is_added:
                            line_type = 'add'
                        elif line.is_removed:
                            line_type = 'remove'
                        else:
                            line_type = 'context'
                        
                        parsed_hunk['lines'].append((line_type, line.value.rstrip('\n')))
                    
                    file_patch['hunks'].append(parsed_hunk)
                
                parsed_patches.append(file_patch)
            
            return parsed_patches
        except Exception as e:
            logger.error(f"解析补丁内容失败: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            # 尝试使用备选解析方法
            return self._fallback_parse_patch(patch_content)
    
    def _fallback_parse_patch(self, patch_content: str) -> List[Dict[str, Any]]:
        """备用补丁解析方法，用于unidiff失败时"""
        parsed_patches = []
        
        # 按文件拆分补丁
        file_pattern = r'(?:diff --git a/(.*?) b/(.*?)|--- a/(.*?)\n\+\+\+ b/(.*?))\n'
        file_matches = re.finditer(file_pattern, patch_content)
        
        last_pos = 0
        for match in file_matches:
            # 获取文件名
            file_path = None
            for i in range(1, 5):
                if match.group(i):
                    file_path = match.group(i)
                    break
            
            if not file_path:
                continue
                
            # 获取下一个文件的位置或文件结束
            next_pos = patch_content.find('diff --git', match.end())
            if next_pos == -1:
                file_content = patch_content[match.start():]
            else:
                file_content = patch_content[match.start():next_pos]
            
            # 解析hunk
            hunks = []
            hunk_pattern = r'@@ -([\d,]+) \+([\d,]+) @@(.*?)(?=\n@@|\Z)'
            hunk_matches = re.finditer(hunk_pattern, file_content, re.DOTALL)
            
            for hunk_match in hunk_matches:
                # 解析hunk头
                source_info = hunk_match.group(1)
                target_info = hunk_match.group(2)
                section_header = hunk_match.group(3).strip() if hunk_match.group(3) else ''
                
                # 解析起始行和长度
                try:
                    if ',' in source_info:
                        source_start, source_length = map(int, source_info.split(','))
                    else:
                        source_start = int(source_info)
                        source_length = 1
                        
                    if ',' in target_info:
                        target_start, target_length = map(int, target_info.split(','))
                    else:
                        target_start = int(target_info)
                        target_length = 1
                except ValueError:
                    # 跳过无法解析的hunk
                    logger.warning(f"无法解析hunk头: {hunk_match.group(0)}")
                    continue
                
                # 解析hunk内容
                hunk_content = hunk_match.group(0)
                lines = []
                
                for line in hunk_content.splitlines()[1:]:  # 跳过@@ 行
                    if not line:
                        continue
                        
                    if line.startswith('+'):
                        line_type = 'add'
                    elif line.startswith('-'):
                        line_type = 'remove'
                    else:
                        line_type = 'context'
                    
                    # 跳过第一个字符
                    lines.append((line_type, line[1:] if line else ''))
                
                hunks.append({
                    'source_start': source_start,
                    'source_length': source_length,
                    'target_start': target_start,
                    'target_length': target_length,
                    'section_header': section_header,
                    'lines': lines
                })
            
            # 添加到解析结果
            if hunks:
                parsed_patches.append({
                    'source_file': file_path,
                    'target_file': file_path,
                    'hunks': hunks
                })
            
            last_pos = match.end()
        
        return parsed_patches
    
    def _prepare_test_branch(self, context: ModuleContext) -> str:
        """准备测试分支"""
        try:
            # 使用target_version作为分支名的一部分
            branch_name = f"test_adapt_{context.config.target_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 检查分支是否存在，如果存在则删除
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=context.config.repo_path,
                capture_output=True,
                text=True
            )
            
            # 创建新分支
            subprocess.run(
                ['git', 'checkout', '-b', branch_name, context.config.target_version],
                cwd=context.config.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            logger.info(f"创建测试分支: {branch_name}")
            return branch_name
        except Exception as e:
            logger.error(f"创建测试分支失败: {e}")
            return ""
    
    def _cleanup_test_branch(self, context: ModuleContext, branch_name: str) -> None:
        """清理测试分支"""
        try:
            # 检查分支是否存在
            branches = subprocess.run(
                ['git', 'branch'],
                cwd=context.config.repo_path,
                check=False,
                capture_output=True,
                text=True
            ).stdout
            
            if branch_name in branches:
                logger.info(f"清理测试分支: {branch_name}")
                
                # 切换到master或main分支
                default_branches = ['master', 'main', context.config.target_version]
                for default_branch in default_branches:
                    try:
                        subprocess.run(
                            ['git', 'checkout', default_branch],
                            cwd=context.config.repo_path,
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
                    cwd=context.config.repo_path,
                    check=False,
                    capture_output=True,
                    text=True
                )
        except Exception as e:
            logger.error(f"清理测试分支失败: {e}")
    
    def _adapt_and_apply_patches(self, context: ModuleContext, parsed_patches: List[Dict[str, Any]], 
                                branch_name: str, adapted_dir: Path) -> List[Dict[str, Any]]:
        """适配并应用补丁"""
        if not parsed_patches:
            logger.warning("没有找到可解析的补丁")
            return []
        
        adapted_files = []
        
        for patch in parsed_patches:
            try:
                # 获取目标文件路径
                target_file = patch['target_file']
                source_file_path = Path(context.config.repo_path) / target_file
                
                # 检查文件是否存在
                if not source_file_path.exists():
                    logger.warning(f"目标文件不存在: {source_file_path}")
                    continue
                
                # 读取原始文件内容
                with open(source_file_path, 'r') as f:
                    file_lines = f.readlines()
                
                # 应用所有的hunk
                modified_lines = file_lines.copy()
                for hunk in patch['hunks']:
                    # 找到对应的位置
                    position = self._find_hunk_position(hunk, modified_lines)
                    if position == -1:
                        logger.warning(f"无法定位hunk在文件中的位置: {target_file}")
                        continue
                    
                    # 应用修改
                    modified_lines = self._apply_hunk(hunk, modified_lines, position)
                
                # 验证修改的合理性
                if not self.validate_modification(file_lines, modified_lines):
                    logger.warning(f"文件修改验证失败: {target_file}")
                    continue
                
                # 保存适配后的文件
                adapted_file_path = adapted_dir / target_file
                adapted_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(adapted_file_path, 'w') as f:
                    f.writelines(modified_lines)
                
                logger.info(f"适配文件已保存: {adapted_file_path}")
                
                # 应用修改到测试分支
                os.makedirs(os.path.dirname(source_file_path), exist_ok=True)
                with open(source_file_path, 'w') as f:
                    f.writelines(modified_lines)
                
                # 添加修改到Git
                subprocess.run(
                    ['git', 'add', target_file],
                    cwd=context.config.repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                adapted_files.append({
                    'file': target_file,
                    'adapted_path': str(adapted_file_path)
                })
                
            except Exception as e:
                logger.error(f"适配文件 {target_file} 时出错: {e}")
                logger.error(f"错误堆栈: {traceback.format_exc()}")
        
        # 创建提交
        if adapted_files:
            commit_message = f"Adapted patch for {context.commit.commit_id} to {context.config.target_version}"
            subprocess.run(
                ['git', 'commit', '-m', commit_message],
                cwd=context.config.repo_path,
                check=False,
                capture_output=True,
                text=True
            )
        
        return adapted_files
    
    def _find_hunk_position(self, hunk: Dict[str, Any], file_lines: List[str]) -> int:
        """找到hunk在文件中的位置"""
        # 从hunk中提取上下文行
        context_lines = [line[1] for line in hunk['lines'] if line[0] == 'context']
        removed_lines = [line[1] for line in hunk['lines'] if line[0] == 'remove']
        
        if not context_lines and not removed_lines:
            # 没有上下文或删除行，使用行号定位
            return hunk['source_start'] - 1  # 转为0-based索引
        
        # 构建上下文模式
        if removed_lines:
            # 使用被删除的行作为匹配模式
            pattern_lines = removed_lines
        else:
            # 使用上下文行作为匹配模式
            pattern_lines = context_lines
        
        # 在文件中搜索模式
        best_match_pos = -1
        best_match_score = 0
        
        for i in range(len(file_lines) - len(pattern_lines) + 1):
            current_lines = [line.rstrip('\n') for line in file_lines[i:i+len(pattern_lines)]]
            
            # 计算匹配得分
            score = sum(1 for a, b in zip(current_lines, pattern_lines) if a == b)
            
            if score > best_match_score:
                best_match_score = score
                best_match_pos = i
        
        # 如果匹配得分过低，认为找不到位置
        if best_match_score < len(pattern_lines) * 0.7:
            return -1
        
        return best_match_pos
    
    def _apply_hunk(self, hunk: Dict[str, Any], file_lines: List[str], position: int) -> List[str]:
        """应用hunk的修改"""
        if position == -1:
            return file_lines
        
        new_lines = file_lines[:position]
        current_pos = position
        
        # 应用修改
        i = 0
        while i < len(hunk['lines']):
            line_type, content = hunk['lines'][i]
            
            if line_type == 'remove':
                # 删除行：跳过原文件中的对应行
                current_pos += 1
            elif line_type == 'add':
                # 添加行：插入新内容
                new_lines.append(content + '\n')
            elif line_type == 'context':
                # 上下文行：保持原样
                if current_pos < len(file_lines):
                    new_lines.append(file_lines[current_pos])
                    current_pos += 1
            
            i += 1
        
        # 添加剩余的行
        new_lines.extend(file_lines[current_pos:])
        return new_lines
    
    def validate_modification(self, original_lines, modified_lines):
        """
        验证修改的合理性
        
        Args:
            original_lines: 原始文件的行列表
            modified_lines: 修改后的行列表
            
        Returns:
            bool: 修改是否合理
        """
        try:
            # 1. 基本检查
            if not modified_lines:
                logger.error("修改后的文件为空")
                return False
            
            # 2. 检查修改幅度
            if len(modified_lines) < len(original_lines) * 0.5 or \
               len(modified_lines) > len(original_lines) * 1.5:
                logger.warning("文件大小变化过大")
                return False
            
            # 3. 括号匹配检查
            if not self._check_brackets(modified_lines):
                logger.error("括号匹配错误")
                return False
            
            # 4. 缩进一致性检查
            if not self._check_indentation(modified_lines):
                logger.error("缩进不一致")
                return False
            
            # 5. 关键结构检查
            if not self._check_key_structures(original_lines, modified_lines):
                logger.error("关键结构被破坏")
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"验证过程出错: {str(e)}")
            return False
    
    def _check_brackets(self, lines: List[str]) -> bool:
        """检查括号匹配"""
        stack = []
        brackets = {')': '(', '}': '{', ']': '['}
        
        for line in lines:
            for char in line:
                if char in '({[':
                    stack.append(char)
                elif char in ')}]':
                    if not stack or stack.pop() != brackets[char]:
                        return False
                    
        return len(stack) == 0
    
    def _check_indentation(self, lines: List[str]) -> bool:
        """检查缩进一致性"""
        prev_indent = 0
        for line in lines:
            if not line.strip():  # 跳过空行
                continue
            
            # 计算当前行的缩进
            current_indent = len(line) - len(line.lstrip())
            
            # 缩进变化不应过大
            if abs(current_indent - prev_indent) > 8:  # 允许最大缩进变化
                return False
            
            prev_indent = current_indent
        return True
    
    def _check_key_structures(self, original_lines: List[str], modified_lines: List[str]) -> bool:
        """检查关键结构完整性"""
        # 提取关键标识符（函数名、类名等）
        def extract_identifiers(lines):
            identifiers = set()
            # 简单的函数/类定义模式
            patterns = [
                r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
                r'class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:\(]'
            ]
            for line in lines:
                for pattern in patterns:
                    matches = re.finditer(pattern, line)
                    for match in matches:
                        identifiers.add(match.group(1))
            return identifiers
        
        original_ids = extract_identifiers(original_lines)
        modified_ids = extract_identifiers(modified_lines)
        
        # 检查重要标识符是否保留
        important_ids_preserved = all(id_ in modified_ids 
                                    for id_ in original_ids 
                                    if not id_.startswith('_'))
        
        # 检查修改是否引入了过多的新标识符
        new_ids = modified_ids - original_ids
        if len(new_ids) > len(original_ids) * 0.3:  # 允许30%的新标识符
            return False
        
        return important_ids_preserved
    
    def _export_final_patch(self, context: ModuleContext, branch_name: str) -> Path:
        """导出最终补丁"""
        # 创建输出目录
        output_dir = context.commit.base_dir / "final_patches"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"adapted_patch_{context.config.target_version}_{timestamp}.patch"
        
        # 导出补丁
        output_path = output_dir / filename
        
        # 生成补丁文件
        subprocess.run(
            ['git', 'format-patch', '-1', '--stdout', 'HEAD'],
            cwd=context.config.repo_path,
            check=True,
            stdout=open(output_path, 'w'),
            text=True
        )
        
        logger.info(f"最终补丁已导出到: {output_path}")
        return output_path
    
    def _test_patch_apply(self, context: ModuleContext, patch_path: Path) -> Dict[str, Any]:
        """测试补丁是否可应用"""
        result = {
            'success': False,
            'error': None,
            'error_type': None,
            'output': None,
        }
        
        # 创建测试分支名
        branch_name = f"test_apply_{context.config.target_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # 准备测试分支
            branches = subprocess.run(
                ['git', 'branch'],
                cwd=context.config.repo_path,
                check=True,
                capture_output=True,
                text=True
            ).stdout
            
            # 如果分支已存在，先删除
            if branch_name in branches:
                subprocess.run(
                    ['git', 'branch', '-D', branch_name],
                    cwd=context.config.repo_path,
                    check=False,
                    capture_output=True,
                    text=True
                )
            
            # 创建新分支
            checkout_result = subprocess.run(
                ['git', 'checkout', '-b', branch_name, context.config.target_version],
                cwd=context.config.repo_path,
                capture_output=True,
                text=True
            )
            
            if checkout_result.returncode != 0:
                result['error'] = f"创建测试分支失败: {checkout_result.stderr}"
                result['error_type'] = 'branch_creation_failed'
                return result
            
            # 应用补丁
            apply_process = subprocess.run(
                ['git', 'am', str(patch_path.absolute())],
                cwd=context.config.repo_path,
                capture_output=True,
                text=True
            )
            
            if apply_process.returncode == 0:
                result['success'] = True
                result['output'] = apply_process.stdout
                logger.info(f"补丁应用成功: {patch_path}")
            else:
                result['error'] = apply_process.stderr
                result['error_type'] = self._categorize_error(apply_process.stderr)
                logger.error(f"补丁应用失败: {result['error']}")
            
            return result
        except Exception as e:
            result['error'] = str(e)
            result['error_type'] = 'exception'
            logger.error(f"应用补丁时发生错误: {e}")
            return result
        finally:
            # 无论成功与否，都清理git am状态
            subprocess.run(['git', 'am', '--abort'], 
                          cwd=context.config.repo_path, 
                          capture_output=True,
                          text=True)
            
            # 清理测试分支
            self._cleanup_test_branch(context, branch_name)
    
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

# class PatchAdapterModule(BaseModule):
#     """补丁适配模块"""
#     def __init__(self, config: Dict[str, Any]):
#         super().__init__(config)
#         self.type = ModuleType.PATCH_ADAPTER
#         self.name = "patch_adapter"
#         self.processor = PatchProcessor(config)
#         self.successful_patches = 0
#         self.failed_patches = 0
    
#     def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
#         if not context.get("llm_output"):
#             logger.info("没有LLM输出，跳过补丁适配")
#             return context
        
#         logger.info("开始应用LLM生成的补丁")
#         try:
#             adapted_patches = []
#             for response in context["llm_output"]["openai_responses"]:
#                 try:
#                     output_path = self.processor.save_response_to_project(response)
#                     self.processor.apply_llm_patch(output_path)
#                     adapted_patches.append({
#                         'path': str(output_path),
#                         'success': True
#                     })
#                     self.successful_patches += 1
#                 except Exception as e:
#                     logger.error(f"应用补丁失败: {e}")
#                     adapted_patches.append({
#                         'success': False,
#                         'error': str(e)
#                     })
#                     self.failed_patches += 1
            
#             context["adapted_patches"] = adapted_patches
            
#         except Exception as e:
#             logger.error(f"补丁适配过程发生错误: {e}")
#             context["patch_adapter_error"] = str(e)
        
#         return context
    
#     def get_metrics(self) -> Dict[str, Any]:
#         total_patches = self.successful_patches + self.failed_patches
#         return {
#             "successful_patches": self.successful_patches,
#             "failed_patches": self.failed_patches,
#             "success_rate": (
#                 self.successful_patches / total_patches 
#                 if total_patches > 0 else 0
#             )
#         } 