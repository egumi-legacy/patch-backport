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

_DEFAULT_INPUT_FILE = Path(__file__).parent / "inputs.yaml"


class Main:
    def __init__(self):
        self.args = self.parse_arguments()
        with open(_DEFAULT_INPUT_FILE, "r") as file:
            yaml_config = YAML().load(file)
        
        # 初始化配置
        self.config = self.initialize_config(yaml_config)
        
    def parse_arguments(self):
        parser = argparse.ArgumentParser(description='Patch Processing Tool')
        parser.add_argument('--mode', type=int, choices=[1, 2], required=True,
                          help='Mode 1: Single commit patch, Mode 2: Multiple commits from branch')
        return parser.parse_args()
    
    def initialize_config(self, yaml_config):
        """初始化配置对象"""
        # 获取通用配置
        common_config = yaml_config.get('common', {})
        
        # 根据模式合并特定配置
        mode_config = yaml_config.get(f'mode{self.args.mode}', {})
        
        # 合并配置
        config_dict = {**common_config, **mode_config}
        config_dict['mode'] = self.args.mode
        
        return ProjectConfig(**config_dict)

    def process_multiple_commits(self):
        git_operations = GitOperations(self.config)
        upstream_commits = git_operations.get_upstream_commits()
        if not upstream_commits:
            logger.error("未找到上游提交信息")
            raise Exception("未找到上游提交信息")
        
        batch_results = []
        
        for commit in upstream_commits[260:280]:
            logger.info(f"处理上游提交: {commit['upstream_sha']}")
            
            # 更新commit相关配置
            commit_details = git_operations.get_commit_details(commit)
            self.config.update(**commit_details)
            
            # 更新base_dir
            url_info = git_operations.parse_github_url(commit_details['patch_url'])
            self.config.update_base_dir(
                owner=url_info['owner'],
                repo=url_info['repo'],
                commit_sha=commit['upstream_sha']
            )
            
            # 创建评估器
            evaluator = PatchEvaluator(self.config)
            
            # 首先尝试直接应用上游补丁
            evaluation_result = evaluator.try_direct_apply(
                upstream_patch_url=self.config.patch_url,
                commit_info=commit
            )
            
            # 如果直接应用失败，进行LLM处理
            if not evaluation_result['upstream_apply']['success']:
                logger.info("直接应用失败，开始LLM处理流程...")
                processor = PatchProcessor(self.config)
                processor.process_single_commit()
                
                # 评估适配后的结果
                adapted_result = evaluator.evaluate_adapted_patch(
                    adapted_dir=self.config.base_dir / f"adapted_{self.config.target_version}",
                    downstream_patch_url=self.config.reference_url
                )
                
                evaluation_result.update(adapted_result)
            else:
                logger.info("直接应用成功，跳过LLM处理流程")
            
            # 收集评估结果
            batch_results.append({
                'commit_info': commit,
                'evaluation': evaluation_result
            })
        
        # 保存批量评估结果
        # evaluator = PatchEvaluator(self.inputs['repo_path'], self.inputs)
        evaluator.save_batch_evaluation_results(batch_results)

    def process_single_commit(self):
        """
        处理模式1：单个提交补丁
        """
        # 确保必要的参数存在
        required_params = ['patch_url', 'target_version']
        for param in required_params:
            if not getattr(self.config, param):
                raise ValueError(f"Missing required parameter for mode 1: {param}")
        
        # 解析URL并更新base_dir
        git_operations = GitOperations(self.config)
        owner, repo = git_operations.parse_github_url(self.config.patch_url)
        commit_sha = git_operations.parse_github_url(self.config.patch_url)['commit_sha']
        self.config.update_base_dir(owner, repo, commit_sha)
        
        # 处理单个提交
        processor = PatchProcessor(self.config)
        processor.process_single_commit()

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