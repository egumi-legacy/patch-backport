from typing import Dict, Any, Optional
from pathlib import Path
import yaml
from datetime import datetime
from loguru import logger
from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext
from patch_evaluator import PatchEvaluator
# from config_manager import ProjectConfig
import subprocess
import shutil

class DirectApplyModule(BaseModule):
    """直接应用补丁模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.DIRECT_APPLY
        self.name = "direct_apply"
        
        # 确保配置中包含必要的路径
        if not config.repo_path:
            raise ValueError("repo_path is required")

        # self.evaluator = PatchEvaluator(config)
        # self.config = config
        
        # # 初始化跳过文件路径
        # self.skip_file = Path("skip_git_am_patchfile") / "commits.yaml"
        # self.skip_file.parent.mkdir(parents=True, exist_ok=True)
        
        # # 加载已知可直接应用的提交
        # self.direct_applicable = self._load_direct_applicable()
        
        # self.last_apply_success = False
        # self.error_count = 0
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行直接应用补丁"""
        if not self._should_run(context):
            return context
            
        start_time = datetime.now()
        commit_sha = context.commit.commit_sha
        patch_url = context.commit.patch_url
        
        try:
            # 检查缓存
            if context.config.use_cached_patches:
                cache_result = self._check_cache(context)
                if cache_result:
                    logger.info(f"从缓存中获取到直接应用结果: {cache_result}")
                    context.direct_apply_result = cache_result
                    context.commit.patch_path = Path(cache_result.get('patch_path'))
                    return context
            
            # 下载补丁文件
            patch_path = self._download_patch(context)
            if not patch_path.exists():
                raise ValueError("下载补丁失败")
            else:
                context.commit.patch_path = patch_path
                logger.info(f"此时upstream_patch_path存在状态: {True if context.commit.patch_path.exists() else False}")
                logger.info(f"下载补丁成功: {patch_path}")
            
            # 准备测试分支
            branch_name = self._prepare_test_branch(context)
            if not branch_name:
                raise ValueError("准备测试分支失败")
            
            try:
                # 尝试直接应用补丁
                apply_result = self._apply_patch(context, patch_path, branch_name)
                
                # 更新结果
                context.direct_apply_result = {
                    'success': apply_result['success'],
                    'message': '补丁直接应用成功' if apply_result['success'] else '补丁应用失败',
                    'error': apply_result.get('error'),
                    'patch_path': str(patch_path),
                    'timestamp': datetime.now().isoformat()
                }

                # 如果应用成功，移动到缓存目录
                if apply_result['success']:
                    self._move_to_cache(context)
                
                # 更新指标
                self._update_metrics(
                    success=apply_result['success'],
                    error_type=apply_result.get('error_type'),
                    execution_time=(datetime.now() - start_time).total_seconds()
                )
                
                # 保存到缓存
                if context.config.use_cached_patches:
                    self._save_to_cache(context)
                
            finally:
                # 清理测试分支
                self._cleanup_test_branch(context, branch_name)
            
        except Exception as e:
            logger.error(f"直接应用过程发生错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            context.direct_apply_result = {
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
        if context.direct_apply_result.get('success', False):
            self._save_metrics(context)
        
        return context

    def _move_to_cache(self, context: ModuleContext):
        """将成功的commit文件夹移动到缓存目录"""
        try:
            # 源目录：当前commit的工作目录
            source_dir = context.commit.base_dir
            logger.info(f"源目录: {source_dir}")
            if not source_dir.exists():
                logger.warning(f"源目录不存在: {source_dir}")
                return

            # 目标目录：缓存目录下的commit目录
            commit_sha = context.commit.commit_sha[:6]
            target_dir = context.cache_dir
            logger.info(f"目标目录: {target_dir}")

            # 确保目标目录存在
            target_dir.mkdir(parents=True, exist_ok=True)

            # 如果目标目录已存在，先删除
            if Path(target_dir / source_dir.name).exists():
                shutil.rmtree(target_dir / source_dir.name)

            # 移动目录
            shutil.move(str(source_dir), str(target_dir))
            logger.info(f"已将成功的commit文件夹移动到缓存: {target_dir}")

        except Exception as e:
            logger.error(f"移动到缓存目录失败: {e}")
    
    def _check_cache(self, context: ModuleContext) -> Optional[Dict[str, Any]]:
        """检查缓存"""
        cache_file = context.cache_dir / f"direct_apply_cache.yaml"
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache = yaml.safe_load(f) or {}
            
            # 构建缓存键
            cache_key = f"{context.commit.commit_sha}_{context.config.target_version}"
            
            if cache_key in cache:
                return cache[cache_key]
        except Exception as e:
            logger.error(f"读取缓存失败: {e}")
        
        return None
    
    def _save_to_cache(self, context: ModuleContext):
        """保存到缓存"""
        if not context.direct_apply_result:
            return
            
        cache_file = context.cache_dir / f"direct_apply_cache.yaml"
        
        try:
            # 读取现有缓存
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    cache = yaml.safe_load(f) or {}
            else:
                cache = {}
            
            # 构建缓存键
            cache_key = f"{context.commit.commit_sha}_{context.config.target_version}"
            
            # 更新缓存
            cache[cache_key] = context.direct_apply_result
            
            # 写入缓存
            with open(cache_file, 'w') as f:
                yaml.dump(cache, f)
                
            logger.info(f"已将直接应用结果保存到缓存: {cache_key}")
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
    
    def _download_patch(self, context: ModuleContext) -> Path:
        """下载补丁文件"""
        
        patch_dir = context.patch_dir
        # patch_dir.mkdir(parents=True, exist_ok=True)
        
        patch_path = patch_dir / f"upstream_{context.commit.commit_sha[:6]}.patch"
        
        # 检查是否有downstream_sha（模式1可能没有）
        if hasattr(context.commit, 'downstream_sha') and context.commit.downstream_sha:
            downstream_patch_path = patch_dir / f"downstream_{context.commit.downstream_sha[:6]}.patch"
            from patch_utils import download_patch
            
            if downstream_patch_path.exists():
                logger.info(f"下游补丁文件已存在: {downstream_patch_path}")
            else:
                logger.info(f"下游补丁文件不存在，下载补丁: {downstream_patch_path}")
                # logger.info(f": {downstream_patch_path}")
                download_patch_url = f"https://github.com/{context.commit.repo_owner}/{context.commit.repo_name}/commit/{context.commit.downstream_sha}.patch"
                success = download_patch(download_patch_url, downstream_patch_path).exists()
                if success:
                    logger.info(f"下游补丁下载成功: {downstream_patch_path}")
                else:
                    # logger.error(f"下游补丁下载失败: {downstream_patch_path}")
                    raise ValueError(f"下游补丁下载失败: {downstream_patch_path}")

        if patch_path.exists():
            logger.info(f"上游补丁文件已存在: {patch_path}")
            # 确保返回绝对路径
            return Path(patch_path.absolute())
        else:
            from patch_utils import download_patch
            logger.info(f"上游补丁文件不存在，下载补丁")
            success = download_patch(context.commit.patch_url, patch_path).exists()
            
            if success:
                logger.info(f"上游补丁下载成功: {patch_path}")
                # self.context.commit.patch_path = patch_path
                # 确保返回绝对路径
                return Path(patch_path.absolute())
            else:
                logger.error(f"补丁下载失败: {context.commit.patch_url}")
                return None
        

    def _apply_patch(self, context: ModuleContext, patch_path: Path, branch_name: str):
        """
        尝试直接应用上游补丁
        """
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
        
        
        
    
    def _prepare_test_branch(self, context: ModuleContext) -> str:
        """
        准备一个干净的分支用于测试
        
        :return: 创建的分支名称，如果失败则返回None
        """
        branch_name = f"test_patch_{context.config.target_version}"
        repo_path = context.config.repo_path

        try:
            # 确保在目标版本的基础上创建新分支
            subprocess.run(
                ['git', 'checkout', context.config.target_version],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            # 如果分支已存在，先删除它
            try:
                subprocess.run(
                    ['git', 'branch', '-D', branch_name],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )
                logger.info(f"删除已存在的测试分支: {branch_name}")
            except subprocess.CalledProcessError:
                # 如果分支不存在，忽略错误
                pass
            
            # 创建新的测试分支
            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"创建测试分支: {branch_name}")
            
            # 确保工作区干净
            subprocess.run(
                ['git', 'reset', '--hard', 'HEAD'],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ['git', 'clean', '-fd'],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            return branch_name
        except subprocess.CalledProcessError as e:
            logger.error(f"准备测试分支失败: {e.stderr}")
            # 发生错误时，尝试清理
            self._cleanup_test_branch(branch_name)
            return None
        except Exception as e:
            logger.error(f"准备测试分支时发生错误: {str(e)}")
            # 发生错误时，尝试清理
            self._cleanup_test_branch(branch_name)
            return None
        

    def apply_upstream_patch(self, patch_path):
        """尝试应用上游patch"""
        try:
            # 将patch_path转换为绝对路径
            absolute_patch_path = Path(patch_path).resolve()
            if not absolute_patch_path.exists():
                logger.error(f"Patch文件不存在: {absolute_patch_path}")
                return {'success': False, 'error': f"Patch文件不存在: {absolute_patch_path}"}
            
            result = subprocess.run(
                ['git', 'am', str(absolute_patch_path)],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            success = result.returncode == 0
            logger.info(f"应用上游patch {'成功' if success else '失败'}")
            return {
                'success': success,
                'output': result.stdout,
                'error': result.stderr
            }
        except Exception as e:
            logger.error(f"应用patch时发生错误: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            # 无论成功与否，都清理git am状态
            subprocess.run(['git', 'am', '--abort'], cwd=self.repo_path, 
                         capture_output=True)
            
            
    def _cleanup_test_branch(self, context: ModuleContext, branch_name: str):
        """
        清理测试分支
        
        :param branch_name: 要清理的分支名称
        """
        if not branch_name:
            return
        
        repo_path = context.config.repo_path

        try:
            # 首先切换回目标版本分支
            
            subprocess.run(
                ['git', 'checkout', context.config.branch],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            # 删除测试分支
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"清理测试分支: {branch_name}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"清理分支时发生错误: {e.stderr}")
        except Exception as e:
            logger.warning(f"清理分支时发生错误: {str(e)}")
    

    # def _apply_patch(self, context: ModuleContext, patch_path: Path, branch_name: str) -> Dict[str, Any]:
    #     """应用补丁"""
    #     result = {
    #         'success': False,
    #         'error': None,
    #         'error_type': None,
    #         'output': None
    #     }
        
    #     try:
    #         # 尝试应用补丁
    #         apply_process = subprocess.run(
    #             ['git', 'am', str(patch_path)],
    #             cwd=context.commit.repo_path,
    #             capture_output=True,
    #             text=True
    #         )
            
    #         if apply_process.returncode == 0:
    #             result['success'] = True
    #             result['output'] = apply_process.stdout
    #             logger.info(f"补丁应用成功: {patch_path}")
    #         else:
    #             # 中止失败的应用
    #             subprocess.run(
    #                 ['git', 'am', '--abort'],
    #                 cwd=context.commit.repo_path,
    #                 capture_output=True,
    #                 text=True
    #             )
                
    #             result['error'] = apply_process.stderr
    #             result['error_type'] = self._categorize_error(apply_process.stderr)
    #             logger.error(f"补丁应用失败: {result['error']}")
            
    #     except Exception as e:
    #         result['error'] = str(e)
    #         result['error_type'] = 'exception'
    #         logger.error(f"应用补丁时发生错误: {e}")
            
    #         # 尝试中止失败的应用
    #         try:
    #             subprocess.run(
    #                 ['git', 'am', '--abort'],
    #                 cwd=context.commit.repo_path,
    #                 capture_output=True,
    #                 text=True
    #             )
    #         except:
    #             pass
        
    #     return result
    
    def _categorize_error(self, error_message: str) -> str:
        """分类错误类型"""
        if "patch does not apply" in error_message:
            return "patch_not_apply"
        elif "conflicts" in error_message:
            return "conflicts"
        elif "file not found" in error_message or "No such file" in error_message:
            return "file_not_found"
        elif "already exists" in error_message:
            return "file_already_exists"
        else:
            return "other"
    
    # def _load_direct_applicable(self) -> Dict:
    #     """加载已知可直接应用的提交记录"""
    #     if self.skip_file.exists():
    #         with open(self.skip_file, 'r') as f:
    #             return yaml.safe_load(f) or {}
    #     return {}
    
    # def _save_direct_applicable(self, commit_sha: str, patch_info: Dict):
    #     """保存可直接应用的提交记录"""
    #     self.direct_applicable[commit_sha] = {
    #         'timestamp': datetime.now().isoformat(),
    #         'patch_url': patch_info['patch_url'],
    #         'target_version': patch_info['target_version']
    #     }
        
    #     # 保存到文件
    #     with open(self.skip_file, 'w') as f:
    #         yaml.safe_dump(self.direct_applicable, f)
        
    #     # 将patch文件复制到skip目录
    #     if 'patch_path' in patch_info:
    #         skip_patch_dir = self.skip_file.parent / f"{commit_sha[:6]}"
    #         skip_patch_dir.mkdir(parents=True, exist_ok=True)
    #         import shutil
    #         shutil.copy2(patch_info['patch_path'], skip_patch_dir / "patch.diff")
    
    # def execute(self, context: ModuleContext) -> ModuleContext:
    #     """执行直接应用补丁"""
    #     patch_info = context.patch_info
    #     commit_sha = patch_info.get("commit_sha")
        
    #     # 如果在跳过列表中，直接返回成功
    #     if commit_sha and commit_sha in self.direct_applicable:
    #         logger.info(f"提交 {commit_sha} 在跳过列表中，直接返回成功")
    #         context["direct_apply_result"] = {
    #             "success": True,
    #             "message": "在跳过列表中"
    #         }
    #         return context
        
    #     # 下载补丁文件
    #     if "patch_url" in patch_info and not patch_info.get("patch_path"):
    #         patch_path = self.evaluator.download_patch_by_type(
    #             patch_info["patch_url"], 
    #             'upstream'
    #         )
    #         patch_info["patch_path"] = patch_path
    #         context.patch_info = dict(patch_info)
        
    #     # logger.info(f"尝试直接应用补丁: {patch_info.get('patch_path')}")
    #     if not patch_path:
    #         logger.error("patch_path is required")
    #         context.direct_apply_result = {
    #             'success': False,
    #             'error': 'patch_path is required'
    #         }
    #         return context
        
    #     try:
    #         # 尝试直接应用补丁
    #         apply_result = self.evaluator.try_direct_apply(
    #             patch_file=patch_path,
    #             commit_info={"upstream_sha": commit_sha} if commit_sha else None
    #         )
            
    #         if apply_result and apply_result.get('success', False):
    #             # 如果成功，保存到跳过记录
    #             if commit_sha:
    #                 self._save_direct_applicable(commit_sha, context.patch_info)
    #             logger.info("直接应用成功")
    #             self.last_apply_success = True
    #         else:
    #             self.error_count += 1
    #             error_msg = apply_result.get('error') if apply_result else 'Unknown error'
    #             logger.warning(f"直接应用失败: {error_msg}")
    #             self.last_apply_success = False
            
    #         context.direct_apply_result = apply_result or {
    #             'success': False,
    #             'error': 'No result from evaluator'
    #         }
            
    #     except Exception as e:
    #         self.error_count += 1
    #         logger.error(f"直接应用过程发生错误: {e}")
    #         context.direct_apply_result = {
    #             'success': False,
    #             'error': str(e)
    #         }
        
    #     return context
    
    # def get_metrics(self) -> Dict[str, Any]:
    #     return {
    #         "apply_success": self.last_apply_success,
    #         "error_count": self.error_count
    #     } 