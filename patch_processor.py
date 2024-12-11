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

    def apply_llm_patch(self, llm_response_path):
        """
        将 LLM 生成的 patch 应用到旧版本的源文件
        
        :param llm_response_path: LLM 生成的响应内容路径
        """
        llm_response = llm_response_path.read_text()
        logger.info("test--------------")
        
        base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"
        target_dir = base_dir / self.target_version
        output_dir = base_dir / f"adapted_{self.target_version}"
        
        # 解析 LLM 响应，提取每个文件的 diff
        current_file = None
        current_diff = []
        files_to_patch = {}
        
        for line in llm_response.splitlines():
            if line.startswith('diff --git'):
                if current_file and current_diff:
                    files_to_patch[current_file] = '\n'.join(current_diff)
                # 从 diff --git a/path/to/file b/path/to/file 提取文件路径
                current_file = line.split(' ')[-1][2:] # 取 b/path/to/file 并去掉 b/
                current_diff = []
                continue
            if line.startswith('index '):
                continue
            if current_file:
                current_diff.append(line)
        
        # 添加最后一个文件的 diff
        if current_file and current_diff:
            files_to_patch[current_file] = '\n'.join(current_diff)
        
        # 创建输出目录
        if not output_dir.exists():
            output_dir.mkdir(parents=True)
        
        # 应用修改到每个文件
        for file_path, diff_content in files_to_patch.items():
            source_file = target_dir / file_path
            target_file = output_dir / file_path
            
            if not source_file.exists():
                logger.error(f"源文件不存在: {source_file}")
                continue
                
            # 确保目标目录存在
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 应用 diff
            try:
                self._apply_patch_to_file(diff_content, source_file, target_file)
                logger.info(f"成功应用修改到文件: {file_path}")
            except Exception as e:
                logger.error(f"应用修改到文件 {file_path} 时出错: {str(e)}")

    def _apply_patch_to_file(self, diff_content, source_file, target_file):
        """Enhanced patch application with structural validation"""
        def find_function_definition(lines, func_name):
            """Find the exact function definition with more flexible matching"""
            # 更灵活的函数定义模式，允许多行定义
            pattern = re.compile(rf'^(?:static\s+)?(?:int|void|char\s*\*)\s+{re.escape(func_name)}\s*\(.*?(?:\)|\n)')
            
            for i, line in enumerate(lines):
                if pattern.match(line.strip()):
                    # 如果函数定义跨多行，找到完整定义
                    if not line.strip().endswith(')'):
                        bracket_count = line.count('(') - line.count(')')
                        j = i + 1
                        while j < len(lines) and bracket_count > 0:
                            bracket_count += lines[j].count('(') - lines[j].count(')')
                            j += 1
                        if bracket_count == 0:
                            return i
                    else:
                        return i
            return None

        def find_function_bounds(lines, start_line):
            """Find function bounds with improved bracket matching"""
            if start_line is None:
                return None, None
            
            # 从函数定义开始查找开括号
            bracket_count = 0
            found_opening = False
            current_line = start_line
            
            # 首先找到函数定义结束和开括号
            while current_line < len(lines):
                line = lines[current_line]
                # 计算当前行的括号
                bracket_count += line.count('{') - line.count('}')
                
                if '{' in line:
                    found_opening = True
                    break
                    
                current_line += 1
                
                # 如果搜索太远还没找到开括号，可能是出错了
                if current_line - start_line > 10:  # 设置合理的搜索范围
                    return None, None
            
            if not found_opening:
                return None, None
            
            # 继续查找直到找到匹配的闭括号
            for i in range(current_line + 1, len(lines)):
                bracket_count += lines[i].count('{') - lines[i].count('}')
                if bracket_count == 0:
                    return start_line, i
            
            return None, None

        def validate_structure(lines):
            """Validate basic code structure"""
            bracket_count = 0
            for line in lines:
                bracket_count += line.count('{') - line.count('}')
            return bracket_count == 0

        with open(source_file, 'r', encoding='utf-8') as f:
            original_lines = f.readlines()

        # Parse hunks and group by function
        function_changes = {}
        for hunk in self._parse_hunks(diff_content):
            if hunk['function']:
                # 提取函数名，处理可能的函数签名变化
                func_match = re.search(r'\b(\w+)\s*\(', hunk['function'])
                if func_match:
                    func_name = func_match.group(1)
                    if func_name not in function_changes:
                        function_changes[func_name] = []
                    function_changes[func_name].append(hunk)
                    logger.debug(f"Found changes for function: {func_name}")

        # Apply changes function by function
        new_lines = original_lines[:]
        modified = False
        
        for func_name, hunks in function_changes.items():
            logger.debug(f"Processing function: {func_name}")
            
            # Find function definition
            func_start = find_function_definition(new_lines, func_name)
            if func_start is None:
                logger.error(f"Could not find function definition: {func_name}")
                continue
            
            # Find function bounds
            start, end = find_function_bounds(new_lines, func_start)
            if start is None:
                logger.error(f"Could not find function bounds: {func_name}")
                continue

            logger.debug(f"Found function {func_name} from line {start} to {end}")

            # Apply changes within function bounds
            function_lines = new_lines[start:end + 1]
            modified_lines = self._apply_changes_to_function(
                function_lines,
                hunks,
                func_name
            )

            # Validate and replace
            if validate_structure(modified_lines):
                if modified_lines != function_lines:  # 只有在实际有修改时才替换
                    new_lines[start:end + 1] = modified_lines
                    modified = True
                    logger.info(f"Successfully modified function: {func_name}")
            else:
                logger.error(f"Invalid structure after modifying {func_name}")

        # Only write if there were actual modifications
        if modified:
            with open(target_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            logger.info(f"Successfully wrote changes to {target_file}")
        else:
            logger.warning("No modifications were made to the file")

    def _apply_changes_to_function(self, function_lines, hunks, func_name):
        """Apply changes to a single function with enhanced content matching"""
        modified_lines = function_lines[:]
        
        for hunk in hunks:
            # 使用更灵活的内容匹配
            position = self._find_best_match_position(
                modified_lines,
                hunk['context_before'],
                hunk['context_after'],
                threshold=0.7  # 降低阈值以允许更多的近似匹配
            )
            
            if position is not None:
                # Create backup
                backup_lines = modified_lines[:]
                
                try:
                    self._apply_hunk_changes(
                        modified_lines,
                        position,
                        hunk['removed_lines'],
                        hunk['added_lines'],
                        similarity_threshold=0.7  # 降低相似度要求
                    )
                    
                    # 验证修改后的代码结构
                    if not self._validate_function_structure(modified_lines):
                        logger.warning(f"Invalid structure after changes in {func_name}, rolling back")
                        modified_lines = backup_lines
                except Exception as e:
                    logger.error(f"Error applying changes to {func_name}: {str(e)}")
                    modified_lines = backup_lines
        
        return modified_lines

    def _parse_hunks(self, diff_content):
        """解析 diff 内容，提取每个 hunk 的上下文和修改内容"""
        hunks = []
        current_hunk = None
        
        # 用于跟踪当前正在处理的函数
        current_function = None
        
        for line in diff_content.splitlines():
            # 检测函数定义
            if re.match(r'^[+-]?\s*(?:static\s+)?(?:int|void|char\s*\*)\s+\w+\s*\(', line):
                current_function = line.strip()
                if current_function.startswith(('+', '-')):
                    current_function = current_function[1:]
            
            # 跳过文件头
            if line.startswith(('---', '+++', 'index', 'diff --git')):
                continue
            
            # 新的 hunk 开始
            if line.startswith('@@'):
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {
                    'function': current_function,
                    'content': line + '\n',
                    'context_before': [],
                    'context_after': [],
                    'removed_lines': [],
                    'added_lines': [],
                    'in_change': False
                }
                continue
            
            if not current_hunk:
                continue
            
            current_hunk['content'] += line + '\n'
            
            if line.startswith(' '):
                if current_hunk['in_change']:
                    current_hunk['context_after'].append(line[1:])
                else:
                    current_hunk['context_before'].append(line[1:])
            elif line.startswith('-'):
                current_hunk['in_change'] = True
                current_hunk['removed_lines'].append(line[1:])
            elif line.startswith('+'):
                current_hunk['in_change'] = True
                current_hunk['added_lines'].append(line[1:])
        
        if current_hunk:
            hunks.append(current_hunk)
        
        return hunks

    def _find_best_match_position(self, context_before, context_after, file_lines, 
                                context_size=3, threshold=0.8):
        """
        使用上下文匹配找到最佳修改位置
        
        :param context_before: 修改前的上下文行
        :param context_after: 修改后的上下文行
        :param file_lines: 文件的所有行
        :param context_size: 匹配的上下文大小
        :param threshold: 匹配度阈值
        :return: 最佳匹配位置，如果没有找到好的匹配则返回 None
        """
        if not context_before and not context_after:
            return None
            
        best_match_score = 0
        best_position = None
        
        # 构建上下文匹配字符串
        context_str = ''.join(context_before + context_after)
        
        # 在文件中滑动窗口寻找最佳匹配
        for i in range(len(file_lines) - len(context_before + context_after) + 1):
            window = file_lines[i:i + len(context_before + context_after)]
            window_str = ''.join(window)
            
            # 计算匹配度
            matcher = SequenceMatcher(None, context_str, window_str)
            score = matcher.ratio()
            
            if score > best_match_score:
                best_match_score = score
                best_position = i + len(context_before)
        
        # 如果最佳匹配超过阈值，返回位置
        if best_match_score >= threshold:
            return best_position
        
        # 如果没有找到好的匹配，尝试只匹配前后文的一部分
        if len(context_before) > context_size:
            context_before = context_before[-context_size:]
        if len(context_after) > context_size:
            context_after = context_after[:context_size]
            
        return self._find_best_match_position(context_before, context_after, 
                                            file_lines, context_size, threshold - 0.1)

    def _apply_hunk_changes(self, lines, position, removed_lines, added_lines, similarity_threshold=0.7):
        """Apply changes with more flexible matching"""
        # 获取实际要修改的行
        actual_lines = lines[position:position + len(removed_lines)]
        
        # 使用更灵活的内容匹配
        if self._lines_match(actual_lines, removed_lines, threshold=similarity_threshold):
            # 删除旧行
            del lines[position:position + len(removed_lines)]
            # 插入新行
            for i, line in enumerate(added_lines):
                if not line.endswith('\n'):
                    line += '\n'
                lines.insert(position + i, line)
        else:
            logger.warning(f"Content mismatch. Expected:\n{''.join(removed_lines)}\nActual:\n{''.join(actual_lines)}")
            # 强制应用修改，但保留日志
            del lines[position:position + len(removed_lines)]
            for i, line in enumerate(added_lines):
                if not line.endswith('\n'):
                    line += '\n'
                lines.insert(position + i, line)

    def _lines_match(self, lines1, lines2, threshold=0.8):
        """
        检查两组行是否匹配
        
        :param lines1: 第一组行
        :param lines2: 第二组行
        :param threshold: 匹配度阈值
        :return: 是否匹配
        """
        if not lines1 or not lines2:
            return False
            
        text1 = ''.join(lines1)
        text2 = ''.join(lines2)
        
        matcher = SequenceMatcher(None, text1, text2)
        return matcher.ratio() >= threshold

    def _find_anchor_points(self, context_lines):
        """
        在上下文中找到可以作为锚点的唯一可识别点
        返回一个 (pattern, type) 元组列表
        """
        anchors = []
        
        for line in context_lines:
            # 查找函数调用
            if re.search(r'\w+\([^)]*\)', line):
                func_call = re.search(r'(\w+\([^)]*\))', line).group(1)
                anchors.append((func_call, 'function_call'))
            
            # 查找控制结构
            elif any(keyword in line for keyword in ['if', 'for', 'while', 'switch', 'return']):
                control = line.strip()
                anchors.append((control, 'control_structure'))
            
            # 查找变量声明
            elif re.search(r'^\s*\w+\s+\w+\s*[=;]', line):
                declaration = line.strip()
                anchors.append((declaration, 'declaration'))
        
        return anchors

    def _find_position_with_anchors(self, lines, context_before, context_after, anchors):
        """
        使用锚点和上下文找到最佳修改位置
        """
        best_position = None
        best_score = 0
        
        # 如果有锚点，首先尝试使用锚点定位
        for anchor, anchor_type in anchors:
            for i, line in enumerate(lines):
                if anchor in line:
                    # 验证周围上下文
                    context_score = self._verify_surrounding_context(
                        lines, i, context_before, context_after
                    )
                    if context_score > best_score:
                        best_score = context_score
                        best_position = i
        
        # 如果没有找到好的锚点匹配，回退到普通上下文匹配
        if best_score < 0.8:
            best_position = self._find_best_match_position(
                context_before, context_after, lines
            )
        
        return best_position

    def _verify_surrounding_context(self, lines, position, context_before, context_after, 
                                  context_size=3):
        """
        验证给定位置周围的上下文匹配程度
        返回0-1之间的匹配分数
        """
        start = max(0, position - len(context_before))
        end = min(len(lines), position + len(context_after))
        
        # 获取实际上下文
        actual_context = lines[start:end]
        expected_context = context_before + context_after
        
        # 使用序列匹配计算相似度
        matcher = SequenceMatcher(None, 
                                ''.join(actual_context), 
                                ''.join(expected_context))
        return matcher.ratio()

    def _validate_function_structure(self, lines):
        """
        验证函数结构的完整性
        检查括号匹配、基本语法等
        """
        # 检查括号平衡
        bracket_count = 0
        for line in lines:
            bracket_count += line.count('{') - line.count('}')
            # 括号数不能小于0
            if bracket_count < 0:
                return False
        
        # 最终括号应该平衡
        if bracket_count != 0:
            return False
        
        # 检查基本语法结构
        for line in lines:
            # 检查未闭合的字符串
            if line.count('"') % 2 != 0:
                return False
            
            # 检查分号结尾（忽略预处理指令、花括号行等）
            stripped = line.strip()
            if (stripped and 
                not stripped.startswith('#') and 
                not stripped.endswith('{') and 
                not stripped.endswith('}') and 
                not stripped.endswith(';')):
                return False
        
        return True

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
            target_file_contents = self.get_file_contents_from_ref(file_list, self.make_commit_info(tag=self.target_version))
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
            output_file = str(base_dir / 'patch' / 'patch.txt')
            # print(f"output_file: {output_file}")
            subprocess.run(['curl', '-L', patch_url, '-o', output_file])
        
        patch_values = [{"patchCode": (base_dir / 'patch' / 'patch.txt').read_text(), "diffCode": (base_dir / 'diff').read_text()}]


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
        

