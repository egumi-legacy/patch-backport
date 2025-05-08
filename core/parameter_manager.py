from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from enum import Enum
from datetime import datetime
from patch_utils import parse_github_url
from pydantic import BaseModel, Field, field_validator, model_validator

class ModuleType(str, Enum):
    DIRECT_APPLY = "direct_apply"
    BACKTRACK_APPLY = "backtrack_apply"
    CHUNK_ANALYZER = "chunk_analyzer"
    LLM_ADAPTER = "llm_adapter"
    PATCH_ADAPTER = "patch_adapter"
    COMPILER = "compiler"
    

class BaseConfig(BaseModel):
    """基础配置类 - 只包含共同的可选参数"""
    mode: int = 1
    
    # LLM 相关的配置
    model: str = "qwen-plus"
    # temperature: float = 0.7
    # max_tokens: int = 4096
    prompt_template_file: Path = Field(default_factory=lambda: Path("templates.json"))
    prompt_value_file: Path = Field(default_factory=lambda: Path("prompt_values.json"))
    prompt_id: str = "backport"
    use_cached_llm_output: bool = True
    response_file: Optional[Path] = None
    
    enabled_modules: List[str] = Field(default_factory=lambda: [
        "direct_apply", "backtrack_apply", "chunk_analyzer", "llm_adapter", "patch_adapter", "compiler"
    ])
    
    build_command: str = "make"
    module_configs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    retry_with_feedback: bool = False
    stop_on_failure: bool = False
    
    use_cached_patches: bool = False # 是否使用已缓存的patches直接应用
    extra_config: Dict[str, Any] = Field(default_factory=dict)
    repo_path: Optional[Path] = None

    # target_version: str 
    target_version: Union[str, List[str]] = Field(default=None)

    module_configs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # 内核编译器配置
    kernel_compiler: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_version")
    def validate_target_version(cls, v):
        if isinstance(v, str):
            # 向后兼容单一版本
            return [v]
        elif isinstance(v, list) and all(isinstance(item, str) for item in v):
            return v
        else:
            raise ValueError("target_version必须是字符串或字符串列表")

    @field_validator("enabled_modules")
    def validate_enabled_modules(cls, v):
        valid_modules = {"direct_apply", "backtrack_apply", "chunk_analyzer", "llm_adapter", "patch_adapter", "compiler"}
        invalid_modules = set(v) - valid_modules
        if invalid_modules:
            raise ValueError(f"Invalid pipeline modules: {invalid_modules}")
        return v
    
    # Pydantic模块所需，用于验证非基本类型（如 Path ）
    class Config:
        arbitrary_types_allowed = True


class Mode1Config(BaseConfig):
    """模式1配置 - 包含所有必需参数和基础配置"""
    # 必需参数
    patch_url: str

    # 下面三个不用输入，会统一预处理赋值
    repo_name: str
    repo_owner: str
    commit_sha: str
    
    @model_validator(mode='before')
    def process_field(cls, data: Any) -> Dict[str, str]:
        if isinstance(data, dict):
            info = parse_github_url(data['patch_url'])
            if not info:
                raise ValueError(f"无法解析补丁URL: {data['patch_url']}")
            repo_name = info['repo']
            repo_owner = info['owner']
            commit_sha = info['commit_sha']
            return {**data, "repo_name": repo_name, "repo_owner": repo_owner, "commit_sha": commit_sha}
        
        return data

    # def __post_init__(self):
    #     """验证配置"""
    #     if not self.patch_url:
    #         raise ValueError("patch_url is required for Mode 1")
    #     if not self.repo_path.exists():
    #         raise ValueError(f"Repository path does not exist: {self.repo_path}")


class Mode2Config(BaseConfig):
    """模式2配置 - 包含所有必需参数和基础配置"""
    # 必需参数
    repo_url: str
    branch: str

    # 下面两个不用输入，会统一预处理赋值
    repo_name: str
    repo_owner: str
    # repo_path: Path
    # target_version: str
    
    # # 基础配置
    # base_config: BaseConfig = field(default_factory=BaseConfig)
    
    # 模式2特定的可选参数
    # commits_range: tuple[int, int] = Field(default=(0, 100))
    use_cached_commits: bool = False
    commits_pages_start: int = 1
    commits_pages_end: int = 3
    commits_per_page: int = 100

    @model_validator(mode='before')
    def process_field(cls, data: Any) -> Dict[str, str]:
        if isinstance(data, dict):
            info = parse_github_url(data['repo_url'])
            if not info:
                raise ValueError(f"无法解析补丁URL: {data['repo_url']}")
            repo_name = info['repo']
            repo_owner = info['owner']
            return {**data, "repo_name": repo_name, "repo_owner": repo_owner}
        
        return data
    
    @property
    def commits_file(self) -> str:
        return f"branch_{self.branch}_commits.json"
    
    @property
    def cached_commits_file_path(self) -> Path:
        path = Path("workspace") / self.repo_owner / f"{self.repo_name}_cache" / self.commits_file
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    # def __post_init__(self):
    #     """验证配置"""
    #     if not self.repo_url or not self.branch:
    #         raise ValueError("repo_url and branch are required for Mode 2")
    #     if not self.repo_path.exists():
    #         raise ValueError(f"Repository path does not exist: {self.repo_path}")


class CommitContext(BaseModel):
    """提交相关信息（可变）"""
    commit_sha: str
    patch_url: str
    repo_name: str
    repo_owner: str
    reference_url: Optional[str] = None
    downstream_message: Optional[str] = None
    downstream_sha: Optional[str] = None
    author: Optional[str] = None
    timestamp: Optional[str] = None
    patch_path: Optional[Path] = None
    optimized_patch_path: Optional[Path] = None
    
    class Config:
        arbitrary_types_allowed = True

    @property
    def base_dir(self) -> Path:
        """获取基础目录"""
        return Path("workspace") / self.repo_owner / self.repo_name / self.commit_sha[:6]

    @property
    def patch_dir(self) -> Path:
        """获取补丁目录"""
        path = self.base_dir / "patches"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def evaluation_dir(self) -> Path:
        """获取评估目录"""
        path = self.base_dir / "evaluations"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def compilation_dir(self) -> Path:
        """获取编译目录"""
        path = self.base_dir / 'compilation'
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @classmethod
    def create_for_mode1(cls, config: Mode1Config) -> 'CommitContext':
        """创建模式1的提交上下文"""
        # info = config.repo_info
        return cls(
            commit_sha=config.commit_sha,
            patch_url=config.patch_url,
            repo_name=config.repo_name,
            repo_owner=config.repo_owner,
        )
    
    @classmethod
    def create_for_mode2(cls, config: Mode2Config, commit_info: Dict[str, str]) -> 'CommitContext':
        """创建模式2的提交上下文"""
        # info = config.repo_info
        upstream_sha = commit_info['upstream_sha']
        return cls(
            commit_sha=upstream_sha,
            patch_url=f"https://github.com/{config.repo_owner}/{config.repo_name}/commit/{upstream_sha}.patch",
            repo_name=config.repo_name,
            repo_owner=config.repo_owner,
            downstream_sha=commit_info['downstream_sha'],
            downstream_message=commit_info['downstream_message']
        )



class ModuleContext(BaseModel):
    """处理上下文（可变）"""
    # 引用不变配置
    config: Union[Mode1Config, Mode2Config]
    
    # 提交信息（模式1固定，模式2可变）
    commit: CommitContext
    
    # # 工作目录
    # workspace: Path = field(init=False)
    
    # 处理状态和结果
    # start_time: datetime = field(default_factory=datetime.now)
    direct_apply_result: Optional[Dict[str, Any]] = None
    llm_output: Optional[Dict[str, Any]] = None
    # adapted_patches: List[Dict[str, Any]] = Field(default_factory=list)
    compilation_result: List[Dict[str, Any]] = Field(default_factory=list)
    compiler_branch: Optional[str] = None
    patch_adapter_result: List[Dict[str, Any]] = Field(default_factory=list)
    chunk_analyzer_result: List[Dict[str, Any]] = Field(default_factory=list)
    backtrack_result: Optional[Dict[str, Any]] = None

    # 内核编译器配置
    docker_image_built: bool = True

    # 反馈数据
    retry_count: int = 0
    last_error: Optional[str] = None
    feedback_data: Optional[Dict[str, Any]] = None
    
    # 时间相关字段
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    execution_times: Dict[str, float] = Field(default_factory=dict)  # 各模块执行时间

    class Config:
        arbitrary_types_allowed = True

    @property
    def base_dir(self) -> Path:
        """获取工作空间目录"""
        return self.commit.base_dir

    @property
    def patch_dir(self) -> Path:
        """获取补丁目录"""
        return self.commit.patch_dir

    @property
    def cache_dir(self) -> Path:
        """获取直接应用成功的缓存目录"""
        path = Path("workspace") / self.commit.repo_owner / f"{self.commit.repo_name}_cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def adapted_dir(self) -> Path:
        """获取适配后代码目录"""
        path = self.base_dir / f"adapted_{self.config.target_version}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def build_dir(self) -> Path:
        path = self.base_dir / 'build'
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def evaluation_dir(self) -> Path:
        return self.commit.evaluation_dir
    
    @classmethod
    def create_from_patch_info(cls, **patch_info):
        """从补丁信息创建上下文"""
        commit_sha = patch_info.get('commit_sha')
        patch_url = patch_info.get('patch_url')
        repo_path = patch_info.get('repo_path')
        target_version = patch_info.get('target_version')
        
        # 从URL解析仓库信息
        from git_operations import parse_github_url
        url_info = parse_github_url(patch_url)
        
        # 创建配置
        config = Mode1Config(
            target_version=target_version,
            repo_owner=url_info['owner'],
            repo_name=url_info['repo'],
            repo_path=repo_path,
            patch_url=patch_url
        )
        
        # 创建提交上下文
        commit = CommitContext(
            commit_sha=commit_sha,
            patch_url=patch_url,
            repo_owner=url_info['owner'],
            repo_name=url_info['repo']
        )
        
        # 创建模块上下文
        return cls(
            config=config,
            commit=commit
        )

    # def __post_init__(self):
    #     # 设置工作目录
    #     self.workspace = Path('workspace') / self.commit_info.repo_owner / self.commit_info.repo_name / self.commit_info.commit_sha[:8]
    #     self.ensure_directories()

    
    # def update_workspace(self, owner: str, repo: str, commit_sha: str) -> None:
    #     """更新工作空间配置"""
    #     self.base_dir = Path('patchfile') / f"{owner}_{repo}_{commit_sha[:6]}"
    #     self.ensure_directories()


    @classmethod
    def create_from_patch_info(cls, 
                             commit_sha: str,
                             patch_url: str,
                             target_version: str,
                             repo_path: Union[str, Path],
                             downstream_patch_url: Optional[str] = None,
                             patch_path: Optional[str] = None) -> 'ModuleContext':
        """从补丁信息创建上下文"""
        patch_info = {
            "commit_sha": commit_sha,
            "patch_url": patch_url,
            "patch_path": patch_path,
            "target_version": target_version,
            "repo_path": str(repo_path),
            "downstream_patch_url": downstream_patch_url
        }
        
        return cls(patch_info=patch_info)
    
    # def __post_init__(self):
    #     """初始化后的处理"""
    #     # 确保patch_info是深拷贝
    #     self.patch_info = copy.deepcopy(self.patch_info)
    #     # 验证必要字段
    #     self._validate_patch_info()

    # def _validate_patch_info(self) -> None:
    #     """验证patch_info的完整性"""
    #     # required_fields = {'commit_sha', 'patch_url', 'target_version', 'repo_path'}
    #     required_fields = {'commit_sha', 'patch_url', 'target_version'}
    #     missing_fields = required_fields - set(self.patch_info.keys())
    #     if missing_fields:
    #         raise ValueError(f"patch_info缺少必要字段: {missing_fields}")
        
    

    # @classmethod
    # def create_from_config(cls, 
    #                       config: ProjectConfig,
    #                       target_version: str,
    #                       patch_url: Optional[str] = None,
    #                       prompt_values: Optional[str] = None) -> 'ModuleContext':
    #     """从配置创建上下文"""
    #     patch_info = {
    #         "commit_sha": config.commit_sha if hasattr(config, 'commit_sha') else None,
    #         "patch_url": patch_url,
    #         "patch_path": None,
    #         "target_version": target_version,
    #         "repo_path": str(config.repo_path),
    #     }
        
    #     return cls(
    #         config=config,
    #         patch_info=patch_info,
    #         target_version=target_version,
    #         patch_url=patch_url,
    #         prompt_values=prompt_values
    #     )

    # def add_module_result(self, 
    #                      module_name: str,
    #                      success: bool,
    #                      duration: float,
    #                      metrics: Optional[Dict[str, Any]] = None,
    #                      error: Optional[str] = None) -> None:
    #     """添加模块执行结果"""
    #     result = {
    #         'module': module_name,
    #         'success': success,
    #         'duration': duration,
    #         'metrics': metrics or {}
    #     }
    #     if error:
    #         result['error'] = error
            
    #     self.module_results.append(result)

    # # def to_dict(self) -> Dict[str, Any]:
    # #     """转换为字典格式"""
    # #     return {
    # #         'patch_info': self.patch_info,
    # #         'target_version': self.target_version,
    # #         'patch_url': self.patch_url,
    # #         'reference_url': self.reference_url,
    # #         'commit_sha': self.commit_sha,
    # #         'prompt_values': self.prompt_values,
    # #         'start_time': self.start_time.isoformat(),
    # #         'module_results': self.module_results,
    # #         'direct_apply_result': self.direct_apply_result,
    # #         'llm_output': self.llm_output,
    # #         'adapted_patches': self.adapted_patches,
    # #         'compilation_result': self.compilation_result,
    # #         'custom_data': copy.deepcopy(self._custom_data) if self._custom_data else None
    # #     }
    
    # def get_data(self, field_path: str, default: Any = None) -> Any:
    #     """获取字段值，支持嵌套访问
        
    #     Args:
    #         field_path: 字段路径，支持点号分隔，如 'llm_output.error'
    #         default: 默认值
    #     """
    #     try:
    #         current = self
    #         for part in field_path.split('.'):
    #             if isinstance(current, dict):
    #                 current = current.get(part, default)
    #             else:
    #                 current = getattr(current, part, default)
    #             if current is None:
    #                 return default
    #         return current
    #     except Exception:
    #         return default
    
    # def update_data(self, field_name: str, value: Any, merge: bool = False) -> None:
    #     """通用数据更新接口
        
    #     Args:
    #         field_name: 字段名称，支持点号分隔的嵌套更新
    #         value: 新值
    #         merge: 如果为True且目标是字典类型，则合并而不是替换
    #     """
    #     if '.' in field_name:
    #         parts = field_name.split('.')
    #         current = self
    #         for part in parts[:-1]:
    #             if not hasattr(current, part):
    #                 raise AttributeError(f"找不到字段: {part}")
    #             current = getattr(current, part)
            
    #         target = getattr(current, parts[-1], None)
    #         if merge and isinstance(target, dict) and isinstance(value, dict):
    #             new_value = copy.deepcopy(target)
    #             new_value.update(value)
    #             setattr(current, parts[-1], new_value)
    #         else:
    #             setattr(current, parts[-1], copy.deepcopy(value))
    #         return

    #     # 处理类属性
    #     if hasattr(self, field_name):
    #         if merge and isinstance(getattr(self, field_name), dict) and isinstance(value, dict):
    #             new_value = copy.deepcopy(getattr(self, field_name))
    #             new_value.update(value)
    #             setattr(self, field_name, new_value)
    #         else:
    #             setattr(self, field_name, copy.deepcopy(value))
    #     else:
    #         # 存储到自定义数据
    #         if merge and isinstance(self._custom_data.get(field_name), dict) and isinstance(value, dict):
    #             new_value = copy.deepcopy(self._custom_data.get(field_name, {}))
    #             new_value.update(value)
    #             self._custom_data[field_name] = new_value
    #         else:
    #             self._custom_data[field_name] = copy.deepcopy(value)

    # @property
    # def success(self) -> bool:
    #     """检查整个处理流程是否成功"""
    #     return all([
    #         not self.get_data('direct_apply_result.error'),
    #         not self.get_data('llm_output.error'),
    #         not self.get_data('adapted_patches.error'),
    #         not self.get_data('compilation_result.error')
    #     ])
    
    # def __str__(self) -> str:
    #     """友好的字符串表示"""
    #     return (
    #         f"ModuleContext("
    #         f"commit_sha={self.patch_info.get('commit_sha', 'None')}, "
    #         f"target_version={self.patch_info.get('target_version', 'None')}, "
    #         f"prompt_values={'设置' if self.prompt_values else 'None'}, "
    #         f"success={self.success}"
    #         f")"
    #     )
    
    # def batch_update(self, data: Dict[str, Any], merge: bool = False) -> None:
    #     """批量更新多个字段
        
    #     Args:
    #         data: 包含要更新的字段和值的字典
    #         merge: 如果为True且目标是字典类型，则合并而不是替换
    #     """
    #     for field_name, value in data.items():
    #         self.update_data(field_name, value, merge)

    @property
    def execution_time(self) -> Optional[float]:
        """获取总执行时间（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None