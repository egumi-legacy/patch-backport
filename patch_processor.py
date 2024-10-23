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


class PatchProcessor:
    def __init__(self, input):
        dotenv.load_dotenv()
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
        owner = ref['owner']
        repo = ref['repo']
        ref_field = self.allowed_ref_fields
        for field in ref_field:
            if field in ref:
                ref = ref[field]
                break
        file_contents = []
        for file_path in file_path_list:
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={ref}"
            print("url:", url)
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                logger.error(f"File {file_path} not found in {ref}")
                print("url:", url)
                raise FileNotFoundError(f"File {file_path} not found in {ref}")

            file_data = response.json()
            content = base64.b64decode(file_data['content']).decode('utf-8')
            file_content = {
                'filename': file_path,
                'content': content,
                'sha': file_data['sha']
            }
            file_contents.append(file_content)
        return file_contents


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
        """
        生成两个文件夹之间的差异，类似git diff的输出。
        
        :param folder1: 第一个文件夹的路径
        :param folder2: 第二个文件夹的路径
        :param output_file: 输出差异的文件路径
        :param context_lines: 显示的上下文行数，默认为3
        """
        with open(output_file, 'w', encoding='utf-8') as out_file:
            files1 = set(f.relative_to(folder1) for f in folder1.rglob('*') if f.is_file())
            files2 = set(f.relative_to(folder2) for f in folder2.rglob('*') if f.is_file())
            all_files = files1.union(files2)
            for file in sorted(all_files):
                path1 = folder1 / file
                path2 = folder2 / file
                if not path1.exists():
                    out_file.write(f"新增文件: {file}\n")
                    with open(path2, 'r', encoding='utf-8') as f:
                        out_file.write(f.read())
                elif not path2.exists():
                    out_file.write(f"删除文件: {file}\n")
                    with open(path1, 'r', encoding='utf-8') as f:
                        out_file.write(f.read())
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
                            out_file.write(f"修改文件: {file}\n")
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
                out_file.write('\n' + '=' * 80 + '\n')  # 添加分隔线
        print(f"差异已保存到 {output_file}")

    def write_file_contents(self, file_contents, folder_name):
        # 在patchfile目录下创建一个文件夹，命名为owner_repo，如果存在则跳过
        base_dir = Path('patchfile') / f"{self.owner}_{self.repo}"
        if not base_dir.exists():
            base_dir.mkdir(parents=True)

        for file_content in file_contents:
            file_path = base_dir / folder_name / file_content['filename']
            if not file_path.exists():
                file_path.parent.mkdir(parents=True)
            file_path.write_text(file_content['content'])


    def run(self):
        # 1. 获取commit信息
        commit_info = self.parse_github_url(self.url)
        commit_content = self.get_commit_content(commit_info)
        file_list = self.get_commit_file_list(commit_content)

        base_dir = Path('patchfile') / f"{self.owner}_{self.repo}"
        
        # 2. 解析commit信息
        if not (base_dir / 'newer').exists():
            newer_file_contents = self.get_file_before_commit(commit_info)
            self.write_file_contents(newer_file_contents, 'newer')

        if not (base_dir / self.target_version).exists():
            target_file_contents = self.get_file_contents_from_ref(file_list, self.make_commit_info(tag=self.target_version))
            self.write_file_contents(target_file_contents, self.target_version)

        # 3. 获取两个版本文件的diff并保存
        self.generate_folder_diff(base_dir / 'newer', base_dir / self.target_version, base_dir / 'diff')
        
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
        

