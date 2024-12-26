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

_DEFAULT_INPUT_FILE = Path(__file__).parent / "inputs.yaml"


class Main:
    def __init__(self):
        self.args = self.parse_arguments()
        with open(_DEFAULT_INPUT_FILE, "r") as file:
            self.yaml_config = YAML().load(file)
        
        # if self.args.mode == 2:
        #     # 获取是否使用缓存的commits文件
        #     self.use_cached_commits = self.inputs.get('use_cached_commits', False)
        #     self.commits_file = Path(self.inputs.get('commits_file', _DEFAULT_COMMITS_FILE))

        # 初始化配置
        self.initialize_config()
        
    def parse_arguments(self):
        parser = argparse.ArgumentParser(description='Patch Processing Tool')
        parser.add_argument('--mode', type=int, choices=[1, 2], required=True,
                          help='Mode 1: Single commit patch, Mode 2: Multiple commits from branch')
        return parser.parse_args()
    
    def initialize_config(self):
        # 获取通用配置
        self.inputs = self.yaml_config.get('common', {})
        
        # 根据模式合并特定配置
        mode_config = {}
        if self.args.mode == 1:
            mode_config = self.yaml_config.get('mode1', {})
        else:
            mode_config = self.yaml_config.get('mode2', {})
        
        # 合并配置
        self.inputs.update(mode_config)

    def process_single_commit(self):
        # 确保必要的参数存在
        required_params = ['patch_url', 'target_version']
        for param in required_params:
            if param not in self.inputs:
                raise ValueError(f"Missing required parameter for mode 1: {param}")
            
        # 处理单个提交
        patch_processor = PatchProcessor(self.inputs)
        patch_processor_outputs = patch_processor.run()
        self.inputs.update(patch_processor_outputs)

        use_cache = self.inputs.get("use_cache", False)
        if use_cache:
            self.inputs["cache_path"] = patch_processor.get_response_path()

        llm_output = LLMAssistant(self.inputs).run()
        self.inputs.update(llm_output)

        for response in llm_output["openai_responses"]:
            if not use_cache:
                output_path = patch_processor.save_response_to_project(response)
            else:
                output_path = self.inputs["cache_path"]

            patch_processor.apply_llm_patch(output_path)
            patch_processor.generate_folder_diff(
                self.inputs['basedir'] / self.inputs['target_version'],
                self.inputs['basedir'] / f'adapted_{self.inputs["target_version"]}',
                self.inputs['basedir'] / f'adapted_diff_{self.inputs["target_version"]}'
            )
        

    def process_multiple_commits(self):
        # 确保必要的参数存在
        required_params = ['repo_url', 'branch', 'target_version']
        for param in required_params:
            if param not in self.inputs:
                raise ValueError(f"Missing required parameter for mode 2: {param}")

        git_operations = GitOperations(self.inputs)
        upstream_commits = git_operations.get_upstream_commits()
        if not upstream_commits:
            logger.error("未找到上游提交信息")
            return
        
        batch_results = []
        for commit in upstream_commits[10:15]:
            logger.info(f"处理上游提交: {commit['upstream_sha']}")
            commit_details = git_operations.get_commit_details(commit)
            self.inputs.update(commit_details)

            # 复用模式1的处理逻辑
            self.process_single_commit()

            # 评估patch应用效果
            evaluation_results = git_operations.evaluate_patch_application(
                repo_path=self.inputs['repo_path'],
                commit_info=commit
            )
            
            # 收集评估结果
            batch_results.append({
                'commit_info': commit,
                'evaluation': evaluation_results
            })
        
        # 保存批量评估结果
        evaluator = PatchEvaluator(self.inputs['repo_path'], self.inputs)
        evaluator.save_batch_evaluation_results(batch_results)

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