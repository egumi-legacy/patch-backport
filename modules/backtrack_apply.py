from typing import Dict, Any, Optional, List
from pathlib import Path
import subprocess
import re
from datetime import datetime
from loguru import logger
from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext
from patch_utils import download_patch

class BacktrackApplyModule(BaseModule):
    """回溯补丁应用模块 - 向前尝试应用补丁到不同历史版本"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.DIRECT_APPLY  # 使用相同的类型
        self.name = "backtrack_apply"
        
        # 确保配置中包含必要的路径
        if not config.repo_path:
            raise ValueError("repo_path is required")
        
        # 设置默认回溯停止点
        self.stop_at = config.module_configs.get('backtrack_apply', {}).get('stop_at', None)
        self.max_attempts = config.module_configs.get('backtrack_apply', {}).get('max_attempts', 50)
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行回溯补丁应用"""
        if not self._should_run(context):
            return context
        
        start_time = datetime.now()
        commit_sha = context.commit.commit_sha
        patch_url = context.commit.patch_url
        
        try:
            # 下载补丁文件
            if not context.commit.patch_path or not Path(context.commit.patch_path).exists():
                patch_path = self._download_patch(context)
                if not patch_path or not patch_path.exists():
                    raise ValueError("下载补丁失败")
            
                context.commit.patch_path = patch_path
                logger.info(f"下载补丁成功: {patch_path}")
            else:
                patch_path = Path(context.commit.patch_path)
            logger.info(f"补丁文件路径: {patch_path}")
            
            # 找到修改的文件
            modified_files = self._find_modified_files(context, patch_path)
            if not modified_files:
                logger.warning(f"无法找到修改的文件: {patch_path}")
                context.backtrack_result = {
                    'success': False,
                    'message': '无法找到修改的文件',
                    'error': '补丁没有修改任何文件',
                    'timestamp': datetime.now().isoformat()
                }
                return context
            
            logger.info(f"找到修改的文件: {modified_files}")
            
            # 先尝试路径自适应应用
            adaptive_result = self._try_adaptive_apply(context, patch_path, modified_files)
            
            # 如果自适应应用成功，直接返回结果
            if adaptive_result and adaptive_result.get('success'):
                context.backtrack_result = {
                    'success': True,
                    'message': adaptive_result.get('message', '路径自适应成功'),
                    'applicable_version': adaptive_result.get('applicable_version'),
                    'last_compatible_commit': adaptive_result.get('last_compatible_commit'),
                    'modified_files': modified_files,
                    'adapted_patch_path': adaptive_result.get('adapted_patch_path'),
                    'attempt_count': 1,
                    'method': 'path_adaptation',
                    'timestamp': datetime.now().isoformat()
                }
                
                # 更新指标
                self._update_metrics(
                    success=True,
                    error_type=None,
                    execution_time=(datetime.now() - start_time).total_seconds()
                )
                
                # 保存指标
                self._save_metrics(context)
                
                return context
            
            # 如果自适应应用失败，使用回溯方法
            logger.info("路径自适应应用失败，尝试回溯方法")
            
            # 执行回溯应用
            backtrack_result = self._backtrack_apply(context, patch_path, modified_files)
            
            # 更新结果
            context.backtrack_result = {
                'success': backtrack_result['success'],
                'message': backtrack_result['message'],
                'error': backtrack_result.get('error'),
                'applicable_version': backtrack_result.get('applicable_version'),
                'last_compatible_commit': backtrack_result.get('last_compatible_commit'),
                'modified_files': modified_files,
                'attempt_count': backtrack_result.get('attempt_count', 0),
                'method': 'backtrack_traversal',
                'timestamp': datetime.now().isoformat()
            }
            
            # 更新指标
            self._update_metrics(
                success=backtrack_result['success'],
                error_type=backtrack_result.get('error_type'),
                execution_time=(datetime.now() - start_time).total_seconds()
            )
            
        except Exception as e:
            logger.error(f"回溯应用过程发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            context.backtrack_result = {
                'success': False,
                'message': '处理过程发生错误',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            
            self._update_metrics(
                success=False,
                error_type='exception',
                execution_time=(datetime.now() - start_time).total_seconds()
            )
        
        # 保存指标
        self._save_metrics(context)
        
        return context
    
    def _download_patch(self, context: ModuleContext) -> Path:
        """下载补丁文件"""
        patch_dir = context.patch_dir
        patch_path = patch_dir / f"upstream_{context.commit.commit_sha[:6]}.patch"
        
        if patch_path.exists():
            logger.info(f"补丁文件已存在: {patch_path}")
            return patch_path.absolute()
        else:
            logger.info(f"下载补丁: {context.commit.patch_url}")
            success = download_patch(context.commit.patch_url, patch_path).exists()
            
            if success:
                logger.info(f"补丁下载成功: {patch_path}")
                return patch_path.absolute()
            else:
                logger.error(f"补丁下载失败: {context.commit.patch_url}")
                return None
    
    def _find_modified_files(self, context: ModuleContext, patch_path: Path) -> List[str]:
        """从补丁中找出修改的文件"""
        modified_files = []
        
        try:
            # 使用git diff --name-only 解析补丁文件
            with open(patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                patch_content = f.read()
            
            # 使用正则表达式提取文件名
            # 匹配 diff --git a/file.txt b/file.txt 格式
            diff_pattern = r"diff --git a/([^\s]+) b/([^\s]+)"
            matches = re.findall(diff_pattern, patch_content)
            
            if matches:
                for match in matches:
                    file_path = match[0]  # a和b应该是相同的文件，取第一个
                    if file_path not in modified_files:
                        modified_files.append(file_path)
            
            logger.info(f"从补丁中找到 {len(modified_files)} 个修改的文件")
            return modified_files
            
        except Exception as e:
            logger.error(f"解析补丁文件失败: {e}")
            return []
    
    def _map_file_paths(self, repo_path: str, modified_files: List[str]) -> Dict[str, str]:
        """
        将补丁中的文件路径映射到目标仓库中的实际路径
        
        :param repo_path: 仓库路径
        :param modified_files: 从补丁解析出的修改文件列表
        :return: 文件路径映射字典，键为补丁中的路径，值为目标仓库中的路径
        """
        path_mapping = {}
        
        try:
            # 不再切换分支，直接在当前分支（目标仓库）中查找文件
            for file_path in modified_files:
                # 检查文件是否直接存在
                direct_path = Path(repo_path) / file_path
                if direct_path.exists():
                    path_mapping[file_path] = file_path
                    logger.info(f"文件直接存在: {file_path}")
                    continue
                
                # 如果文件不直接存在，尝试通过文件名查找
                file_name = Path(file_path).name
                
                # 使用git ls-files查找所有可能的路径
                try:
                    result = subprocess.run(
                        ['git', 'ls-files', f"*{file_name}"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    
                    potential_paths = result.stdout.strip().split('\n')
                    potential_paths = [p for p in potential_paths if p]  # 过滤空行
                    
                    if potential_paths:
                        # 如果找到多个文件，使用路径相似度来选择最佳匹配
                        if len(potential_paths) > 1:
                            best_match = self._find_best_path_match(file_path, potential_paths)
                            path_mapping[file_path] = best_match
                            logger.info(f"文件路径映射: {file_path} -> {best_match}")
                        else:
                            path_mapping[file_path] = potential_paths[0]
                            logger.info(f"文件路径映射: {file_path} -> {potential_paths[0]}")
                    else:
                        logger.warning(f"在目标仓库中未找到文件: {file_path}")
                        # 尝试查看文件是否有目录变更但名称相同的情况
                        logger.info(f"尝试在整个仓库中搜索文件: {file_name}")
                        try:
                            # 使用find命令在整个仓库中查找文件
                            find_result = subprocess.run(
                                ['find', repo_path, '-name', file_name, '-type', 'f'],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            
                            find_paths = find_result.stdout.strip().split('\n')
                            find_paths = [p for p in find_paths if p]  # 过滤空行
                            
                            # 转换为相对路径
                            repo_path_obj = Path(repo_path)
                            find_paths = [str(Path(p).relative_to(repo_path_obj)) for p in find_paths if Path(p).is_relative_to(repo_path_obj)]
                            
                            if find_paths:
                                if len(find_paths) > 1:
                                    best_match = self._find_best_path_match(file_path, find_paths)
                                    path_mapping[file_path] = best_match
                                    logger.info(f"通过find命令找到文件: {file_path} -> {best_match}")
                                else:
                                    path_mapping[file_path] = find_paths[0]
                                    logger.info(f"通过find命令找到文件: {file_path} -> {find_paths[0]}")
                            else:
                                logger.warning(f"在整个仓库中也未找到文件: {file_name}")
                        except Exception as e:
                            logger.warning(f"使用find命令查找文件失败: {e}")
                
                except subprocess.CalledProcessError as e:
                    logger.warning(f"查找文件 {file_name} 失败: {e.stderr}")
            
            return path_mapping
            
        except Exception as e:
            logger.error(f"映射文件路径时发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return {file_path: file_path for file_path in modified_files}  # 默认返回原路径
    
    def _find_best_path_match(self, original_path: str, candidate_paths: List[str]) -> str:
        """
        在多个候选路径中找出与原始路径最相似的一个
        
        :param original_path: 原始文件路径
        :param candidate_paths: 候选路径列表
        :return: 最佳匹配的路径
        """
        # 使用目录部分和最长公共子序列来计算相似度
        
        # 原始路径的目录部分
        original_dir = str(Path(original_path).parent)
        
        best_match = candidate_paths[0]
        highest_score = 0
        
        for path in candidate_paths:
            # 候选路径的目录部分
            candidate_dir = str(Path(path).parent)
            
            # 计算目录部分的相似度
            dir_similarity = self._longest_common_subsequence(original_dir, candidate_dir)
            
            # 如果分数更高，更新最佳匹配
            if dir_similarity > highest_score:
                highest_score = dir_similarity
                best_match = path
        
        return best_match
        
    def _longest_common_subsequence(self, str1: str, str2: str) -> int:
        """
        计算两个字符串的最长公共子序列长度
        
        :param str1: 第一个字符串
        :param str2: 第二个字符串
        :return: 最长公共子序列的长度
        """
        m, n = len(str1), len(str2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if str1[i - 1] == str2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        
        return dp[m][n]

    def _backtrack_apply(self, context: ModuleContext, patch_path: Path, modified_files: List[str]) -> Dict[str, Any]:
        """执行回溯补丁应用"""
        repo_path = context.config.repo_path
        result = {
            'success': False,
            'message': '',
            'error': None,
            'error_type': None,
            'applicable_version': None,
            'last_compatible_commit': None,
            'attempt_count': 0
        }
        
        # 获取当前分支
        try:
            current_branch = self._get_current_branch(repo_path)
            logger.info(f"当前分支: {current_branch}")
        except Exception as e:
            logger.error(f"获取当前分支失败: {e}")
            result['error'] = f"获取当前分支失败: {e}"
            result['error_type'] = 'branch_error'
            return result
        
        # 准备一个临时分支
        temp_branch = f"backtrack_{context.commit.commit_sha[:6]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            # 映射文件路径到目标仓库
            path_mapping = self._map_file_paths(repo_path, modified_files)
            if not path_mapping:
                logger.error("无法映射任何文件路径")
                result['error'] = "无法映射文件路径"
                result['error_type'] = 'path_mapping_failed'
                return result
                
            logger.info(f"文件路径映射: {path_mapping}")
            
            # 获取有效的映射文件列表
            mapped_files = list(path_mapping.values())
            if not mapped_files:
                logger.error("没有有效的映射文件")
                result['error'] = "没有有效的映射文件"
                result['error_type'] = 'no_valid_files'
                return result
            
            # 如果有指定停止点，找到它在修改文件的历史记录中的位置
            stop_commit = None
            if self.stop_at:
                try:
                    stop_commit = self._resolve_ref(repo_path, self.stop_at)
                    logger.info(f"停止点解析为commit: {stop_commit}")
                except Exception as e:
                    logger.error(f"解析停止点失败: {e}")
                    
            # 获取映射后文件的提交历史
            file_history = []
            for file_path in mapped_files:
                history = self._get_file_history(repo_path, file_path, stop_commit)
                file_history.extend(history)
            
            # 去重并排序
            unique_commits = list(set(file_history))
            unique_commits.sort(key=lambda x: file_history.count(x), reverse=True)
            
            logger.info(f"找到 {len(unique_commits)} 个历史提交")
            
            # 逐个尝试应用补丁
            attempt_count = 0
            
            for commit in unique_commits:
                if attempt_count >= self.max_attempts:
                    logger.warning(f"达到最大尝试次数 {self.max_attempts}")
                    break
                
                attempt_count += 1
                logger.info(f"尝试应用补丁到 {commit[:8]} (尝试 {attempt_count}/{len(unique_commits)})")
                
                # 创建临时分支并应用补丁
                branch_created = False
                try:
                    # 创建临时分支
                    branch_created = self._create_temp_branch(repo_path, temp_branch, commit)
                    if not branch_created:
                        logger.warning(f"创建临时分支失败，跳过提交: {commit[:8]}")
                        continue
                    
                    # 尝试应用补丁
                    apply_result = self._apply_patch(repo_path, patch_path)
                    
                    if apply_result['success']:
                        result['success'] = True
                        result['message'] = f"补丁可以应用于 {commit[:8]}"
                        result['applicable_version'] = commit
                        result['last_compatible_commit'] = commit
                        break
                    
                    logger.info(f"补丁无法应用于 {commit[:8]}: {apply_result.get('error', '未知错误')}")
                    
                finally:
                    # 无论成功与否，都清理临时分支
                    if branch_created:
                        self._cleanup_temp_branch(repo_path, temp_branch, current_branch)
            
            result['attempt_count'] = attempt_count
            
            if not result['success']:
                result['message'] = "无法找到可应用的版本"
                result['error'] = f"尝试了 {attempt_count} 个版本，均无法应用补丁"
                result['error_type'] = 'no_compatible_version'
            
            return result
            
        except Exception as e:
            logger.error(f"回溯应用过程发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            result['error'] = str(e)
            result['error_type'] = 'exception'
            return result
            
        finally:
            # 确保切回原始分支
            try:
                current_repo_branch = self._get_current_branch(repo_path)
                if current_repo_branch != current_branch:
                    logger.warning(f"检测到分支未切回原始分支，当前为 {current_repo_branch}，应为 {current_branch}")
                    subprocess.run(
                        ['git', 'checkout', current_branch],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    logger.info(f"已强制切回原始分支: {current_branch}")
                
                # 检查临时分支是否存在并清理
                branches_result = subprocess.run(
                    ['git', 'branch'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
                if branches_result.returncode == 0 and temp_branch in branches_result.stdout:
                    logger.warning(f"临时分支 {temp_branch} 仍然存在，尝试清理")
                    subprocess.run(
                        ['git', 'branch', '-D', temp_branch],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        check=False
                    )
            except Exception as cleanup_error:
                logger.error(f"最终清理过程发生错误: {cleanup_error}")

    def _get_current_branch(self, repo_path: str) -> str:
        """获取当前分支名"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"获取当前分支失败: {e.stderr}")
            raise ValueError(f"获取当前分支失败: {e.stderr}")
    
    def _resolve_ref(self, repo_path: str, ref: str) -> str:
        """解析引用（分支或标签）为提交哈希"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', ref],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"解析引用 {ref} 失败: {e.stderr}")
            raise ValueError(f"解析引用失败: {e.stderr}")
    
    def _get_file_history(self, repo_path: str, file_path: str, stop_commit: Optional[str] = None) -> List[str]:
        """获取文件的提交历史"""
        try:
            cmd = ['git', 'log', '--format=%H']
            
            if stop_commit:
                # 如果有停止点，只获取到停止点的历史
                cmd.append(f"{stop_commit}..HEAD")
            
            cmd.append('--')
            cmd.append(file_path)
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            commits = result.stdout.strip().split('\n')
            # 过滤空行
            commits = [commit for commit in commits if commit]
            
            logger.info(f"文件 {file_path} 有 {len(commits)} 个历史提交")
            return commits
            
        except subprocess.CalledProcessError as e:
            logger.error(f"获取文件 {file_path} 历史失败: {e.stderr}")
            return []
    
    def _create_temp_branch(self, repo_path: str, branch_name: str, commit: str) -> bool:
        """创建临时分支"""
        try:
            # 检出特定提交
            result = subprocess.run(
                ['git', 'checkout', '-b', branch_name, commit],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"创建临时分支 {branch_name} 指向 {commit[:8]}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"创建临时分支失败: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"创建临时分支过程发生未知错误: {e}")
            return False

    def _apply_patch(self, repo_path: str, patch_path: Path) -> Dict[str, Any]:
        """应用补丁"""
        result = {
            'success': False,
            'error': None,
            'error_type': None,
            'output': None
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
            
            # 尝试应用补丁
            apply_process = subprocess.run(
                ['git', 'am', str(absolute_patch_path)],
                cwd=repo_path,
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
            try:
                abort_process = subprocess.run(
                    ['git', 'am', '--abort'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False  # 忽略错误
                )
                if result['success']:
                    logger.debug("补丁应用成功，不需要中止")
                else:
                    logger.info("清理 git am 状态")
            except Exception as cleanup_error:
                logger.warning(f"清理 git am 状态时发生错误: {cleanup_error}")

    def _cleanup_temp_branch(self, repo_path: str, temp_branch: str, original_branch: str) -> None:
        """清理临时分支"""
        try:
            # 尝试中止任何可能正在进行的 git am 操作
            try:
                subprocess.run(
                    ['git', 'am', '--abort'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
            except Exception as e:
                logger.debug(f"中止 git am 过程发生错误: {e}")
            
            # 获取当前分支
            current_branch = self._get_current_branch(repo_path)
            
            # 切回原始分支 (如果当前不在原始分支上)
            if current_branch != original_branch:
                subprocess.run(
                    ['git', 'checkout', original_branch],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"切回原始分支: {original_branch}")
            
            # 检查临时分支是否存在
            branches_result = subprocess.run(
                ['git', 'branch'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            if temp_branch in branches_result.stdout:
                # 删除临时分支
                subprocess.run(
                    ['git', 'branch', '-D', temp_branch],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                logger.info(f"删除临时分支: {temp_branch}")
            else:
                logger.debug(f"临时分支 {temp_branch} 不存在，无需删除")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"清理临时分支失败: {e.stderr}")
        except Exception as e:
            logger.error(f"清理临时分支过程发生未知错误: {e}")

    def _try_adaptive_apply(self, context: ModuleContext, patch_path: Path, modified_files: List[str]) -> Dict[str, Any]:
        """
        尝试通过修改补丁中的文件路径来适配目标仓库
        
        :param context: 模块上下文
        :param patch_path: 原始补丁路径
        :param modified_files: 补丁中修改的文件列表
        :return: 应用结果字典
        """
        repo_path = context.config.repo_path
        result = {
            'success': False,
            'message': '',
            'error': None,
            'error_type': None
        }
        
        # 获取当前分支
        try:
            current_branch = self._get_current_branch(repo_path)
            logger.info(f"当前分支: {current_branch}")
        except Exception as e:
            logger.error(f"获取当前分支失败: {e}")
            result['error'] = f"获取当前分支失败: {e}"
            result['error_type'] = 'branch_error'
            return result
        
        # 准备临时分支名
        temp_branch = f"adaptive_{context.commit.commit_sha[:6]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        branch_created = False
        
        try:
            # 映射文件路径到目标仓库
            path_mapping = self._map_file_paths(repo_path, modified_files)
            if not path_mapping:
                logger.warning("无法映射任何文件路径")
                result['error'] = "无法映射文件路径"
                result['error_type'] = 'path_mapping_failed'
                return result
                
            logger.info(f"文件路径映射: {path_mapping}")
            
            # 检查是否所有文件都有映射
            unmapped_files = [f for f in modified_files if f not in path_mapping]
            if unmapped_files:
                logger.warning(f"以下文件未找到映射: {unmapped_files}")
                result['error'] = f"部分文件未找到映射: {unmapped_files}"
                result['error_type'] = 'incomplete_mapping'
                return result
            
            # 修改补丁文件
            adapted_patch_path = self._adapt_patch_paths(context, patch_path, path_mapping)
            if not adapted_patch_path:
                logger.warning("修改补丁文件失败")
                result['error'] = "修改补丁文件失败"
                result['error_type'] = 'patch_adaptation_failed'
                return result
            
            try:
                # 创建临时分支用于测试
                branch_created = self._create_temp_branch(repo_path, temp_branch, 'HEAD')
                if not branch_created:
                    logger.warning("创建临时分支失败")
                    result['error'] = "创建临时分支失败"
                    result['error_type'] = 'branch_creation_failed'
                    return result
                
                # 尝试应用修改后的补丁
                apply_result = self._apply_patch(repo_path, adapted_patch_path)
                
                if apply_result['success']:
                    # 获取应用的提交的哈希值
                    head_commit = self._get_head_commit(repo_path)
                    
                    result['success'] = True
                    result['message'] = "路径自适应应用成功"
                    result['applicable_version'] = head_commit
                    result['last_compatible_commit'] = head_commit
                    result['adapted_patch_path'] = str(adapted_patch_path)
                    
                    logger.info(f"路径自适应应用成功: {head_commit[:8]}")
                else:
                    logger.warning(f"路径自适应应用失败: {apply_result.get('error', '未知错误')}")
                    result['error'] = apply_result.get('error', '应用失败')
                    result['error_type'] = apply_result.get('error_type', 'apply_failed')
            
            finally:
                # 无论成功与否，都清理临时分支
                if branch_created:
                    self._cleanup_temp_branch(repo_path, temp_branch, current_branch)
                
            return result
            
        except Exception as e:
            logger.error(f"路径自适应应用过程发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            result['error'] = str(e)
            result['error_type'] = 'exception'
            return result
        
        finally:
            # 确保切回原始分支
            try:
                current_repo_branch = self._get_current_branch(repo_path)
                if current_repo_branch != current_branch:
                    logger.warning(f"检测到分支未切回原始分支，当前为 {current_repo_branch}，应为 {current_branch}")
                    subprocess.run(
                        ['git', 'checkout', current_branch],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        check=False
                    )
                    logger.info(f"已强制切回原始分支: {current_branch}")
                
                # 检查临时分支是否存在并清理
                branches_result = subprocess.run(
                    ['git', 'branch'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
                if branches_result.returncode == 0 and temp_branch in branches_result.stdout:
                    logger.warning(f"临时分支 {temp_branch} 仍然存在，尝试清理")
                    subprocess.run(
                        ['git', 'branch', '-D', temp_branch],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        check=False
                    )
            except Exception as cleanup_error:
                logger.error(f"最终清理过程发生错误: {cleanup_error}")

    def _get_head_commit(self, repo_path: str) -> str:
        """获取当前HEAD指向的提交哈希值"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"获取HEAD提交失败: {e.stderr}")
            raise ValueError(f"获取HEAD提交失败: {e.stderr}")
    
    def _adapt_patch_paths(self, context: ModuleContext, patch_path: Path, path_mapping: Dict[str, str]) -> Optional[Path]:
        """
        根据路径映射修改补丁文件中的路径
        
        :param context: 模块上下文
        :param patch_path: 原始补丁路径
        :param path_mapping: 文件路径映射字典
        :return: 修改后的补丁路径
        """
        try:
            # 读取原始补丁内容
            with open(patch_path, 'r', encoding='utf-8', errors='ignore') as f:
                patch_content = f.read()
            
            # 创建修改后的补丁文件路径
            adapted_patch_path = context.patch_dir / f"adapted_{context.commit.commit_sha[:6]}.patch"
            
            # 为每个映射路径创建正则表达式并替换
            modified_content = patch_content
            
            # 替换 diff --git a/file.txt b/file.txt 格式的路径
            for old_path, new_path in path_mapping.items():
                if old_path != new_path:  # 只替换路径发生变化的文件
                    # 替换diff行
                    diff_pattern = re.compile(r'(diff --git a/)' + re.escape(old_path) + r'( b/)' + re.escape(old_path))
                    modified_content = diff_pattern.sub(r'\1' + new_path + r'\2' + new_path, modified_content)
                    
                    # 替换--- a/path和+++ b/path行
                    minus_pattern = re.compile(r'(--- a/)' + re.escape(old_path))
                    modified_content = minus_pattern.sub(r'\1' + new_path, modified_content)
                    
                    plus_pattern = re.compile(r'(\+\+\+ b/)' + re.escape(old_path))
                    modified_content = plus_pattern.sub(r'\1' + new_path, modified_content)
                    
                    # 文件创建/删除模式的特殊处理
                    # 处理 /dev/null -> new_file 情况
                    null_to_new_pattern = re.compile(r'(--- /dev/null\n\+\+\+ b/)' + re.escape(old_path))
                    modified_content = null_to_new_pattern.sub(r'\1' + new_path, modified_content)
                    
                    # 处理 old_file -> /dev/null 情况
                    old_to_null_pattern = re.compile(r'(--- a/)' + re.escape(old_path) + r'(\n\+\+\+ /dev/null)')
                    modified_content = old_to_null_pattern.sub(r'\1' + new_path + r'\2', modified_content)
            
            # 写入修改后的内容到新文件
            with open(adapted_patch_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            logger.info(f"路径适配补丁已创建: {adapted_patch_path}")
            return adapted_patch_path
        
        except Exception as e:
            logger.error(f"修改补丁文件路径时发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return None 