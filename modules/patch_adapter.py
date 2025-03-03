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
            if not llm_response_path or not Path(llm_response_path).exists():
                raise ValueError(f"LLM响应文件不存在: {llm_response_path}")
                
            # 保存原始补丁
            raw_patch_path = self._save_raw_patch(context, Path(llm_response_path).read_text())
            
            # 创建适配目录
            adapted_dir = self._create_adapted_dir(context)
            
            # 创建测试分支
            branch_name = self._prepare_test_branch(context)
            
            try:
                # 应用补丁
                source_dir = context.commit.base_dir / context.config.target_version
                output_dir = context.commit.base_dir / f"adapted_{context.config.target_version}"
                
                # 调用PatchAdapterUtils的generate_adapted_file方法
                self.adapter_utils.generate_adapted_file(llm_response_path, source_dir, output_dir)
                
                # 测试补丁应用
                apply_result = self._test_patch_apply(context, branch_name)
                
                # 生成适配后的补丁文件
                if apply_result.get('success', False):
                    patch_path = self._generate_adapted_patch(context)
                    if patch_path:
                        apply_result['adapted_patch_path'] = str(patch_path)
                
                # 更新上下文和指标
                context.patch_adapter_result = {
                    'success': True,
                    'adapted_patch_path': str(raw_patch_path),
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
            if self.verbose:
                logger.error(f"错误堆栈: {traceback.format_exc()}")
            
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
    
    def _save_raw_patch(self, context: ModuleContext, patch_content: str) -> Path:
        """保存原始补丁"""
        # 创建适配补丁目录
        patch_dir = context.commit.base_dir / "adapted_patches"
        patch_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        patch_path = patch_dir / f"raw_patch_{timestamp}.patch"
        
        with open(patch_path, 'w') as f:
            f.write(patch_content)
        
        logger.info(f"原始补丁已保存到: {patch_path}")
        return patch_path
    
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
            cwd=context.commit.base_dir,
            capture_output=True,
            check=True
        )
        
        # 创建测试分支
        subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            cwd=context.commit.base_dir,
            capture_output=True,
            check=True
        )
        
        # 清理工作区
        subprocess.run(
            ['git', 'reset', '--hard', 'HEAD'],
            cwd=context.commit.base_dir,
            capture_output=True,
            check=True
        )
        
        subprocess.run(
            ['git', 'clean', '-fd'],
            cwd=context.commit.base_dir,
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
                cwd=context.commit.base_dir,
                capture_output=True,
                check=False
            )
            
            # 删除测试分支
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=context.commit.base_dir,
                capture_output=True,
                check=False
            )
        except Exception as e:
            logger.warning(f"清理测试分支时出错: {str(e)}")
    
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
            # 明确使用repo_path而不是当前目录
            repo_path = context.config.repo_path
            
            # 准备测试分支
            branches = subprocess.run(
                ['git', 'branch'],
                cwd=repo_path,  # 明确使用repo_path
                check=True,
                capture_output=True,
                text=True
            ).stdout
            
            # 如果分支已存在，先删除
            if branch_name in branches:
                subprocess.run(
                    ['git', 'branch', '-D', branch_name],
                    cwd=repo_path,  # 明确使用repo_path
                    check=False,
                    capture_output=True,
                    text=True
                )
            
            # 创建新分支
            checkout_result = subprocess.run(
                ['git', 'checkout', '-b', branch_name, context.config.target_version],
                cwd=repo_path,  # 明确使用repo_path
                capture_output=True,
                text=True
            )
    
    def _generate_adapted_patch(self, context: ModuleContext) -> Optional[Path]:
        """生成适配后的patch文件"""
        patch_dir = context.commit.base_dir / "patches"
        patch_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        patch_path = patch_dir / f"adapted_{context.config.target_version}_{timestamp}.patch"
        
        try:
            # 使用git format-patch生成补丁
            result = subprocess.run(
                ['git', 'format-patch', '-1', 'HEAD', '-o', str(patch_dir)],
                cwd=context.commit.base_dir,
                capture_output=True,
                check=True,
                encoding='utf-8'
            )
            
            # 找到生成的补丁文件
            generated_patches = list(patch_dir.glob('*.patch'))
            if not generated_patches:
                logger.error("未能生成补丁文件")
                return None
                
            # 重命名最新生成的补丁文件
            latest_patch = max(generated_patches, key=lambda p: p.stat().st_mtime)
            shutil.move(latest_patch, patch_path)
            
            logger.info(f"已生成适配后的补丁文件: {patch_path}")
            return patch_path
            
        except subprocess.CalledProcessError as e:
            logger.error(f"生成补丁文件失败: {e.stderr}")
            return None
        except Exception as e:
            logger.error(f"生成补丁文件时发生错误: {str(e)}")
            return None
    
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