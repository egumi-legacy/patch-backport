from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import os

@dataclass
class ProjectConfig:
    """项目配置类，统一管理所有配置参数"""
    # 基础配置
    mode: int
    target_version: str
    model: str = "gpt-3.5-turbo"
    
    # 路径配置
    base_dir: Optional[Path] = None
    repo_path: Optional[Path] = None
    
    # Git相关配置
    repo_url: Optional[str] = None
    branch: Optional[str] = None
    patch_url: Optional[str] = None
    reference_url: Optional[str] = None
    
    # 缓存配置
    use_cached_patches: bool = False
    use_cached_commits: bool = False
    
    # 其他配置
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def update(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.extra_config[key] = value

    def update_base_dir(self, owner: str, repo: str, commit_sha: str):
        """更新base_dir"""
        self.base_dir = Path('patchfile') / f"{owner}_{repo}_{commit_sha[:6]}"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    @property
    def patch_dir(self) -> Path:
        """patch文件存储路径"""
        if not self.base_dir:
            raise ValueError("base_dir not set")
        return self.base_dir / 'patches'

    @property
    def evaluation_dir(self) -> Path:
        """评估结果存储路径"""
        if not self.base_dir:
            raise ValueError("base_dir not set")
        return self.base_dir / 'evaluations'

    def ensure_directories(self):
        """确保所需目录存在"""
        if self.base_dir:
            self.patch_dir.mkdir(parents=True, exist_ok=True)
            self.evaluation_dir.mkdir(parents=True, exist_ok=True) 