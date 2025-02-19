from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from enum import Enum
from config_manager import ProjectConfig
from dataclasses import dataclass, field
from datetime import datetime
import copy

@dataclass
class CommitContext:
    """提交相关的运行时上下文"""
    commit_sha: str
    patch_url: str
    target_version: str
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    patch_path: Optional[Path] = None
    reference_url: Optional[str] = None
    commit_message: Optional[str] = None
    author: Optional[str] = None
    timestamp: Optional[str] = None

@dataclass
class ModuleContext:
    config: ProjectConfig
    commit_info: CommitContext

    """模块运行时上下文"""
    patch_info: Dict[str, Any]  # 补丁相关信息
    start_time: datetime = field(default_factory=datetime.now)  # 开始时间
    module_results: List[Dict[str, Any]] = field(default_factory=list)  # 模块执行结果
    direct_apply_result: Optional[Dict[str, Any]] = None  # 直接应用结果
    llm_output: Optional[Dict[str, Any]] = None  # LLM输出
    adapted_patches: Optional[List[Dict[str, Any]]] = None  # 适配的补丁
    compilation_result: Optional[Dict[str, Any]] = None  # 编译结果
    prompt_values: Optional[Any] = None

    # 运行时目录
    base_dir: Path = None

    # 自定义数据
    _custom_data: Dict[str, Any] = field(default_factory=dict)  # 用于存储自定义数据

    @property
    def patch_dir(self) -> Path:
        """patch文件存储路径"""
        return self.base_dir / 'patches'

    @property
    def evaluation_dir(self) -> Path:
        """评估结果存储路径"""
        return self.base_dir / 'evaluations'
    
    def update_workspace(self, owner: str, repo: str, commit_sha: str) -> None:
        """更新工作空间配置"""
        self.base_dir = Path('patchfile') / f"{owner}_{repo}_{commit_sha[:6]}"
        self.ensure_directories()

    def ensure_directories(self) -> None:
        """确保所需目录存在"""
        self.patch_dir.mkdir(parents=True, exist_ok=True)
        self.evaluation_dir.mkdir(parents=True, exist_ok=True)

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
    
    def __post_init__(self):
        """初始化后的处理"""
        # 确保patch_info是深拷贝
        self.patch_info = copy.deepcopy(self.patch_info)
        # 验证必要字段
        self._validate_patch_info()

    def _validate_patch_info(self) -> None:
        """验证patch_info的完整性"""
        # required_fields = {'commit_sha', 'patch_url', 'target_version', 'repo_path'}
        required_fields = {'commit_sha', 'patch_url', 'target_version'}
        missing_fields = required_fields - set(self.patch_info.keys())
        if missing_fields:
            raise ValueError(f"patch_info缺少必要字段: {missing_fields}")
        
    

    @classmethod
    def create_from_config(cls, 
                          config: ProjectConfig,
                          target_version: str,
                          patch_url: Optional[str] = None,
                          prompt_values: Optional[str] = None) -> 'ModuleContext':
        """从配置创建上下文"""
        patch_info = {
            "commit_sha": config.commit_sha if hasattr(config, 'commit_sha') else None,
            "patch_url": patch_url,
            "patch_path": None,
            "target_version": target_version,
            "repo_path": str(config.repo_path),
        }
        
        return cls(
            config=config,
            patch_info=patch_info,
            target_version=target_version,
            patch_url=patch_url,
            prompt_values=prompt_values
        )

    def add_module_result(self, 
                         module_name: str,
                         success: bool,
                         duration: float,
                         metrics: Optional[Dict[str, Any]] = None,
                         error: Optional[str] = None) -> None:
        """添加模块执行结果"""
        result = {
            'module': module_name,
            'success': success,
            'duration': duration,
            'metrics': metrics or {}
        }
        if error:
            result['error'] = error
            
        self.module_results.append(result)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'patch_info': self.patch_info,
            'target_version': self.target_version,
            'patch_url': self.patch_url,
            'reference_url': self.reference_url,
            'commit_sha': self.commit_sha,
            'prompt_values': self.prompt_values,
            'start_time': self.start_time.isoformat(),
            'module_results': self.module_results,
            'direct_apply_result': self.direct_apply_result,
            'llm_output': self.llm_output,
            'adapted_patches': self.adapted_patches,
            'compilation_result': self.compilation_result,
            'custom_data': copy.deepcopy(self._custom_data) if self._custom_data else None
        }
    
    def get_data(self, field_path: str, default: Any = None) -> Any:
        """获取字段值，支持嵌套访问
        
        Args:
            field_path: 字段路径，支持点号分隔，如 'llm_output.error'
            default: 默认值
        """
        try:
            current = self
            for part in field_path.split('.'):
                if isinstance(current, dict):
                    current = current.get(part, default)
                else:
                    current = getattr(current, part, default)
                if current is None:
                    return default
            return current
        except Exception:
            return default
    
    def update_data(self, field_name: str, value: Any, merge: bool = False) -> None:
        """通用数据更新接口
        
        Args:
            field_name: 字段名称，支持点号分隔的嵌套更新
            value: 新值
            merge: 如果为True且目标是字典类型，则合并而不是替换
        """
        if '.' in field_name:
            parts = field_name.split('.')
            current = self
            for part in parts[:-1]:
                if not hasattr(current, part):
                    raise AttributeError(f"找不到字段: {part}")
                current = getattr(current, part)
            
            target = getattr(current, parts[-1], None)
            if merge and isinstance(target, dict) and isinstance(value, dict):
                new_value = copy.deepcopy(target)
                new_value.update(value)
                setattr(current, parts[-1], new_value)
            else:
                setattr(current, parts[-1], copy.deepcopy(value))
            return

        # 处理类属性
        if hasattr(self, field_name):
            if merge and isinstance(getattr(self, field_name), dict) and isinstance(value, dict):
                new_value = copy.deepcopy(getattr(self, field_name))
                new_value.update(value)
                setattr(self, field_name, new_value)
            else:
                setattr(self, field_name, copy.deepcopy(value))
        else:
            # 存储到自定义数据
            if merge and isinstance(self._custom_data.get(field_name), dict) and isinstance(value, dict):
                new_value = copy.deepcopy(self._custom_data.get(field_name, {}))
                new_value.update(value)
                self._custom_data[field_name] = new_value
            else:
                self._custom_data[field_name] = copy.deepcopy(value)

    @property
    def success(self) -> bool:
        """检查整个处理流程是否成功"""
        return all([
            not self.get_data('direct_apply_result.error'),
            not self.get_data('llm_output.error'),
            not self.get_data('adapted_patches.error'),
            not self.get_data('compilation_result.error')
        ])
    
    def __str__(self) -> str:
        """友好的字符串表示"""
        return (
            f"ModuleContext("
            f"commit_sha={self.patch_info.get('commit_sha', 'None')}, "
            f"target_version={self.patch_info.get('target_version', 'None')}, "
            f"prompt_values={'设置' if self.prompt_values else 'None'}, "
            f"success={self.success}"
            f")"
        )
    
    def batch_update(self, data: Dict[str, Any], merge: bool = False) -> None:
        """批量更新多个字段
        
        Args:
            data: 包含要更新的字段和值的字典
            merge: 如果为True且目标是字典类型，则合并而不是替换
        """
        for field_name, value in data.items():
            self.update_data(field_name, value, merge)

    

class ModuleType(Enum):
    DIRECT_APPLY = "direct_apply"
    # AST_PARSER = "ast_parser"
    # FUZZY_MATCHER = "fuzzy_matcher"
    LLM_ADAPTER = "llm_adapter"
    COMPILER = "compiler"
    PATCH_ADAPTER = "patch_adapter"

class BaseModule:
    """模块基类"""
    def __init__(self, config: ProjectConfig):
        self.config = config
        self.type = ModuleType.DIRECT_APPLY
        self.name = "base_module"
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行模块逻辑"""
        raise NotImplementedError
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取模块执行指标"""
        return {} 