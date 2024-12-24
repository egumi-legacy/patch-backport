from pathlib import Path
from ruamel.yaml import YAML
import pprint
from llm_assistant import LLMAssistant
from patch_processor import PatchProcessor
from commit_scanner import CommitScanner
import argparse
from loguru import logger
import json

_DEFAULT_INPUT_FILE = Path(__file__).parent / "inputs.yaml"
_DEFAULT_COMMITS_FILE = Path(__file__).parent / "commits.json"

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

        use_cached_commits = self.inputs.get('use_cached_commits', False)
        commits_file = Path(self.inputs.get('commits_file', _DEFAULT_COMMITS_FILE))

        upstream_commits = self.get_upstream_commits(use_cached_commits, commits_file)
        if not upstream_commits:
            logger.error("未找到上游提交信息")
            return
        
        scanner = CommitScanner(self.inputs['repo_url'], self.inputs['branch'])
        
        for commit in upstream_commits:
            logger.info(f"处理上游提交: {commit['upstream_sha']}")
            commit_details = scanner.get_commit_details(commit)
            pprint.pprint(commit_details)
            self.inputs.update(commit_details)
            
            # 复用模式1的处理逻辑
            # self.process_single_commit()
    
    def load_cached_commits(self, commits_file):
        """从缓存文件加载commits信息"""
        if not commits_file.exists():
            logger.warning(f"Commits缓存文件不存在: {commits_file}")
            return []
        
        with open(commits_file, 'r') as f:
            return json.load(f)

    def save_commits_cache(self, commits, commits_file):
        """保存commits信息到缓存文件"""
        with open(commits_file, 'w') as f:
            json.dump(commits, f, indent=2)
        logger.info(f"已保存commits信息到: {commits_file}")

    def get_upstream_commits(self, use_cached_commits=False, commits_file=None):
        """获取上游commits信息，支持从缓存或API获取"""
        if use_cached_commits:
            logger.info("从缓存文件加载commits信息")
            return self.load_cached_commits(commits_file)
        
        logger.info("从GitHub API获取commits信息")
        scanner = CommitScanner(self.inputs['repo_url'], self.inputs['branch'])
        commits = scanner.scan_commits()
        
        # 保存到缓存文件
        self.save_commits_cache(commits, commits_file)
        return commits

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