from pathlib import Path
from typing import Dict, Any, List
import yaml
from datetime import datetime
import json
from dataclasses import dataclass, asdict

@dataclass
class TrackingStats:
    """统计信息数据类"""
    total_commits: int
    direct_applicable: int
    llm_processed: int
    successful_adaptations: int
    failed_adaptations: int
    average_duration: float
    success_rate: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class TrackingResult:
    def __init__(self, base_dir: Path):
        """初始化追踪结果管理器"""
        if base_dir is None:
            raise ValueError("base_dir cannot be None")
        
        self.base_dir = Path(base_dir)
        self.results_dir = self.base_dir / "results"
        self.direct_apply_dir = self.base_dir / "skip_git_am_patchfile"
        self.stats_file = self.base_dir / "statistics.yaml"
        
        # 确保目录存在
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.direct_apply_dir.mkdir(parents=True, exist_ok=True)
    
    def save_direct_apply_result(self, commit_sha: str, result: Dict[str, Any]):
        """保存直接应用的结果"""
        # 保存到commits.yaml
        commits_file = self.direct_apply_dir / "commits.yaml"
        if commits_file.exists():
            with open(commits_file) as f:
                commits = yaml.safe_load(f) or {}
        else:
            commits = {}
        
        commits[commit_sha] = result
        with open(commits_file, 'w') as f:
            yaml.safe_dump(commits, f)
    
    def save_adaptation_result(self, commit_sha: str, result: Dict[str, Any]):
        """保存适配结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = self.results_dir / f"{commit_sha}_{timestamp}.yaml"
        
        with open(result_file, 'w') as f:
            yaml.safe_dump(result, f)
    
    def generate_statistics(self) -> TrackingStats:
        """生成统计信息"""
        # 读取直接应用的结果
        direct_results = {}
        commits_file = self.direct_apply_dir / "commits.yaml"
        if commits_file.exists():
            with open(commits_file) as f:
                direct_results = yaml.safe_load(f) or {}
        
        # 读取适配结果
        adaptation_results = []
        for result_file in self.results_dir.glob("*.yaml"):
            with open(result_file) as f:
                adaptation_results.append(yaml.safe_load(f))
        
        # 计算统计信息
        total_commits = len(direct_results) + len(adaptation_results)
        successful_adaptations = sum(
            1 for r in adaptation_results 
            if r['results']['final_status']['success']
        )
        total_duration = sum(
            r['results']['final_status']['total_duration'] 
            for r in adaptation_results
        )
        
        stats = TrackingStats(
            total_commits=total_commits,
            direct_applicable=len(direct_results),
            llm_processed=len(adaptation_results),
            successful_adaptations=successful_adaptations,
            failed_adaptations=len(adaptation_results) - successful_adaptations,
            average_duration=total_duration / len(adaptation_results) if adaptation_results else 0,
            success_rate=(successful_adaptations + len(direct_results)) / total_commits if total_commits else 0
        )
        
        # 保存统计信息
        with open(self.stats_file, 'w') as f:
            yaml.safe_dump(stats.to_dict(), f)
        
        return stats
    
    def get_commit_status(self, commit_sha: str) -> Dict[str, Any]:
        """获取某个提交的处理状态"""
        # 检查是否是直接应用的提交
        commits_file = self.direct_apply_dir / "commits.yaml"
        if commits_file.exists():
            with open(commits_file) as f:
                direct_results = yaml.safe_load(f) or {}
                if commit_sha in direct_results:
                    return {
                        'type': 'direct_apply',
                        'result': direct_results[commit_sha]
                    }
        
        # 查找适配结果
        for result_file in self.results_dir.glob(f"{commit_sha}_*.yaml"):
            with open(result_file) as f:
                return {
                    'type': 'adaptation',
                    'result': yaml.safe_load(f)
                }
        
        return None 