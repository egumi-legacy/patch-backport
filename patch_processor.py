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


class PatchProcessor:
    def __init__(self, input):
        dotenv.load_dotenv()
        self.input = input
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Accept': 'application/json, application/vnd.github+json',
            'Authorization': f'Bearer {self.github_token}',
            'Host': 'api.github.com',
            'Connection': 'keep-alive'
        }
        self.url = input['patch_url']
        self.target_version = input['target_version']
        self.allowed_ref_fields = ['commit_sha', 'tag', 'branch']
        self.commit_info = self.parse_github_url(self.url)
        self.owner = self.commit_info['owner']
        self.repo = self.commit_info['repo']
        self.patch_commit_sha = self.commit_info['commit_sha']
        self.base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
        input.update(basedir = self.base_dir)
        

    def make_commit_info(self, owner = None, repo = None, **kwargs):
        # 构建提交信息字典，根据传入的可变参数动态设置键值对
        owner = owner if owner else self.owner
        repo = repo if repo else self.repo
        commit_info = {
            'owner': owner,
            'repo': repo,
        }
        
        # 从 kwargs 中提取第一个键值对
        if kwargs:
            key, value = next(iter(kwargs.items()))
            if key in self.allowed_ref_fields:
                commit_info[key] = value
            else:
                raise ValueError(f"Invalid field: {key}")
        
        return commit_info
    
    def parse_github_url(self, url):
        # 解析github url，获取owner, repo, commit_sha
        pattern = r'https://github\.com/([^/]+)/([^/]+)/commit/([^/]+)'
        match = re.search(pattern, url)
        if match:
            owner, repo, commit_sha = match.groups()
            return {'owner': owner, 'repo': repo, 'commit_sha': commit_sha}
        else:
            raise ValueError("Invalid GitHub URL")

    def get_commit_content(self, commit_info):
        owner = commit_info['owner']
        repo = commit_info['repo']
        commit_sha = commit_info['commit_sha']
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
        response = requests.get(url, headers=self.headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get commit info: {response.status_code} {response.text}")
        return response.json()

    def get_commit_file_list(self, commit_content):
        # 获取commit中的文件列表
        files = commit_content['files']
        file_list = [file['filename'] for file in files]
        return file_list

    def get_file_contents_from_ref(self, file_path_list, ref):
        """
        获取指定引用（tag/commit/branch）下的文件内容
        使用多个API端点尝试获取文件内容
        """
        owner = ref['owner']
        repo = ref['repo']
        ref_field = self.allowed_ref_fields
        
        # 从ref中获取commit_sha, tag, branch其中一个
        for field in ref_field:
            if field in ref:
                ref_value = ref[field]
                break
        
        file_contents = []
        for file_path in file_path_list:
            logger.info(f"正在获取文件 {file_path} 在 {ref_value} 的内容")
            
            # 方法1: 使用 contents API
            content = self._get_file_using_contents_api(owner, repo, file_path, ref_value)
            
            # 如果方法1失败，尝试方法2
            if content is None:
                logger.info(f"使用 contents API 失败，尝试使用 Git Data API")
                content = self._get_file_using_git_data_api(owner, repo, file_path, ref_value)
            
            if content:
                file_contents.append(content)
            else:
                logger.warning(f"无法获取文件 {file_path} 在 {ref_value} 的内容")
                # raise RuntimeError(f"已退出")
        
        return file_contents

    def _get_file_using_contents_api(self, owner, repo, file_path, ref):
        """使用 contents API 获取文件内容"""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
        params = {"ref": ref}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                file_data = response.json()
                content = base64.b64decode(file_data['content']).decode('utf-8')
                return {
                    'filename': file_path,
                    'content': content,
                    'sha': file_data['sha']
                }
        except Exception as e:
            logger.error(f"Contents API 错误: {str(e)}")
        return None

    def _get_file_using_git_data_api(self, owner, repo, file_path, ref):
        """使用 Git Data API 获取文件内容"""
        try:
            # 1. 首先获取引用的commit SHA
            commit_sha = self._get_ref_commit_sha(owner, repo, ref)
            if not commit_sha:
                return None
                
            # 2. 获取commit的树
            tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{commit_sha}?recursive=1"
            tree_response = requests.get(tree_url, headers=self.headers)
            if tree_response.status_code != 200:
                return None
                
            # 3. 在树中查找文件
            tree_data = tree_response.json()
            file_info = next((item for item in tree_data["tree"] 
                             if item["path"] == file_path), None)
            
            if not file_info:
                return None
                
            # 4. 获取文件内容
            blob_url = f"https://api.github.com/repos/{owner}/{repo}/git/blobs/{file_info['sha']}"
            blob_response = requests.get(blob_url, headers=self.headers)
            if blob_response.status_code != 200:
                return None
                
            blob_data = blob_response.json()
            content = base64.b64decode(blob_data['content']).decode('utf-8')
            
            return {
                'filename': file_path,
                'content': content,
                'sha': file_info['sha']
            }
        except Exception as e:
            logger.error(f"Git Data API 错误: {str(e)}")
            return None

    def _get_ref_commit_sha(self, owner, repo, ref):
        """获取引用（tag/branch）对应的commit SHA"""
        try:
            # 首先尝试作为tag获取
            tag_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/tags/{ref}"
            response = requests.get(tag_url, headers=self.headers)
            logger.debug(f"Tag API response status: {response.status_code}")
            
            if response.status_code == 200:
                tag_data = response.json()
                logger.debug(f"Tag data: {tag_data}") 
                
                # 如果返回的是列表
                if isinstance(tag_data, list):
                    # 查找匹配的tag
                    for tag in tag_data:
                        if tag['ref'] == f'refs/tags/{ref}':
                            # 直接返回commit SHA
                            return tag['object']['sha']
                # 如果返回的是单个对象
                else:
                    return tag_data['object']['sha']
                
            # 如果tag获取失败，记录错误
            else:
                logger.error(f"Failed to get tag: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.error(f"获取引用SHA错误: {str(e)}")
        return None

    def get_file_before_commit(self, commit_info):
        owner = commit_info['owner']
        repo = commit_info['repo']

        commit_content = self.get_commit_content(commit_info)
        changed_files = self.get_commit_file_list(commit_content)
        
        # 获取commit之前的commit
        parent_commit_sha = commit_content['parents'][0]['sha']
        parent_commit_info = self.make_commit_info(commit_sha=parent_commit_sha)
        # parent_commit_content = self.get_commit_content(parent_commit_info)
        parent_file_contents = self.get_file_contents_from_ref(changed_files, parent_commit_info)

        return parent_file_contents


    # def get_diff_between_target_version_commits(self, owner, repo, target_version):
    #     # 获取两个commit之间的diff
    #     target_commit = self.get_target_version_commits(owner, repo, target_version)
    #     patch_commit = self.get_commit_info(owner, repo, self.patch_commit_sha)
        
    #     return diff

    # def get_commit_branch(self, commit_info):
    #     # 获取commit所在的branch或tag
    #     owner = commit_info['owner']
    #     repo = commit_info['repo']
    #     commit_sha = commit_info['commit_sha']
    #     url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}/refs"

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


    # def get_diff_between_target_version_and_patch(self, target_version, patch_contents):
    #     # 获取目标版本对应文件与patch文件的diff
    #     # # 使用git diff命令获取diff
    #     # for patch_content in patch_contents:
    #     #     diff = subprocess.check_output(
    #     #         f"git diff {target_version} {patch_content['sha']} -- {patch_content['uri']}",
    #     #         shell=True
    #     #     )
    #     #     patch_content['diff_to_target'] = diff

    #     for patch_content in patch_contents:
    #         file_path = patch_content['uri']
    #         patch_sha = patch_content['sha']
            
    #         # 构建 API 请求 URL
    #         # compare_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/compare/{target_version}...{patch_sha}"
    #         # 通过 API 获取目标版本文件内容
    #         target_file_response = self.get_file_content_from_github(file_path, target_version)
    #         target_file_content = target_file_response['content']
    #         target_file_content = base64.b64decode(target_file_content).decode('utf-8')

    #         # 获取当前文件内容
    #         current_file_response = self.get_file_content_from_github(file_path, patch_sha)
    #         current_file_content = current_file_response['content']
    #         current_file_content = base64.b64decode(current_file_content).decode('utf-8')

    #         # 比较两个文件内容
    #         diff = self.get_diff_between_two_files(target_file_content, current_file_content)
    #         patch_content['diff_to_target'] = diff

    #     return patch_contents
    # def get_diff_between_two_files(self, original_file_contents, target_file_contents):
    #     diffs = []
    #     for original_file_content, target_file_content in zip(original_file_contents, target_file_contents):
    #         if original_file_content['filename'] != target_file_content['filename']:
    #             continue
            
    #         # 使用difflib生成两个文件的diff
    #         diff = difflib.unified_diff(
    #             original_file_content['content'], 
    #             target_file_content['content'],
    #             fromfile = 'original',
    #             tofile = 'target'
    #         )
    #         diffs.append({'filename': original_file_content['filename'], 'diff': ''.join(diff)})
    #     return diffs
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
        output_file_name = f"output_{self.input['target_version']}_{self.input['model']}"
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

    # def apply_llm_patch(self, llm_response_path):
    #     """
    #     将 LLM 生成的 patch 应用到旧版本的源文件
        
    #     :param llm_response_path: LLM 生成的patch内容路径
    #     """
    #     llm_response = llm_response_path.read_text()
    #     logger.info("test--------------")
    #     base_dir = self.base_dir
        
    #     # base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
    #     target_dir = base_dir / self.target_version
    #     output_dir = base_dir / f"adapted_{self.target_version}"
        
    #     # 解析 LLM 响应，提取每个文件的 diff
    #     current_file = None
    #     current_diff = []
    #     files_to_patch = {}
        
    #     for line in llm_response.splitlines():
    #         if line.startswith('diff --git'):
    #             if current_file and current_diff:
    #                 files_to_patch[current_file] = '\n'.join(current_diff)
    #             # 从 diff --git a/path/to/file b/path/to/file 提取文件路径
    #             current_file = line.split(' ')[-1][2:] # 取 b/path/to/file 并去掉 b/
    #             current_diff = []
    #             continue
    #         if line.startswith('index '):
    #             continue
    #         if current_file:
    #             current_diff.append(line)
        
    #     # 添加最后一个文件的 diff
    #     if current_file and current_diff:
    #         files_to_patch[current_file] = '\n'.join(current_diff)
        
    #     # 创建输出目录
    #     if not output_dir.exists():
    #         output_dir.mkdir(parents=True)
        
    #     # 应用修改到每个文件
    #     for file_path, diff_content in files_to_patch.items():
    #         source_file = target_dir / file_path
    #         target_file = output_dir / file_path
            
    #         if not source_file.exists():
    #             logger.error(f"源文件不存在: {source_file}")
    #             continue
                
    #         # 确保目标目录存在
    #         target_file.parent.mkdir(parents=True, exist_ok=True)
            
    #         logger.info(f"diff_content:{diff_content}")
    #         # 应用 diff
    #         try:
    #             self._apply_patch_to_file(diff_content, source_file, target_file)
    #             logger.info(f"成功应用修改到文件: {file_path}")
    #         except Exception as e:
    #             logger.error(f"应用修改到文件 {file_path} 时出错: {str(e)}")
    def apply_llm_patch(self, llm_response_path):
        base_dir = self.base_dir
        source_dir = base_dir / f'{self.target_version}'
        output_dir = base_dir / f"adapted_{self.target_version}"

        adapter = PatchAdapter()
        adapter.generate_adapted_file(llm_response_path, source_dir, output_dir)
        

    # def _apply_patch_to_file(self, diff_content, source_file, target_file):
        

    def run(self):
        # 1. 获取commit信息
        commit_info = self.parse_github_url(self.url)
        commit_content = self.get_commit_content(commit_info)
        file_list = self.get_commit_file_list(commit_content)

        # patch_commit_sha只截取前面6位
        base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
        
        # 2. 解析commit信息
        if not (base_dir / 'newer').exists():
            # bug: 如果commit之前的commit没有file_list中的文件，则无法获取到文件内容
            newer_file_contents = self.get_file_before_commit(commit_info)
            self.write_file_contents(newer_file_contents, 'newer')

        if not (base_dir / self.target_version).exists():
            # target_file_contents = self.get_file_contents_from_ref(file_list, self.make_commit_info(tag=self.target_version))
            target_file_contents = self.get_file_contents_from_ref(file_list, self.make_commit_info(branch=self.target_version))
            self.write_file_contents(target_file_contents, self.target_version)

        # 3. 获取两个版本文件的diff并保存
        self.generate_folder_diff(base_dir / 'newer', base_dir / self.target_version, base_dir / 'diff')
        # self.generate_folder_diff(base_dir / self.target_version, base_dir / 'newer', base_dir / 'diff')

        # 4. 获取patch文件
        # 使用curl模块将self.url中的github commit url后加上.patch获取patch文件并写入patch文件夹
        if not (base_dir / 'patch').exists():
            (base_dir / 'patch').mkdir(parents=True)
        
        if not (base_dir / 'patch' / 'patch.txt').exists():
            patch_url = self.url + '.patch'
            print(f"patch_url: {patch_url}")
            output_file = str(base_dir / 'patch' / f'patch.txt')
            # print(f"output_file: {output_file}")
            subprocess.run(['curl', '-L', patch_url, '-o', output_file])
        
        patch_values = [{"patchCode": (base_dir / 'patch' / f'patch.txt').read_text(), "diffCode": (base_dir / 'diff').read_text()}]


        return dict(prompt_values=patch_values)
        
        # diff_between_two_versions = self.get_diff_between_two_files(original_file_contents, target_file_contents)
        
        # for diff in diff_between_two_versions:
        #     print(diff['filename'])
        #     print(diff['diff'])



        # logger.info('hello------------------------')
        # pprint.pprint(target_file_contents)
        



        # patch_contents = self.get_patch_files(commit_content)
        # print('patch_contents:')
        # pprint.pprint(patch_contents)

        # file_paths = [patch_content['uri'] for patch_content in patch_contents]
        # 3. 获取目标版本对应文件与patch文件的diff
        # patch_contents = self.get_diff_between_target_version_and_patch(self.target_version, patch_contents)
        # print('patch_contents_with_diff:')
        # pprint.pprint(patch_contents)


        
        
        # 3. 调整patch
        # 4. 返回patch  
        

