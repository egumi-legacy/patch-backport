from pathlib import Path
from ruamel.yaml import YAML
import pprint
from llm_assistant import LLMAssistant
from patch_processor import PatchProcessor
# from commit_scanner import CommitScanner
from git_operations import GitOperations
import argparse
from loguru import logger
import json
from patch_evaluator import PatchEvaluator
from config_manager import ProjectConfig
import re
# from tracking_manager import TrackingManager
from adaptation_pipeline_bak import AdaptationPipeline
import yaml
from datetime import datetime
import shutil
from core.tracking_result import TrackingResult

_DEFAULT_INPUT_FILE = Path(__file__).parent / "inputs.yaml"


class Main:
    def __init__(self):
        self.args = self.parse_arguments()
        with open(_DEFAULT_INPUT_FILE, "r") as file:
            yaml_config = YAML().load(file)
        
        # 初始化配置
        self.config = self.initialize_config(yaml_config)

        # 追踪管理器
        # self.tracking = TrackingManager(self.config)  
        
        
    def parse_arguments(self):
        parser = argparse.ArgumentParser(description='Patch Processing Tool')
        parser.add_argument('--mode', type=int, choices=[1, 2], required=True,
                          help='Mode 1: Single commit patch, Mode 2: Multiple commits from branch')
        
        # 为模式1添加可选参数
        mode1_group = parser.add_argument_group('Mode 1 arguments')
        mode1_group.add_argument('--patch-url', type=str,
                          help='Full URL to the commit patch')
        mode1_group.add_argument('--owner', type=str,
                          help='Repository owner for local repo (e.g., "django" in django/django)')
        mode1_group.add_argument('--repo', type=str,
                          help='Repository name for local repo (e.g., "django" in django/django)')
        mode1_group.add_argument('--target', type=str,
                          help='Target version for backporting')
        
        args = parser.parse_args()
        return args
    
    def initialize_config(self, yaml_config):
        """初始化配置对象"""
        # 获取通用配置
        common_config = yaml_config.get('common', {})
        
        # 根据模式合并特定配置
        mode_config = yaml_config.get(f'mode{self.args.mode}', {})
        
        # 合并配置
        config_dict = {**common_config, **mode_config}
        config_dict['mode'] = self.args.mode
        
        # 如果是模式1，使用命令行参数覆盖配置文件
        if self.args.mode == 1:
            # 处理patch_url
            if self.args.patch_url:
                config_dict['patch_url'] = self.args.patch_url
            
            # 处理仓库信息
            if self.args.owner and self.args.repo:
                config_dict['repo_owner'] = self.args.owner
                config_dict['repo_name'] = self.args.repo
            
            # 处理目标版本
            if self.args.target:
                config_dict['target_version'] = self.args.target
        
        return ProjectConfig(**config_dict)

    def process_commit_range(self, start_index: int, end_index: int):
        """处理指定范围内的提交
        
        :param start_index: 起始索引
        :param end_index: 结束索引
        :return: 处理结果列表
        """
        git_operations = GitOperations(self.config)
        upstream_commits = git_operations.get_upstream_commits()
        
         # # 加载已知可直接应用的提交记录
        # direct_apply_file = Path("skip_git_am_patchfile") / "commits.yaml"
        # direct_apply_file.parent.mkdir(parents=True, exist_ok=True)
        # # 设置基础目录
        # if not self.config.base_dir:
        #     self.config.base_dir = Path("projects") / f"{self.config.repo_owner}_{self.config.repo_name}"
        #     self.config.base_dir.mkdir(parents=True, exist_ok=True)
        
        # if direct_apply_file.exists():
        #     with open(direct_apply_file, 'r') as f:
        #         direct_applicable = yaml.safe_load(f) or {}
        # else:
        #     direct_applicable = {}
        
        # batch_results = []
        # 创建结果追踪器
        
        
        for commit in upstream_commits[start_index:end_index]:
            commit_sha = commit['upstream_sha']
            
            # # 检查是否是已知可直接应用的提交
            # if commit_sha in direct_applicable:
            #     logger.info(f"跳过已知可直接应用的提交: {commit_sha}")
            # 检查是否已处理过
            tracking = TrackingResult(self.config.base_dir)
            logger.info(f"基础目录: {self.config.base_dir}")
            existing_status = tracking.get_commit_status(commit_sha)
            if existing_status:
                logger.info(f"跳过已处理的提交: {commit_sha}")
                continue
            
            try:
                logger.info(f"处理上游提交: {commit_sha}")
                
                # 更新commit相关配置
                commit_details = git_operations.get_commit_details(commit)
                self.config.update(**commit_details)
                
                # 更新base_dir
                url_info = git_operations.parse_github_url(commit_details['patch_url'])

                evaluator = PatchEvaluator(self.config)
                
                # 首先尝试直接应用
                patch_path = evaluator.download_patch_by_type(commit_details['patch_url'], 'upstream')
                if not patch_path:
                    logger.error("下载patch失败，跳过此commit")
                    continue
                
                # 尝试直接应用
                direct_result = evaluator.try_direct_apply(
                    patch_file=patch_path,
                    commit_info=commit
                )
                
                if direct_result['success']:
                    # # 如果可以直接应用，记录到skip_git_am_patchfile
                    # logger.info(f"提交 {commit_sha} 可以直接应用")
                    # direct_applicable[commit_sha] = {
                    # 保存直接应用结果
                    tracking.save_direct_apply_result(commit_sha, {
                        'timestamp': datetime.now().isoformat(),
                        'patch_url': commit_details['patch_url'],
                        'target_version': self.config.target_version,
                        'apply_result': direct_result
                    # }
                    
                    # # 将patch文件移动到skip_git_am_patchfile目录
                    # direct_patch_dir = Path("skip_git_am_patchfile") / f"{url_info['owner']}_{url_info['repo']}_{commit_sha[:6]}"
                    # direct_patch_dir.mkdir(parents=True, exist_ok=True)
                    # shutil.copy2(patch_path, direct_patch_dir / "patch.diff")
                    
                    # # 保存更新后的记录
                    # with open(direct_apply_file, 'w') as f:
                    #     yaml.safe_dump(direct_applicable, f)
                    })
                    continue
                
                # 如果不能直接应用，使用常规流程处理
                self.config.update_base_dir(
                    owner=url_info['owner'],
                    repo=url_info['repo'],
                    # commit_sha=commit['upstream_sha']
                    commit_sha=commit_sha
                )
                
                # # 创建评估器
                # evaluator = PatchEvaluator(self.inputs['repo_path'], self.inputs)
                # 创建pipeline配置
                pipeline_config = {
                    "enabled_modules": self.config.pipeline.enabled_modules,
                    "results_dir": self.config.base_dir / "results",
                    "direct_apply_config": self.config.dict(),
                    "llm_adapter_config": self.config.dict(),
                    "patch_adapter_config": self.config.dict(),
                    "compiler_config": self.config.dict(),
                    "stop_on_failure": self.config.pipeline.stop_on_failure
                }
                
                # # 下载patch文件
                # patch_path = evaluator.download_patch_by_type(self.config.patch_url, 'upstream')
                # if not patch_path:
                #     logger.error("下载patch失败，跳过此commit")
                #     continue

                # 创建pipeline
                pipeline = AdaptationPipeline(pipeline_config)
                
                
                # # 首先尝试直接应用上游补丁
                # evaluation_result = evaluator.try_direct_apply(
                #     patch_file=patch_path,
                #     commit_info=commit
                # )
                # # 如果直接应用失败，进行LLM处理
                # if not evaluation_result['upstream_apply']['success']:
                #     logger.info("直接应用失败，开始LLM处理流程...")
                #     processor = PatchProcessor(self.config)
                #     processor.process_single_commit()
                    
                #     # 评估适配后的结果
                #     adapted_result = evaluator.evaluate_adapted_patch(
                #         adapted_dir=self.config.base_dir / f"adapted_{self.config.target_version}",
                #         downstream_patch_url=self.config.reference_url
                #     )
                    
                #     evaluation_result.update(adapted_result)
                #     # 记录每个commit的处理结果
                #     tracking_data = {
                #         'commit_sha': commit['upstream_sha'],
                #         'patch_url': commit_details['patch_url'],
                #         'target_version': self.config.target_version,
                #         'success': evaluation_result['adapted_apply']['success'],
                #         'failure_reason': evaluation_result['adapted_apply'].get('error', ''),
                #         'similarity_score': evaluation_result.get('patch_comparison', {}).get('similarity', 0),
                #         'evaluation_results': evaluation_result
                #     }
                #     self.tracking.record_attempt(tracking_data)
                # else:
                #     logger.info("直接应用成功，跳过LLM处理流程")
                
                # # 收集评估结果
                # batch_results.append({
                #     'commit_info': commit,
                #     'evaluation': evaluation_result
                #     })
                #  # 保存批量评估结果
                # # evaluator = PatchEvaluator(self.inputs['repo_path'], self.inputs)
                # evaluator.save_batch_evaluation_results(batch_results)
                # 准备patch信息
                patch_info = {
                    "commit_sha": commit_sha,
                    "patch_path": patch_path,
                    "target_version": self.config.target_version,
                    "repo_path": self.config.repo_path,
                    "downstream_patch_url": commit_details.get('reference_url')
                }
                
                # 执行pipeline
                result = pipeline.process_patch(patch_info)
                
                
                # # 记录结果
                # self.tracking.record_attempt({
                #     # 'commit_sha': commit['upstream_sha'],
                #     'commit_sha': commit_sha,
                #     'patch_url': commit_details['patch_url'],
                #     'target_version': self.config.target_version,
                #     'success': result.results['final_status']['success'],
                #     'failure_reason': result.results['final_status'].get('error', ''),
                #     'evaluation_results': result.to_dict()
                # })
                
                # batch_results.append(result)
                # 保存适配结果
                tracking.save_adaptation_result(commit_sha, result.to_dict())
                
            except Exception as e:
                logger.error(f"处理提交 {commit_sha} 时发生错误: {e}")
                # self.tracking.record_attempt({
                #     'commit_sha': commit_sha,
                #     'patch_url': commit_details.get('patch_url', 'unknown'),
                #     'target_version': self.config.target_version,
                tracking.save_adaptation_result(commit_sha, {
                    'error': str(e),
                    'success': False,
                    'timestamp': datetime.now().isoformat()
                })
        
        # 生成统计信息
        stats = tracking.generate_statistics()
        logger.info(f"处理完成，统计信息: {stats}")
        return stats

    def process_multiple_commits(self):
        """处理模式2：多个提交"""
        return self.process_commit_range(100, 105)  # 使用之前的范围

    def process_single_commit(self):
        # """
        # 处理模式1：单个提交补丁
        # """
        # # 确保必要的参数存在
        # required_params = ['patch_url', 'target_version']
        # for param in required_params:
        #     if not getattr(self.config, param):
        #         raise ValueError(f"Missing required parameter for mode 1: {param}")
        
        # # 解析URL并更新base_dir
        # git_operations = GitOperations(self.config)
        # # owner, repo = git_operations.parse_github_url(self.config.patch_url)
        # url_info = git_operations.parse_github_url(self.config.patch_url)
        # self.config.update_base_dir(
        #     owner=url_info['owner'],
        #     repo=url_info['repo'],
        #     commit_sha=url_info['commit_sha']
        # )
        
        # # 创建评估器
        # evaluator = PatchEvaluator(self.config)
        
        # # 下载patch文件
        # patch_path = evaluator.download_patch_by_type(self.config.patch_url, 'upstream')
        # if not patch_path:
        #     logger.error("下载patch失败")
        #     return
        
        # # 首先尝试直接应用上游补丁
        # evaluation_result = evaluator.try_direct_apply(
        #     patch_file=patch_path,
        #     single_file=False
        # )
        
        # # # 处理单个提交
        # # processor = PatchProcessor(self.config)
        # # processor.process_single_commit()
        # # 如果直接应用失败，进行LLM处理
        # if not evaluation_result['upstream_apply']['success']:
        #     logger.info("直接应用失败，开始LLM处理流程...")
        #     processor = PatchProcessor(self.config)
        #     processor.process_single_commit()
            
        #     # 评估适配后的结果
        #     adapted_result = evaluator.evaluate_adapted_patch(
        #         adapted_dir=self.config.base_dir / f"adapted_{self.config.target_version}",
        #         downstream_patch_url=None  # 模式1没有下游补丁
        #     )
            
        #     evaluation_result.update(adapted_result)
        # else:
        #     logger.info("直接应用成功，跳过LLM处理流程")
        
        # # 保存评估结果
        # commit_info = {
        #     'upstream_sha': url_info['commit_sha'],
        #     'downstream_sha': None,  # 模式1没有下游提交
        #     'downstream_message': None
        # }
        
        # batch_results = [{
        #     'commit_info': commit_info,
        #     'evaluation': evaluation_result
        # }]
        
        # evaluator.save_batch_evaluation_results(batch_results)
        pipeline_config = {
            "enabled_modules": ["direct_apply", "llm_adapter", "patch_adapter", "compiler"],
            "results_dir": self.config.base_dir / "results",
            "direct_apply_config": self.config.dict(),
            "llm_adapter_config": self.config.dict(),
            "patch_adapter_config": self.config.dict(),
            "compiler_config": self.config.dict(),
            "stop_on_failure": False  # 允许在模块失败后继续执行
        }
        pipeline = AdaptationPipeline(pipeline_config)
        # 准备patch信息
        patch_info = {
            "commit_sha": self.config.commit_sha,
            "patch_path": self.evaluator.download_patch_by_type(self.config.patch_url, 'upstream'),
            "target_version": self.config.target_version,
            "repo_path": self.config.repo_path
        }
        # 执行pipeline
        result = pipeline.process_patch(patch_info)
        
        # 更新配置
        self.config.update(adaptation_result=result)
        

    def run(self):
        if self.args.mode == 1:
            self.process_single_commit()
        elif self.args.mode == 2:
            self.process_multiple_commits()
        else:
            raise ValueError(f"Invalid mode: {self.args.mode}")


if __name__ == "__main__":
    main = Main()
    main.run()