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
import shutil
from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext
# 导入PatchAdapterUtils
from patch_adapter_utils import PatchAdapterUtils

class PatchAdapterModule(BaseModule):
    """补丁适配模块"""
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.PATCH_ADAPTER
        self.name = "patch_adapter"
        # self.verbose = config.get('verbose', False)
        self.metrics = {
            'total_attempts': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'execution_time': 0,
            'error_types': {},
            'apply_success': False,
            'apply_errors': []
        }
        # 创建PatchAdapterUtils实例
        self.adapter_utils = PatchAdapterUtils()
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行补丁适配"""
        if not self._should_run(context):
            return context
            
        start_time = datetime.now()
        self.metrics['total_attempts'] += 1
        
        try:
            # 获取LLM生成的补丁路径
            llm_response_path = self._get_llm_response_path(context)
            logger.info(f"LLM响应文件路径: {llm_response_path}")
            if not llm_response_path or not Path(llm_response_path).exists():
                raise ValueError(f"LLM响应文件不存在: {llm_response_path}")
                
            # # 保存原始补丁
            # raw_patch_path = self._save_raw_patch(context, Path(llm_response_path).read_text())
            
            # 创建适配目录
            adapted_dir = self._create_adapted_dir(context)
            
            # 创建测试分支
            branch_name = self._prepare_test_branch(context)
            
            try:
                # 应用补丁
                source_dir = context.commit.base_dir / context.config.target_version
                output_dir = adapted_dir
                
                # 调用PatchAdapterUtils的generate_adapted_file方法
                self.adapter_utils.generate_adapted_file(llm_response_path, source_dir, output_dir)
                
                # 创建适配后的补丁文件
                adapted_patch_path = self._generate_adapted_patch(context, branch_name)
                if not adapted_patch_path:
                    raise ValueError("生成适配补丁失败")
                else:
                    logger.info(f"生成适配补丁成功: {adapted_patch_path}")
                    # context.adapted_patches.append(adapted_patch_path)
                # 测试补丁应用
                apply_result = self._test_apply_patch(context, adapted_patch_path)
                # 更新上下文和指标
                context.patch_adapter_result = {
                    'success': apply_result.get('success', False),
                    'adapted_patch_path': str(adapted_patch_path),
                    'apply_result': apply_result
                }
                
                self._update_metrics(True, apply_success=apply_result.get('success', False),
                       apply_error=apply_result.get('error'), 
                       execution_time=(datetime.now() - start_time).total_seconds())
                
            finally:
                # 清理测试分支
                self._cleanup_test_branch(context, branch_name)
            
            self._save_metrics(context)
            return context
            
        except Exception as e:
            logger.error(f"补丁适配过程发生错误: {str(e)}")
            # if self.verbose:
            import traceback
            logger.error(traceback.format_exc())
            
            # 更新上下文和指标
            error_type = type(e).__name__
            self._update_metrics(False, error_type=error_type, 
                               execution_time=(datetime.now() - start_time).total_seconds())
            
            context.patch_adapter_result = {
                'success': False,
                'error': str(e)
            }
            
            self._save_metrics(context)
            return context
    
    def _get_llm_response_path(self, context: ModuleContext) -> str:
        """获取LLM响应文件路径"""
        # 从context中获取LLM响应路径
        if hasattr(context, 'llm_output') and context.llm_output:
            llm_response_path = context.llm_output.get('response_path')
            if llm_response_path:
                return llm_response_path
                
        # 尝试从配置中获取
        llm_dir = context.commit.base_dir / "llm_output"
        if llm_dir.exists():
            patch_files = list(llm_dir.glob(f"*_{context.config.target_version}_*.patch"))
            if patch_files:
                return str(patch_files[0])
                
        raise ValueError("找不到LLM响应文件")
    
    # def _save_raw_patch(self, context: ModuleContext, patch_content: str) -> Path:
    #     """保存原始补丁"""
    #     # 创建适配补丁目录
    #     patch_dir = context.commit.base_dir / "adapted_patches"
    #     patch_dir.mkdir(parents=True, exist_ok=True)
        
    #     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    #     patch_path = patch_dir / f"raw_patch_{timestamp}.patch"
        
    #     with open(patch_path, 'w') as f:
    #         f.write(patch_content)
        
    #     logger.info(f"原始补丁已保存到: {patch_path}")
    #     return patch_path
    
    def _create_adapted_dir(self, context: ModuleContext) -> Path:
        """创建适配目录"""
        adapted_dir = context.commit.base_dir / f"adapted_{context.config.target_version}"
        
        # 清理已存在的目录
        if adapted_dir.exists():
            shutil.rmtree(adapted_dir)
        
        adapted_dir.mkdir(parents=True)
        return adapted_dir
    
    def _prepare_test_branch(self, context: ModuleContext) -> str:
        """准备测试分支"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        branch_name = f"test_adapt_{context.config.target_version}_{timestamp}"
        
        logger.info(f"创建测试分支: {branch_name}")
        
        # 确保我们从目标版本创建分支
        subprocess.run(
            ['git', 'checkout', context.config.target_version],
            cwd=context.config.repo_path,
            capture_output=True,
            check=True
        )
        
        # 创建测试分支
        subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            cwd=context.config.repo_path,
            capture_output=True,
            check=True
        )
        
        # 清理工作区
        subprocess.run(
            ['git', 'reset', '--hard', 'HEAD'],
            cwd=context.config.repo_path,
            capture_output=True,
            check=True
        )
        
        subprocess.run(
            ['git', 'clean', '-fd'],
            cwd=context.config.repo_path,
            capture_output=True,
            check=True
        )
        
        return branch_name
    
    def _cleanup_test_branch(self, context: ModuleContext, branch_name: str) -> None:
        """清理测试分支"""
        logger.info(f"清理测试分支: {branch_name}")
        
        try:
            # 切换回目标版本分支
            subprocess.run(
                ['git', 'checkout', context.config.target_version],
                cwd=context.config.repo_path,
                capture_output=True,
                check=False
            )
            
            # 删除测试分支
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=context.config.repo_path,
                capture_output=True,
                check=False
            )
        except Exception as e:
            logger.warning(f"清理测试分支时出错: {str(e)}")
    
    
    def _generate_adapted_patch(self, context: ModuleContext, branch_name: str) -> Optional[Path]:
        """从适配后的文件创建提交并生成补丁"""
        result = {
            'success': False,
            'error': None,
            'modified_files': []
        }
        
        try:
            # 获取路径
            repo_path = context.config.repo_path
            adapted_dir = context.commit.base_dir / f"adapted_{context.config.target_version}"
            
            # # 准备测试分支
            # branch_result = subprocess.run(
            #     ['git', 'checkout', '-b', branch_name, context.config.target_version],
            #     cwd=repo_path,
            #     capture_output=True,
            #     text=True
            # )
            
            # if branch_result.returncode != 0:
            #     logger.error(f"创建分支失败: {branch_result.stderr}")
            #     return None
            
            # 复制适配后的文件到仓库
            files_changed = False
            modified_files = []
            
            for file_path in adapted_dir.rglob('*'):
                if file_path.is_file():
                    rel_path = file_path.relative_to(adapted_dir)
                    target_path = Path(repo_path) / rel_path
                    logger.info(f"target_path: {target_path.resolve()}")
                    # 检查目标文件是否存在
                    if target_path.exists():
                        # 比较文件内容是否有变化
                        with open(file_path, 'rb') as f1, open(target_path, 'rb') as f2:
                            source_content = f1.read()
                            target_content = f2.read()
                            
                            if source_content != target_content:
                                # 只有文件内容有变化时才复制
                                logger.info(f"文件内容变化，执行复制: {rel_path}")
                                target_path.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(file_path, target_path)
                                logger.info(f"将文件从{file_path.resolve()}复制到{target_path.resolve()}")
                                files_changed = True
                                modified_files.append(str(rel_path))
                            else:
                                logger.info(f"文件未修改: {rel_path}")
                    else:
                        # 新增文件
                        logger.info(f"新增文件: {rel_path}")
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, target_path)
                        files_changed = True
                        modified_files.append(str(rel_path))
            
            if not files_changed:
                logger.warning("没有发现需要更改的文件")
                return None
            
            # 提交更改
            add_result = subprocess.run(
                ['git', 'add', '.'],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            commit_result = subprocess.run(
                ['git', 'commit', '-m', f"Applied adapted patch for {context.config.target_version}"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if commit_result.returncode != 0:
                logger.error(f"创建提交失败: {commit_result.stderr}")
                return None
            
            # 生成补丁文件
            absolute_patch_dir = context.commit.patch_dir.resolve()
            # patch_dir.mkdir(exist_ok=True)
            
            # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # adapted_patch_path = absolute_patch_dir / f"adapted_{context.config.target_version}_{timestamp}.patch"
            adapted_patch_path = absolute_patch_dir / f"adapted_{context.config.target_version}.patch"
            # 使用git format-patch生成补丁
            format_result = subprocess.run(
                ['git', 'format-patch', '-1', '-o', str(absolute_patch_dir)],
                cwd=repo_path,
                capture_output=True,
                check=True,
                text=True
            )
            if format_result.returncode != 0:
                logger.error(f"生成补丁失败: {format_result.stderr}")
                return None
            else:
                logger.info(f"生成补丁成功: {format_result.stdout}")
                files = os.listdir(absolute_patch_dir)
                logger.info(f"patch_dir所含文件: {files}")
            # 找到生成的补丁文件
            # 找到git format-patch生成的补丁文件 (通常以00-开头)
            generated_patches = list(absolute_patch_dir.glob('00*.patch'))
            if not generated_patches:
                logger.error("未能找到git format-patch生成的补丁文件")
                return None

            # 确保只重命名新生成的补丁文件
            format_patch = generated_patches[0]
            format_patch.rename(adapted_patch_path)
            logger.info(f"已重命名补丁文件: 从 {format_patch} 到 {adapted_patch_path}")
            # if not generated_patches:
            #     logger.error("未能生成补丁文件")
            #     return None
                
            # 重命名最新生成的补丁文件
            # latest_patch = max(generated_patches, key=lambda p: p.stat().st_mtime)
            # logger.info(f"latest_patch: {latest_patch.resolve()}")
            # shutil.copy2(generated_patches, adapted_patch_path)
            
            logger.info(f"已生成适配后的补丁文件: {adapted_patch_path}")
            return adapted_patch_path
            
        except Exception as e:
            logger.error(f"生成适配补丁时发生错误: {str(e)}")
            # if self.verbose:
            import traceback
            logger.error(traceback.format_exc())
            return None
        
        # finally:
        #     # 删除测试分支并切换回目标版本分支
        #     subprocess.run(
        #         ['git', 'branch', '-D', branch_name],
        #         cwd=repo_path,
        #         capture_output=True,
        #         check=False
        #     )
        #     subprocess.run(
        #         ['git', 'checkout', context.config.target_version],
        #         cwd=repo_path,
        #         capture_output=True,
        #         check=False
        #     )
    
    def _compare_patches(self, context: ModuleContext, adapted_patch: Path, reference_patch: Optional[Path] = None) -> Dict[str, Any]:
        """比较适配补丁和参考补丁（如果有）"""
        result = {'similarity': 0.0, 'diff': []}
        
        if not adapted_patch.exists():
            logger.warning(f"适配补丁文件不存在: {adapted_patch}")
            return result
            
        if reference_patch and reference_patch.exists():
            # 读取两个补丁文件
            with open(adapted_patch) as f1, open(reference_patch) as f2:
                adapted_content = f1.read()
                reference_content = f2.read()
            
            # 计算差异
            diff = list(difflib.unified_diff(
                adapted_content.splitlines(),
                reference_content.splitlines(),
                fromfile='adapted_patch',
                tofile='reference_patch'
            ))
            
            # 计算相似度
            similarity = difflib.SequenceMatcher(
                None, adapted_content, reference_content
            ).ratio()
            
            result['similarity'] = similarity
            result['diff'] = diff
            
            logger.info(f"补丁相似度: {similarity:.2f}")
        
        return result
    
    def _update_metrics(self, success: bool, error_type: str = None, apply_success: bool = False, 
                       apply_error: str = None, execution_time: float = 0) -> None:
        """更新指标"""
        self.metrics['execution_time'] = execution_time
        
        if success:
            self.metrics['successful_executions'] += 1
            self.metrics['apply_success'] = apply_success
            if apply_error:
                self.metrics['apply_errors'].append(apply_error)
        else:
            self.metrics['failed_executions'] += 1
            if error_type:
                self.metrics['error_types'][error_type] = self.metrics['error_types'].get(error_type, 0) + 1
    
    def _save_metrics(self, context: ModuleContext):
        """保存指标"""
        metrics_dir = context.commit.base_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        
        metrics_file = metrics_dir / "patch_adapter_metrics.json"
        with open(metrics_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"补丁适配指标已保存到: {metrics_file}")

    def _test_apply_patch(self, context: ModuleContext, patch_path: Path) -> Dict[str, Any]:
        """测试补丁是否可应用 (使用git am)"""
        result = {
            'success': False,
            'error': None,
            'error_type': None,
            'output': None,
        }

        try:
            # 创建测试分支
            branch_name = f"test_am_{context.config.target_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            repo_path = context.config.repo_path
            
            # 切换到目标版本并创建测试分支
            checkout_result = subprocess.run(
                ['git', 'checkout', '-b', branch_name, context.config.target_version],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if checkout_result.returncode != 0:
                result['error'] = f"创建测试分支失败: {checkout_result.stderr}"
                result['error_type'] = 'branch_creation_failed'
                return result
            
            # 确保使用绝对路径
            absolute_patch_path = patch_path.absolute()
            
            # 验证文件存在
            if not absolute_patch_path.exists():
                logger.error(f"补丁文件不存在: {absolute_patch_path}")
                result['error'] = f"补丁文件不存在: {absolute_patch_path}"
                result['error_type'] = 'file_not_found'
                return result
            
            # 应用补丁
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
            subprocess.run(['git', 'am', '--abort'], 
                          cwd=repo_path, 
                          capture_output=True,
                          text=True)
            
            # 切换回目标版本分支
            subprocess.run(
                ['git', 'checkout', context.config.target_version],
                cwd=repo_path,
                capture_output=True,
                check=False
            )
            
            # 删除测试分支
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=repo_path,
                capture_output=True,
                check=False
            )

    def _categorize_error(self, error_message: str) -> str:
        """分类git错误类型"""
        if "patch does not apply" in error_message:
            return "patch_not_apply"
        elif "already exists" in error_message:
            return "file_exists"
        elif "hunks failed" in error_message:
            return "hunk_failed"
        elif "not found" in error_message:
            return "file_not_found"
        else:
            return "unknown"