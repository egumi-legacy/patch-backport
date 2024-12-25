from pathlib import Path
import requests
import re
from loguru import logger
import os
from loguru import logger
import dotenv

class CommitScanner:
    def __init__(self, repo_url, branch):
        """
        初始化 CommitScanner
        
        :param repo_url: GitHub 仓库URL (例如: "https://github.com/gregkh/linux")
        :param branch: 分支名称 (例如: "linux-6.12.y")
        """
        self.repo_url = repo_url
        self.branch = branch
        self.git_ops = GitOperations()
        self.commit_info = self.git_ops.parse_github_url(self.repo_url)
        self.owner = self.commit_info['owner']
        self.repo = self.commit_info['repo']
        # dotenv.load_dotenv()
        # self.repo_url = repo_url
        # self.branch = branch
        # self.github_token = os.getenv('GITHUB_TOKEN')
        # print(f"github_token: {self.github_token}")
        # self.headers = {
        #     'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
        #     'Accept': 'application/json, application/vnd.github+json',
        #     'Authorization': f'token {self.github_token}',
        #     'Host': 'api.github.com',
        #     'Connection': 'keep-alive'
        # }
        
        # # 解析仓库信息
        # pattern = r'https://github\.com/([^/]+)/([^/]+)'
        # match = re.match(pattern, repo_url)
        # if not match:
        #     raise ValueError("无效的 GitHub 仓库 URL")
        # self.owner, self.repo = match.groups()

    def scan_commits(self, page=1, per_page=100):
        """扫描提交历史，查找包含上游提交引用的提交"""
        commits_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/commits"
        # https://api.github.com/repos/gregkh/linux/commits?sha=linux-6.12.y&page=1&per_page=100
        # https://api.github.com/repos/gregkh/linux/commits?sha=linux-6.12.y&per_page=100&page=1
        params = {
            'sha': self.branch,
            'per_page': per_page,
            'page': page
        }
        
        try:
            response = requests.get(commits_url, headers=self.headers, params=params)
            print(f"request url:{response.url}")
            response.raise_for_status()
            commits = response.json()
            upstream_commits = []
            for commit in commits:
                commit_message = commit['commit']['message']
                upstream_sha = self._extract_upstream_commit(commit_message)
                if upstream_sha:
                    upstream_commits.append({
                        'downstream_sha': commit['sha'],
                        'downstream_message': commit_message,
                        'upstream_sha': upstream_sha
                    })
            
            return upstream_commits
            
        except requests.exceptions.RequestException as e:
            logger.error(f"获取提交历史失败: {e}")
            return []

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

    def get_commit_details(self, commit_info):
        """
        获取上游提交和下游提交的详细信息
        
        :param commit_info: 包含 upstream_sha 和 downstream_sha 的字典
        :return: 包含补丁URL和其他相关信息的字典
        """
        return {
            'patch_url': f"https://github.com/torvalds/linux/commit/{commit_info['upstream_sha']}",
            'reference_url': f"https://github.com/{self.owner}/{self.repo}/commit/{commit_info['downstream_sha']}",
            'target_version': self.branch
        }
