from typing import Dict, Any
from pathlib import Path
import yaml
from datetime import datetime
from loguru import logger
from .base_module import BaseModule, ModuleType, ModuleContext
from patch_evaluator import PatchEvaluator
from config_manager import ProjectConfig

class DirectApplyModule(BaseModule):
    """直接应用补丁模块"""
    def __init__(self, config: ProjectConfig):
        super().__init__(config)
        self.type = ModuleType.DIRECT_APPLY
        self.name = "direct_apply"
        
        # 确保配置中包含必要的路径
        if not config.repo_path:
            raise ValueError("repo_path is required")
            
        self.evaluator = PatchEvaluator(config)
        self.config = config
        
        # 初始化跳过文件路径
        self.skip_file = Path("skip_git_am_patchfile") / "commits.yaml"
        self.skip_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载已知可直接应用的提交
        self.direct_applicable = self._load_direct_applicable()
        
        self.last_apply_success = False
        self.error_count = 0
    
    def _load_direct_applicable(self) -> Dict:
        """加载已知可直接应用的提交记录"""
        if self.skip_file.exists():
            with open(self.skip_file, 'r') as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def _save_direct_applicable(self, commit_sha: str, patch_info: Dict):
        """保存可直接应用的提交记录"""
        self.direct_applicable[commit_sha] = {
            'timestamp': datetime.now().isoformat(),
            'patch_url': patch_info['patch_url'],
            'target_version': patch_info['target_version']
        }
        
        # 保存到文件
        with open(self.skip_file, 'w') as f:
            yaml.safe_dump(self.direct_applicable, f)
        
        # 将patch文件复制到skip目录
        if 'patch_path' in patch_info:
            skip_patch_dir = self.skip_file.parent / f"{commit_sha[:6]}"
            skip_patch_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(patch_info['patch_path'], skip_patch_dir / "patch.diff")
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行直接应用补丁"""
        patch_info = context.patch_info
        commit_sha = patch_info.get("commit_sha")
        
        # 如果在跳过列表中，直接返回成功
        if commit_sha and commit_sha in self.direct_applicable:
            logger.info(f"提交 {commit_sha} 在跳过列表中，直接返回成功")
            context["direct_apply_result"] = {
                "success": True,
                "message": "在跳过列表中"
            }
            return context
        
        # 下载补丁文件
        if "patch_url" in patch_info and not patch_info.get("patch_path"):
            patch_path = self.evaluator.download_patch_by_type(
                patch_info["patch_url"], 
                'upstream'
            )
            patch_info["patch_path"] = patch_path
            context.patch_info = dict(patch_info)
        
        # logger.info(f"尝试直接应用补丁: {patch_info.get('patch_path')}")
        if not patch_path:
            logger.error("patch_path is required")
            context.direct_apply_result = {
                'success': False,
                'error': 'patch_path is required'
            }
            return context
        
        try:
            # 尝试直接应用补丁
            apply_result = self.evaluator.try_direct_apply(
                patch_file=patch_path,
                commit_info={"upstream_sha": commit_sha} if commit_sha else None
            )
            
            if apply_result and apply_result.get('success', False):
                # 如果成功，保存到跳过记录
                if commit_sha:
                    self._save_direct_applicable(commit_sha, context.patch_info)
                logger.info("直接应用成功")
                self.last_apply_success = True
            else:
                self.error_count += 1
                error_msg = apply_result.get('error') if apply_result else 'Unknown error'
                logger.warning(f"直接应用失败: {error_msg}")
                self.last_apply_success = False
            
            context.direct_apply_result = apply_result or {
                'success': False,
                'error': 'No result from evaluator'
            }
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"直接应用过程发生错误: {e}")
            context.direct_apply_result = {
                'success': False,
                'error': str(e)
            }
        
        return context
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            "apply_success": self.last_apply_success,
            "error_count": self.error_count
        } 