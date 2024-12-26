import requests
import re
import dotenv
import pprint
import os
import subprocess
import base64
from pathlib import Path
from llm_assistant import LLMAssistant
from loguru import logger
import difflib
from difflib import SequenceMatcher
from patch_adapter import PatchAdapter
from git_operations import GitOperations
from patch_utils import download_patch


class PatchProcessor:
    def __init__(self, inputs):
        dotenv.load_dotenv()
        self.inputs = inputs
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Accept': 'application/json, application/vnd.github+json',
            'Authorization': f'Bearer {self.github_token}',
            'Host': 'api.github.com',
            'Connection': 'keep-alive'
        }
        self.url = inputs['patch_url']
        self.target_version = inputs['target_version']
        self.git_operations = GitOperations(inputs)
        # self.allowed_ref_fields = ['commit_sha', 'tag', 'branch']
        self.commit_info = self.git_operations.parse_github_url(self.url)
        self.owner = self.commit_info['owner']
        self.repo = self.commit_info['repo']
        if self.commit_info['commit_sha']:
            self.patch_commit_sha = self.commit_info['commit_sha']
        self.base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
        # 设置patch文件存储路径
        self.patch_dir = self.base_dir / 'patches'
        # self.patch_dir.mkdir(exist_ok=True)
        
        # # 评估结果存储路径
        # self.evaluation_dir = self.base_dir / 'evaluations'
        # self.evaluation_dir.mkdir(exist_ok=True)
        inputs.update(basedir = self.base_dir)

        # 缓存设置
        self.use_cached_patches = inputs.get('use_cached_patches', False)


    def download_patch_by_type(self, patch_url, patch_type='upstream'):
        """
        下载patch文件，支持缓存
        
        :param patch_url: patch的URL
        :param patch_type: patch类型 ('upstream' 或 'downstream')
        :return: patch文件路径
        """
        # 生成缓存文件名
        url_hash = patch_url.split('/')[-1][:6]  # 使用commit hash的前6位
        cache_name = f"{patch_type}_{url_hash}.patch"
        cache_path = self.patch_dir / cache_name
        
        return download_patch(patch_url, cache_path, self.use_cached_patches)
        

    def parse_patch(self, patch_content):
        # 解析patch内容
        pass

    def adapt_patch(self, patch_content, target_version):
        # 调整patch以适应目标版本
        pass

    def get_patch_files(self, commit_content):
        patch_files = commit_content['files']
        # patch_message = commit_info['commit']['message']
        patch_contents = []

        for patch_file in patch_files:
            patch_content = {}
            patch_content['filename'] = patch_file['filename']
            patch_content['patch'] = patch_file['patch']
            patch_content['sha'] = patch_file['sha']
            patch_contents.append(patch_content)
        return patch_contents

    def generate_folder_diff(self, folder1, folder2, output_file, context_lines=3):
        # 生成两个文件夹之间的差异，类似git diff的输出。
        # folder1: 新版本文件夹
        # folder2: 目标版本文件夹，通常为旧版本
        with open(output_file, 'w', encoding='utf-8') as out_file:
            files1 = set(f.relative_to(folder1) for f in folder1.rglob('*') if f.is_file())
            files2 = set(f.relative_to(folder2) for f in folder2.rglob('*') if f.is_file())
            all_files = files1.union(files2)
            for file in sorted(all_files):
                path1 = folder1 / file
                path2 = folder2 / file
                if not path1.exists():
                    out_file.write(f"The file does not exist in the new version: {file}\n")
                    # with open(path2, 'r', encoding='utf-8') as f:
                    #     out_file.write(f.read())
                elif not path2.exists():
                    out_file.write(f"The file does not exist in the older (target) version: {file}\n")
                    # with open(path1, 'r', encoding='utf-8') as f:
                    #     out_file.write(f.read())
                else:
                    with open(path1, 'r', encoding='utf-8') as f1, open(path2, 'r', encoding='utf-8') as f2:
                        lines1 = f1.readlines()
                        lines2 = f2.readlines()
                        diff = list(difflib.unified_diff(
                            lines1, lines2,
                            fromfile=str(path1),
                            tofile=str(path2),
                            n=context_lines,
                            lineterm=''
                        ))
                        if diff:
                            out_file.write(f"modified file: {file}\n")
                            in_comment = False
                            for line in diff:
                                if line.strip().startswith('/*'):
                                    in_comment = True
                                if in_comment and '*/' in line:
                                    in_comment = False
                                    continue
                                if not in_comment:
                                    if line.startswith('@@'):
                                        out_file.write(line + '\n')
                                    elif line.startswith(('---', '+++')):
                                        out_file.write(line + '\n')
                                    else:
                                        out_file.write(' ' + line)
                out_file.write('\n' + '"' * 6 + '\n')  # 添加分隔线
        print(f"差异已保存到 {output_file}")

    def write_file_contents(self, file_contents, folder_name):
        # 在patchfile目录下创建一个文件夹，命名为owner_repo_sha[:6]，如果存在则跳过
        base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
        if not base_dir.exists():
            base_dir.mkdir(parents=True)

        for file_content in file_contents:
            file_path = base_dir / folder_name / file_content['filename']
            if not file_path.exists():
                if not file_path.parent.exists():
                    file_path.parent.mkdir(parents=True)
            file_path.write_text(file_content['content'])

    def get_response_path(self):
        """获取响应文件的路径"""
        output_file_name = f"output_{self.inputs['target_version']}_{self.inputs['model']}"
        return self.base_dir / output_file_name

    def save_response_to_project(self, response):
        # 将response写入到project文件夹中
        if response is None:
            return None
        output_path = self.get_response_path()
        # if not output_path.exists():
        #     output_path.parent.mkdir(parents=True)
            
        output_path.write_text(response)
        return output_path

   
    def apply_llm_patch(self, llm_response_path):
        base_dir = self.base_dir
        source_dir = base_dir / f'{self.target_version}'
        output_dir = base_dir / f"adapted_{self.target_version}"

        adapter = PatchAdapter()
        adapter.generate_adapted_file(llm_response_path, source_dir, output_dir)
        

    # def _apply_patch_to_file(self, diff_content, source_file, target_file):
        

    def run(self):
        # 1. 获取commit信息
        commit_info = self.git_operations.parse_github_url(self.url)
        commit_content = self.git_operations.get_commit_content(commit_info)
        file_list = self.git_operations.get_commit_file_list(commit_content)

        # patch_commit_sha只截取前面6位
        base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
        
        # 2. 解析commit信息
        if not (base_dir / 'newer').exists():
            # bug: 如果commit之前的commit没有file_list中的文件，则无法获取到文件内容
            newer_file_contents = self.git_operations.get_file_before_commit(commit_info)
            self.write_file_contents(newer_file_contents, 'newer')

        if not (base_dir / self.target_version).exists():
            # target_file_contents = self.get_file_contents_from_ref(file_list, self.make_commit_info(tag=self.target_version))
            target_file_contents = self.git_operations.get_file_contents_from_ref(file_list, self.git_operations.make_commit_info(branch=self.target_version))
            self.write_file_contents(target_file_contents, self.target_version)

        # 3. 获取两个版本文件的diff并保存
        self.generate_folder_diff(base_dir / 'newer', base_dir / self.target_version, base_dir / 'diff')
        # self.generate_folder_diff(base_dir / self.target_version, base_dir / 'newer', base_dir / 'diff')

        # 4. 获取patch文件
        # 使用curl模块将self.url中的github commit url后加上.patch获取patch文件并写入patch文件夹
        # if not (base_dir / 'patch').exists():
        #     (base_dir / 'patch').mkdir(parents=True)
        
        # if not (base_dir / 'patch' / 'patch.txt').exists():
        #     patch_url = self.url + '.patch'
        #     print(f"patch_url: {patch_url}")
        #     output_file = str(base_dir / 'patch' / f'patch.txt')
        #     # print(f"output_file: {output_file}")
        #     subprocess.run(['curl', '-L', patch_url, '-o', output_file])
        patch_path = self.download_patch_by_type(self.url, 'upstream')
        
        patch_values = [{"patchCode": patch_path, "diffCode": (base_dir / 'diff').read_text()}]


        return dict(prompt_values=patch_values)
        
        

