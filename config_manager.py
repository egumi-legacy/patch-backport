from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import os

@dataclass
class ProjectConfig:
    """项目配置类，统一管理所有配置参数"""
    # 基础配置
    mode: int
    
    # Git相关配置
    patch_url: Optional[str] = None  # mode1: URL to the patch
    repo_owner: Optional[str] = None # mode1: Repository owner for local repo
    repo_name: Optional[str] = None  # mode1: Repository name for local repo
    target_version: Optional[str] = None
    repo_url: Optional[str] = None  # mode2
    branch: Optional[str] = None  # mode2
    repo_path: Optional[Path] = None
    reference_url: Optional[str] = None  # mode2
    commits_pages_start: int = 1  # 起始页
    commits_pages_end: int = 1    # 结束页
    commits_per_page: int = 100   # 每页数量
    
    # 路径配置
    base_dir: Optional[Path] = None
    
    # 缓存配置
    use_cached_patches: bool = False
    use_cached_commits: bool = False
    commits_file: Optional[Path] = None
    
    # LLM配置
    model: str = "qwen-plus"
    use_cache: bool = False
    prompt_id: str = "backport"
    prompt_template_file: str = "test_prompts.json"
    prompt_value_file: str = "test_prompt_values.json"
    response_file: str = "response.txt"
    
    # 其他配置
    extra_config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """初始化后的处理"""
        # 转换路径类型
        if self.repo_path and isinstance(self.repo_path, str):
            self.repo_path = Path(self.repo_path)
        if self.commits_file and isinstance(self.commits_file, str):
            self.commits_file = Path(self.commits_file)
        if self.base_dir and isinstance(self.base_dir, str):
            self.base_dir = Path(self.base_dir)
        if self.prompt_template_file and isinstance(self.prompt_template_file, str):
            self.prompt_template_file = Path(self.prompt_template_file)
        if self.prompt_value_file and isinstance(self.prompt_value_file, str):
            self.prompt_value_file = Path(self.prompt_value_file)
        if self.response_file and isinstance(self.response_file, str):
            self.response_file = Path(self.response_file)

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

    def __getitem__(self, key):
        """支持字典式访问"""
        if hasattr(self, key):
            return getattr(self, key)
        return self.extra_config.get(key) 

    def get_repo_url(self) -> Optional[str]:
        """获取仓库URL"""
        if self.mode == 1 and self.repo_owner and self.repo_name:
            return f"https://github.com/{self.repo_owner}/{self.repo_name}"
        return self.repo_url 