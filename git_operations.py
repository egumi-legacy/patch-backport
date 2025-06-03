import requests
import re
import os
import subprocess
import base64
from pathlib import Path
from loguru import logger
import dotenv
import json
# from patch_evaluator import PatchEvaluator
from patch_utils import download_patch, parse_github_url
from core.parameter_manager import ModuleContext
from typing import Optional, Dict, Any, List


_DEFAULT_COMMITS_FILE = Path(__file__).parent / "commits.json"

class GitOperations:
    def __init__(self, context: Optional[ModuleContext] = None):
        """
        初始化Git操作工具
        
        Args:
            context: 可选的模块上下文对象
        """
        dotenv.load_dotenv()
        self.context = context
        # 根据需要从上下文中获取必要的信息
        if context:
            self.repo_path = context.config.repo_path
            self.github_token = os.getenv('GITHUB_TOKEN')
            self.headers = {
                'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
                'Accept': 'application/json, application/vnd.github+json',
                'Authorization': f'Bearer {self.github_token}',
                'Host': 'api.github.com',
                'Connection': 'keep-alive'
            }
        else:
            # 如果没有提供上下文，使用最小化的配置
            self.github_token = os.getenv('GITHUB_TOKEN')
            self.headers = {
                'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
                'Accept': 'application/json, application/vnd.github+json',
                'Authorization': f'Bearer {self.github_token}',
                'Host': 'api.github.com',
                'Connection': 'keep-alive'
            }
            self.repo_path = None

        # 如果有这个属性，则使用缓存的commits
        if hasattr(context.config, 'use_cached_commits'):
            self.use_cached_commits = context.config.use_cached_commits
        else:
            self.use_cached_commits = False
        if hasattr(context.config, 'commits_file'):
            self.commits_file = context.config.commits_file
        else:
            self.commits_file = _DEFAULT_COMMITS_FILE
        if hasattr(context.config, 'branch'):
            self.branch = context.config.branch
        else:
            self.branch = self.context.config.target_version
        # 可能是模式1的 patch_url，也可能是模式2的 repo_url
        if hasattr(context.config, 'repo_url'):
            self.url = context.config.repo_url
        else:
            self.url = context.config.patch_url
        self.allowed_ref_fields = ['commit_sha', 'tag', 'branch']
        
        self.commit_info = parse_github_url(self.url) if self.url else None
        self.owner = self.commit_info['owner'] if self.commit_info else None
        self.repo = self.commit_info['name'] if self.commit_info else None

        # 如果context有commits_pages_start属性，则使用context的commits_pages_start
        if hasattr(context.config, 'commits_pages_start'):
            self.commits_pages_start = context.config.commits_pages_start
        else:
            self.commits_pages_start = None
        if hasattr(context.config, 'commits_pages_end'):
            self.commits_pages_end = context.config.commits_pages_end
        else:
            self.commits_pages_end = None
        if hasattr(context.config, 'commits_per_page'):
            self.commits_per_page = context.config.commits_per_page
        else:
            self.commits_per_page = None
        
        # if self.commit_info and self.commit_info['commit_sha']:
        #     self.patch_commit_sha = self.commit_info['commit_sha']
        #     # 设置base_dir
        #     self.base_dir = Path('patchfile') / f"{self.owner}_{self.repo}_{self.patch_commit_sha[:6]}"

        #     context.config.update(basedir = self.base_dir)

    def make_commit_info(self, owner = None, repo = None, **kwargs):
        """构建提交信息字典，根据传入的可变参数动态设置键值对"""
        owner = owner if owner else self.owner
        repo = repo if repo else self.repo
        commit_info = {
            'owner': owner,
            'name': repo,
        }
        
        # 从 kwargs 中提取第一个键值对
        if kwargs:
            key, value = next(iter(kwargs.items()))
            if key in self.allowed_ref_fields:
                commit_info[key] = value
            else:
                raise ValueError(f"Invalid field: {key}")
        
        return commit_info

    # def parse_github_url(self, url):
    #     """处理输入可能是patch_url或repo_url的情况"""
    #     # 解析github url，获取owner, repo, commit_sha
    #     pattern = r'https://github\.com/([^/]+)/([^/]+)/commit/([^/]+)'
    #     match = re.search(pattern, url)
    #     if match:
    #         owner, repo, commit_sha = match.groups()
    #         return {'owner': owner, 'repo': repo, 'commit_sha': commit_sha}
    #     else:
    #         pattern = r'https://github\.com/([^/]+)/([^/]+)'
    #         match = re.match(pattern, url)
    #         if not match:
    #             raise ValueError("无效的 GitHub 仓库 URL")
    #         owner, repo = match.groups()
    #         return {'owner': owner, 'repo': repo, 'commit_sha': None}
        

    def get_commit_content(self, commit_info: Dict[str, str]) -> Dict[str, Any]:
        """获取提交内容，优先使用GitHub API，失败则尝试本地Git仓库"""
        # 尝试使用GitHub API获取提交内容
        url = f"https://api.github.com/repos/{commit_info['owner']}/{commit_info['name']}/commits/{commit_info['commit_sha']}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            commit_content = response.json()
            return commit_content
        except requests.exceptions.HTTPError as e:
            logger.warning(f"GitHub API获取提交内容失败: {e.response.status_code}, {e.response.text}")
            logger.info("尝试使用本地Git仓库获取提交内容...")
            return self._get_commit_content_local(commit_info)
        except Exception as e:
            logger.warning(f"GitHub API获取提交内容失败: {e}")
            logger.info("尝试使用本地Git仓库获取提交内容...")
            return self._get_commit_content_local(commit_info)

    def _get_commit_content_local(self, commit_info: Dict[str, str]) -> Dict[str, Any]:
        """使用本地Git仓库获取提交内容"""
        if not self.repo_path:
            logger.error("未设置本地仓库路径，无法使用本地Git操作")
            return {"files": []}
        
        commit_sha = commit_info['commit_sha']
        result = {}
        
        try:
            # 获取提交的文件列表
            files_cmd = subprocess.run(
                ['git', 'show', '--name-status', '--pretty=format:', commit_sha],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # 解析文件列表
            files = []
            for line in files_cmd.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    status, filename = parts[0], parts[-1]
                    
                    # 获取文件的差异
                    try:
                        patch_cmd = subprocess.run(
                            ['git', 'show', '--format=', '-p', f'{commit_sha}', '--', filename],
                            cwd=self.repo_path,
                            capture_output=True,
                            text=True,
                            check=True
                        )
                        patch_content = patch_cmd.stdout
                    except Exception as e:
                        logger.warning(f"获取文件 {filename} 的差异失败: {e}")
                        patch_content = ""
                    
                    files.append({
                        'filename': filename,
                        'status': status,
                        'patch': patch_content,
                        'sha': None  # 本地模式下可能无法获取文件sha
                    })
            
            # 获取父提交信息
            parents_cmd = subprocess.run(
                ['git', 'show', '--pretty=%P', '--no-patch', commit_sha],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            parent_shas = parents_cmd.stdout.strip().split()
            parents = []
            for parent_sha in parent_shas:
                if parent_sha:
                    parents.append({'sha': parent_sha})
            
            # 获取提交信息
            commit_msg_cmd = subprocess.run(
                ['git', 'show', '--pretty=%B', '--no-patch', commit_sha],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # 构建结果
            result = {
                'sha': commit_sha,
                'files': files,
                'parents': parents,
                'commit': {
                    'message': commit_msg_cmd.stdout.strip()
                }
            }
            
            logger.info(f"成功从本地Git仓库获取提交 {commit_sha} 的内容，包含 {len(files)} 个文件")
            return result
            
        except subprocess.CalledProcessError as e:
            logger.error(f"从本地Git仓库获取提交内容失败: {e.stderr}")
            return {"files": []}
        except Exception as e:
            logger.error(f"从本地Git仓库获取提交内容失败: {e}")
            return {"files": []}

    def get_commit_file_list(self, commit_content):
        # 获取commit中的文件列表
        files = commit_content['files']
        file_list = [file['filename'] for file in files]
        return file_list

    def get_file_contents_from_ref(self, file_list: List[str], ref_info: Dict[str, str], local_first: bool = False, local_repo_path: Optional[str] = None) -> List[Dict[str, str]]:
        """获取特定版本的文件内容"""
        results = []
        
        # 如果指定了本地仓库路径且优先使用本地仓库
        if local_first and local_repo_path:
            repo_path = local_repo_path
        elif local_first and not local_repo_path:
            # 使用上下文中的仓库路径（如果有）
            repo_path = self.repo_path
        else:
            repo_path = None
            
        
        logger.info(f"获取内容中：{file_list}")
        if repo_path:
            return self._get_file_contents_local(file_list, ref_info, repo_path)
        else:
            return self._get_file_contents_remote(file_list, ref_info)

    def _get_file_contents_local(self, file_path_list, ref, repo_path):
        """使用本地git仓库获取文件内容"""
        # 从ref中获取引用值（commit_sha/tag/branch）
        for field in self.allowed_ref_fields:
            if field in ref:
                ref_value = ref[field]
                break
        
        file_contents = []
        for file_path in file_path_list:
            logger.info(f"正在从本地仓库获取文件 {file_path} 在 {ref_value} 的内容")
            try:
                # 使用git show命令获取指定版本的文件内容
                result = subprocess.run(
                    ['git', 'show', f'{ref_value}:{file_path}'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                content = {
                    'filename': file_path,
                    'content': result.stdout,
                    'sha': None  # 本地模式下可能不需要sha
                }
                file_contents.append(content)
            except subprocess.CalledProcessError as e:
                logger.warning(f"无法获取文件 {file_path} 在 {ref_value} 的内容: {e.stderr}")
                continue

        logger.info(f"本地获取文件内容为: {file_contents}")
        return file_contents

    def _get_file_contents_remote(self, file_path_list, ref):
        """使用GitHub API获取文件内容（原有的远程获取逻辑）"""
        owner = ref['owner']
        repo = ref['name']
        
        # 从ref中获取引用值
        for field in self.allowed_ref_fields:
            if field in ref:
                ref_value = ref[field]
                break
        
        file_contents = []
        for file_path in file_path_list:
            logger.info(f"正在通过API获取文件 {file_path} 在 {ref_value} 的内容")
            
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
        
        return file_contents
    
    # def get_file_contents_from_ref(self, file_path_list, ref):
    #     """
    #     获取指定引用（tag/commit/branch）下的文件内容
    #     使用多个API端点尝试获取文件内容
    #     """
    #     owner = ref['owner']
    #     repo = ref['repo']
    #     ref_field = self.allowed_ref_fields
        
    #     # 从ref中获取commit_sha, tag, branch其中一个
    #     for field in ref_field:
    #         if field in ref:
    #             ref_value = ref[field]
    #             break
        
    #     file_contents = []
    #     for file_path in file_path_list:
    #         logger.info(f"正在获取文件 {file_path} 在 {ref_value} 的内容")
            
    #         # 方法1: 使用 contents API
    #         content = self._get_file_using_contents_api(owner, repo, file_path, ref_value)
            
    #         # 如果方法1失败，尝试方法2
    #         if content is None:
    #             logger.info(f"使用 contents API 失败，尝试使用 Git Data API")
    #             content = self._get_file_using_git_data_api(owner, repo, file_path, ref_value)
            
    #         if content:
    #             file_contents.append(content)
    #         else:
    #             logger.warning(f"无法获取文件 {file_path} 在 {ref_value} 的内容")
    #             # raise RuntimeError(f"已退出")
        
    #     return file_contents


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
            logger.info(f"-------------commit_sha:{commit_sha}")
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
        """获取提交前的文件内容，处理非GitHub仓库的情况"""
        owner = commit_info['owner']
        repo = commit_info['name']

        commit_content = self.get_commit_content(commit_info)
        changed_files = self.get_commit_file_list(commit_content)
        
        # 检查是否有父提交信息
        if 'parents' not in commit_content or not commit_content['parents']:
            logger.warning("提交内容中没有父提交信息，尝试使用本地Git仓库获取")
            
            if not self.repo_path:
                logger.error("未设置本地仓库路径，无法获取父提交")
                return []
            
            try:
                # 使用git命令获取父提交SHA
                parent_cmd = subprocess.run(
                    ['git', 'show', '--pretty=%P', '--no-patch', commit_info['commit_sha']],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                parent_sha = parent_cmd.stdout.strip().split()[0] if parent_cmd.stdout.strip() else None
                
                if not parent_sha:
                    logger.error(f"无法获取提交 {commit_info['commit_sha']} 的父提交")
                    return []
                
                # 使用本地Git仓库获取文件内容
                file_contents = []
                for file_path in changed_files:
                    try:
                        content_cmd = subprocess.run(
                            ['git', 'show', f'{parent_sha}:{file_path}'],
                            cwd=self.repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if content_cmd.returncode == 0:
                            file_contents.append({
                                'filename': file_path,
                                'content': content_cmd.stdout,
                                'sha': None
                            })
                        else:
                            logger.warning(f"无法获取文件 {file_path} 在父提交 {parent_sha} 的内容")
                    except Exception as e:
                        logger.warning(f"获取文件 {file_path} 内容失败: {e}")
                
                return file_contents
                
            except subprocess.CalledProcessError as e:
                logger.error(f"获取父提交失败: {e.stderr}")
                return []
            except Exception as e:
                logger.error(f"获取父提交失败: {e}")
                return []
        
        # 原有逻辑：使用GitHub API获取父提交的文件内容
        parent_commit_sha = commit_content['parents'][0]['sha']
        parent_commit_info = self.make_commit_info(commit_sha=parent_commit_sha)
        parent_file_contents = self.get_file_contents_from_ref(
            changed_files, 
            parent_commit_info,
            True,
            self.repo_path
            )

        return parent_file_contents
    

    """
    下面主要是模式 2 使用的函数
    """
    def _extract_upstream_commit(self, commit_message):
        """从提交信息中提取上游提交的 SHA"""
        patterns = [
            r'(?i)commit\s+([a-f0-9]+)\s+upstream',           # commit hash upstream
            r'(?i)\[\s*upstream\s+commit\s+([a-f0-9]+)\s*\]', # [upstream commit hash]
            r'(?i)upstream:?\s+([a-f0-9]+)',                  # upstream: hash
            r'(?i)upstream\s+commit:?\s+([a-f0-9]+)',         # upstream commit: hash
            r'(?i)\(upstream\s*(?:commit)?\s*([a-f0-9]+)\)',  # (upstream commit hash)
        ]
        # pattern = r'\[upstream commit ([a-f0-9]+)\]'
        for pattern in patterns:
            match = re.search(pattern, commit_message)
            if match:
                logger.info(f"提取上游提交: {match.group(1)}")
                return match.group(1)
        logger.info(f"未提取到上游提交: {commit_message}")
        return None

    def scan_commits(self, branch, start_page=1, end_page=1, per_page=100):
        """
        扫描提交历史，查找包含上游提交引用的提交
        
        :param branch: 分支名
        :param start_page: 起始页码
        :param end_page: 结束页码
        :param per_page: 每页数量
        :return: 上游提交列表
        """
        if branch is None:
            raise ValueError("branch 为空，无法扫描提交历史")
        
        # 使用配置中的值
        if self.commits_pages_start is not None:
            start_page = self.commits_pages_start
        if self.commits_pages_end is not None:
            end_page = self.commits_pages_end
        if self.commits_per_page is not None:
            per_page = self.commits_per_page
            
        logger.info(f"扫描提交历史: 页码范围={start_page}-{end_page}, 每页={per_page}")
        
        all_upstream_commits = []
        
        # 遍历所有页面
        for page in range(start_page, end_page + 1):
            commits_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/commits"
            params = {
                'sha': branch,
                'per_page': per_page,
                'page': page
            }
            
            try:
                logger.info(f"获取第 {page} 页提交...")
                response = requests.get(commits_url, headers=self.headers, params=params)
                logger.debug(f"请求URL: {response.url}")
                response.raise_for_status()
                commits = response.json()
                
                if not commits:  # 如果返回空列表，说明已经没有更多提交
                    logger.info(f"第 {page} 页没有更多提交")
                    break
                
                # 处理当前页的提交
                for commit in commits:
                    commit_message = commit['commit']['message']
                    upstream_sha = self._extract_upstream_commit(commit_message)
                    if upstream_sha:
                        all_upstream_commits.append({
                            'downstream_sha': commit['sha'],
                            'downstream_message': commit_message,
                            'upstream_sha': upstream_sha
                        })
                
            except requests.exceptions.RequestException as e:
                logger.error(f"获取第 {page} 页提交失败: {e}")
                continue
            
            logger.info(f"第 {page} 页处理完成，当前共找到 {len(all_upstream_commits)} 个上游提交")
        
        return all_upstream_commits

    def get_upstream_commits(self):
        """获取上游提交信息"""
        if self.use_cached_commits and self.commits_file.exists():
            logger.info("从缓存文件加载commits信息")
            with open(self.commits_file, 'r') as f:
                return json.load(f)
        
        # 扫描提交历史
        upstream_commits = self.scan_commits(self.branch)
        
        # 缓存结果
        logger.info("保存commits信息到缓存文件")
        with open(self.commits_file, 'w') as f:
            json.dump(upstream_commits, f, indent=2)
        
        return upstream_commits
    
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
            

    def get_commit_details(self, commit_info):
        return {
            'patch_url': f"https://github.com/{self.owner}/{self.repo}/commit/{commit_info['upstream_sha']}",
            'reference_url': f"https://github.com/{self.owner}/{self.repo}/commit/{commit_info['downstream_sha']}",
            'target_version': self.branch
        }

    # def download_patch_by_type(self, patch_url, patch_type='upstream'):
    #     """
    #     下载并缓存patch文件
    #     """
    #     # 生成缓存文件名
    #     url_hash = patch_url.split('/')[-1][:6]  # 使用commit hash的前8位
    #     cache_name = f"{patch_type}_{url_hash}.patch"
    #     cache_path = self.patch_dir / cache_name
        
    #     return download_patch(patch_url, cache_path, self.use_cached_patches)

    def evaluate_patch_application(self, repo_path, commit_info):
        """评估patch应用效果"""
        from patch_evaluator import PatchEvaluator
        evaluator = PatchEvaluator(repo_path, self.config)

        logger.info(f"upstream_patch: {self.config.patch_url}")
        logger.info(f"downstream_patch: {self.config.reference_url}")
        
        results = evaluator.evaluate_patch(
            upstream_patch_url=self.config.patch_url,
            downstream_patch_url=self.config.reference_url,
            adapted_dir=Path(self.config.basedir) / f"adapted_{self.config.target_version}",
            commit_info=commit_info
        )
        
        return results