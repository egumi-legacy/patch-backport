from typing import Dict, Any, OrderedDict
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class AdaptationResult:
    """适配结果数据类"""
    metadata: Dict[str, Any]  # 元数据（时间戳、commit信息等）
    configuration: Dict[str, Any]  # 配置信息（使用的模块、配置等）
    results: Dict[str, Any]  # 处理结果（各模块的执行结果）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典"""
        def _convert_value(value):
            if isinstance(value, Path):
                return str(value)
            elif isinstance(value, datetime):
                return value.isoformat()
            elif isinstance(value, (dict, OrderedDict)):
                return {k: _convert_value(v) for k, v in value.items()}
            elif isinstance(value, (list, tuple)):
                return [_convert_value(v) for v in value]
            elif isinstance(value, (set, frozenset)):
                return [_convert_value(v) for v in value]
            elif hasattr(value, 'dict') and callable(value.dict):
                return value.dict()
            elif hasattr(value, 'to_dict') and callable(value.to_dict):
                return value.to_dict()
            elif hasattr(value, '__dict__'):
                return {k: _convert_value(v) for k, v in value.__dict__.items() 
                       if not k.startswith('_')}
            return value

        try:
            return {
                'metadata': _convert_value(self.metadata),
                'configuration': _convert_value(self.configuration),
                'results': _convert_value(self.results)
            }
        except Exception as e:
            logger.error(f"序列化失败: {e}")
            return {
                'metadata': {},
                'configuration': {},
                'results': {'error': str(e)}
            }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AdaptationResult':
        """从字典创建实例"""
        return cls(
            metadata=data.get('metadata', {}),
            configuration=data.get('configuration', {}),
            results=data.get('results', {})
        )
    
    def get_final_status(self) -> Dict[str, Any]:
        """获取最终状态"""
        return self.results.get('final_status', {
            'success': False,
            'error': 'No final status available'
        })
    
    def get_module_result(self, module_name: str) -> Dict[str, Any]:
        """获取特定模块的结果"""
        module_results = self.results.get('module_results', [])
        for result in module_results:
            if result.get('module') == module_name:
                return result
        return {}
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有模块的指标"""
        metrics = {}
        for module_result in self.results.get('module_results', []):
            module_name = module_result.get('module')
            if module_name and 'metrics' in module_result:
                metrics[module_name] = module_result['metrics']
        return metrics
    
    def get_duration_stats(self) -> Dict[str, float]:
        """获取处理时间统计"""
        module_results = self.results.get('module_results', [])
        return {
            'total_duration': sum(r.get('duration', 0) for r in module_results),
            'average_duration': (
                sum(r.get('duration', 0) for r in module_results) / len(module_results)
                if module_results else 0
            ),
            'module_durations': {
                r.get('module'): r.get('duration', 0)
                for r in module_results
            }
        } 