from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import os

@dataclass
class PipelineConfig:
    """Pipeline配置"""
    enabled_modules: List[str] = field(default_factory=lambda: [
        "direct_apply", "llm_adapter", "patch_adapter", "compiler"
    ])
    module_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    stop_on_failure: bool = False

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

    # 新增pipeline配置
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

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

        # 确保目录存在
        if self.base_dir:
            self.base_dir.mkdir(parents=True, exist_ok=True)

        # 如果提供了pipeline配置，创建PipelineConfig对象
        if isinstance(self.pipeline, dict):
            self.pipeline = PipelineConfig(**self.pipeline)

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

    def dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'repo_path': str(self.repo_path),
            'patch_dir': str(self.patch_dir),
            'evaluation_dir': str(self.evaluation_dir),
            'base_dir': str(self.base_dir) if self.base_dir else None,
            'target_version': self.target_version,
            'mode': self.mode,
            'patch_url': self.patch_url,
            'reference_url': self.reference_url,
            'repo_owner': self.repo_owner,
            'repo_name': self.repo_name,
            'commit_sha': self.commit_sha,
            'use_cached_patches': self.use_cached_patches,
            'pipeline': {
                'enabled_modules': self.pipeline.enabled_modules,
                'module_configs': self.pipeline.module_configs,
                'stop_on_failure': self.pipeline.stop_on_failure
            }
        } 

    def validate_config(self) -> List[str]:
        """验证配置的完整性和正确性"""
        errors = []
        
        # 检查必要的路径
        if not self.repo_path.exists():
            errors.append(f"仓库路径不存在: {self.repo_path}")
        
        # 检查模式相关的必要参数
        if self.mode == 1:
            if not self.patch_url:
                errors.append("模式1需要patch_url参数")
        
        # 检查pipeline配置
        if not self.pipeline.enabled_modules:
            errors.append("pipeline.enabled_modules不能为空")
        
        # 检查模块配置
        for module in self.pipeline.enabled_modules:
            if module not in ["direct_apply", "llm_adapter", "patch_adapter", "compiler"]:
                errors.append(f"未知的模块: {module}")
        
        return errors 