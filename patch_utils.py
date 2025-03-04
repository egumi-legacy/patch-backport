import requests
import dotenv
import os
from pathlib import Path
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse
import re
import time

# from config_manager import ProjectConfig

# def download_patch_by_type(self, patch_url, patch_type='upstream'):
#     """
#     下载patch文件，支持缓存
    
#     :param patch_url: patch的URL
#     :param patch_type: patch类型 ('upstream' 或 'downstream')
#     :return: patch文件路径
#     """
#     # 生成缓存文件名
#     url_hash = patch_url.split('/')[-1][:6]  # 使用commit hash的前6位
#     cache_name = f"{patch_type}_{url_hash}.patch"
#     cache_path = self.patch_dir / cache_name
    
#     return download_patch(patch_url, cache_path, self.use_cached_patches)
def parse_github_url(url):
    """处理输入可能是patch_url或repo_url的情况"""
    # 解析github url，获取owner, repo, commit_sha
    pattern = r'https://github\.com/([^/]+)/([^/]+)/commit/([^/]+)'
    match = re.search(pattern, url)
    if match:
        owner, repo, commit_sha = match.groups()
        return {'owner': owner, 'repo': repo, 'commit_sha': commit_sha}
    else:
        pattern = r'https://github\.com/([^/]+)/([^/]+)'
        match = re.match(pattern, url)
        if not match:
            raise ValueError("无效的 GitHub 仓库 URL")
        owner, repo = match.groups()
        return {'owner': owner, 'repo': repo, 'commit_sha': None}

def download_patch(patch_url: str, output_path: Path = None) -> Path:
    """
    下载补丁文件
    
    :param patch_url: 补丁URL
    :param output_path: 输出路径
    :param github_token: GitHub令牌
    :return: 保存的文件路径
    """
    # 获取GitHub令牌
    dotenv.load_dotenv()
    github_token = os.getenv('GITHUB_TOKEN')
    headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Accept': 'application/json, application/vnd.github+json',
            'Authorization': f'token {github_token}',
            'Host': 'api.github.com',
            'Connection': 'keep-alive'
        }  
    
    # if github_token:
    #     headers['Authorization'] = f'token {github_token}'
    
    # 确保输出路径存在
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    # else:
    #     # 创建临时文件
    #     timestamp = time.strftime("%Y%m%d_%H%M%S")
    #     output_path = Path(f"temp_patch_{timestamp}.patch")
    
    # 尝试使用GitHub API下载
    try:
        # 解析URL获取owner/repo/commit
        parts = patch_url.split('/')
        logger.info(f"parts: {parts}")
        if len(parts) >= 7 and 'github.com' in patch_url:
            owner = parts[3]
            repo = parts[4]
            commit_sha = parts[6].replace('.patch', '')
            
            # 构建API URL (注意：不要在API URL后面加.patch)
            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
            logger.info(f"使用Commit API下载patch: {api_url}")
            
            # 获取提交详情
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            
            # 获取补丁内容 - 使用Accept头指定格式
            patch_headers = headers.copy()
            patch_headers['Accept'] = 'application/vnd.github.v3.patch'
            patch_response = requests.get(api_url, headers=patch_headers)
            patch_response.raise_for_status()
            
            # 保存到文件
            with open(output_path, 'wb') as f:
                f.write(patch_response.content)
            
            if output_path.exists():
                logger.info(f"下载补丁成功，补丁已保存到: {output_path}")
            return output_path
    
    except Exception as e:
        logger.error(f"下载patch失败: {e}")
    
    # 尝试直接下载patch文件
    try:
        logger.info("尝试直接下载patch文件...")
        
        # 修正URL，确保没有重复的.patch后缀
        direct_url = patch_url
        if direct_url.endswith('.patch.patch'):
            direct_url = direct_url[:-6]  # 移除重复的.patch
        
        response = requests.get(direct_url, headers=headers)
        response.raise_for_status()
        
        # 保存到文件
        with open(output_path, 'wb') as f:
            f.write(response.content)

        if output_path.exists():
            logger.info(f"补丁已保存到: {output_path}")
            return output_path
        else:
            logger.error(f"补丁保存失败: {output_path}")
            raise ValueError(f"补丁保存失败: {output_path}")
    
    except Exception as e:
        logger.error(f"直接下载patch也失败: {e}")
     
    # 所有尝试都失败
    raise ValueError(f"无法下载补丁: {patch_url}")


# def download_patch_by_commit_info(repo_owner: str = None, repo_name: str = None, 
#                   commit_sha: str = None, output_path: Path = None, resource_type: str = 'github') -> Path:
#     if resource_type == 'github':
#         patch_url = f"https://github.com/{repo_owner}/{repo_name}/commit/{commit_sha}.patch"
#         return download_patch(patch_url, output_path)
#     else:
#         raise ValueError(f"不支持的资源类型: {resource_type}")
