import requests
import dotenv
import os
from pathlib import Path
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urlparse

def download_patch(patch_url, output_path, use_cached_patches=False):
    """
    下载patch文件，支持缓存和GitHub API
    
    :param patch_url: patch的URL (例如: https://github.com/owner/repo/commit/hash 或 /pull/number)
    :param output_path: 输出路径
    :param use_cached_patches: 是否使用缓存
    :return: patch文件路径
    """
    if use_cached_patches and output_path.exists():
        logger.info(f"使用缓存的patch文件: {output_path}")
        return output_path
    
    # 配置重试策略
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"]  # 明确指定允许的方法
    )
    
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        # 加载GitHub token
        dotenv.load_dotenv()
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            raise ValueError("未设置GITHUB_TOKEN环境变量")

        # 解析URL
        path_parts = urlparse(patch_url).path.strip('/').split('/')
        
        # 设置通用headers
        headers = {
            'Authorization': f'Bearer {github_token}',
            'User-Agent': 'GitHub-Patch-Downloader'
        }
        
        # 设置代理
        proxies = {
            'http': os.getenv('HTTP_PROXY', 'http://127.0.0.1:7890'),
            'https': os.getenv('HTTPS_PROXY', 'http://127.0.0.1:7890')
        }

        # 根据URL类型选择不同的处理方式
        if 'pull' in path_parts:
            # 处理 PR URL
            owner, repo, _, pr_number = path_parts[-4:]
            api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            headers['Accept'] = 'application/vnd.github.v3.patch'
            logger.info(f"使用Pull Request API下载patch: {api_url}")
        elif 'commit' in path_parts:
            # 处理 commit URL
            owner, repo = path_parts[0:2]
            commit_hash = path_parts[-1]
            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_hash}"
            headers['Accept'] = 'application/vnd.github.v3.patch'
            logger.info(f"使用Commit API下载patch: {api_url}")
        else:
            raise ValueError(f"不支持的URL格式: {patch_url}")

        # 发送请求
        response = session.get(
            api_url,
            headers=headers,
            proxies=proxies,
            timeout=30
        )
        response.raise_for_status()

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存patch内容
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"下载patch文件成功: {output_path}")
        return output_path

    except requests.exceptions.RequestException as e:
        logger.error(f"下载patch失败: {str(e)}")
        # 如果API方式失败，尝试直接下载
        try:
            logger.info("尝试直接下载patch文件...")
            direct_url = f"{patch_url}.patch"
            response = session.get(
                direct_url,
                headers={'User-Agent': 'GitHub-Patch-Downloader'},
                proxies=proxies,
                timeout=30
            )
            response.raise_for_status()
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"直接下载patch文件成功: {output_path}")
            return output_path
        except requests.exceptions.RequestException as e:
            logger.error(f"直接下载patch也失败: {str(e)}")
            return None
    except Exception as e:
        logger.error(f"处理过程中出错: {str(e)}")
        return None