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
import subprocess

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
def parse_repo_url(url):
    """
    从不同格式的仓库URL中解析owner和name信息，并提供正确的克隆URL
    
    支持的格式:
    - GitHub: https://github.com/owner/repo
    - Gitee: https://gitee.com/owner/repo
    - GitLab: https://gitlab.com/owner/repo
    - SourceForge: https://sourceforge.net/p/project/repo
    
    Args:
        url: 仓库URL
        
    Returns:
        包含owner、name、commit_sha和clone_url的字典
    """
    result = {'owner': '', 'name': '', 'commit_sha': None, 'clone_url': ''}
    
    # 标准化URL
    normalized_url = url.rstrip('/')
    
    # GitHub commit格式
    github_pattern = r'https://github\.com/([^/]+)/([^/]+)/commit/([^/]+)'
    match = re.search(github_pattern, normalized_url)
    if match:
        owner, repo, commit_sha = match.groups()
        result['owner'] = owner
        result['name'] = repo.replace('.git', '')
        result['commit_sha'] = commit_sha
        result['clone_url'] = f"https://github.com/{owner}/{repo}.git"
        return result
    
    # Gitee commit格式
    gitee_pattern = r'https://gitee\.com/([^/]+)/([^/]+)/commit/([^/]+)'
    match = re.search(gitee_pattern, normalized_url)
    if match:
        owner, repo, commit_sha = match.groups()
        result['owner'] = owner
        result['name'] = repo.replace('.git', '')
        result['commit_sha'] = commit_sha
        result['clone_url'] = f"https://gitee.com/{owner}/{repo}.git"
        return result
    
    # GitLab commit格式
    gitlab_pattern = r'https://gitlab\.com/([^/]+)/([^/]+)/-/commit/([^/]+)'
    match = re.search(gitlab_pattern, normalized_url)
    if match:
        owner, repo, commit_sha = match.groups()
        result['owner'] = owner
        result['name'] = repo.replace('.git', '')
        result['commit_sha'] = commit_sha
        result['clone_url'] = f"https://gitlab.com/{owner}/{repo}.git"
        return result
    
    # SourceForge commit格式 - 注意：第一部分是项目名，第二部分是仓库名
    sourceforge_pattern = r'https://sourceforge\.net/p/([^/]+)/([^/]+)/ci/([^/]+)'
    match = re.search(sourceforge_pattern, normalized_url)
    if match:
        project, repo, commit_sha = match.groups()
        result['owner'] = project  # 项目名作为owner
        result['name'] = repo      # 仓库名
        result['commit_sha'] = commit_sha
        result['clone_url'] = f"https://git.code.sf.net/p/{project}/{repo}"
        return result
    
    # GitHub仓库格式
    github_repo_pattern = r'https://github\.com/([^/]+)/([^/]+)'
    match = re.match(github_repo_pattern, normalized_url)
    if match:
        owner, repo = match.groups()
        result['owner'] = owner
        result['name'] = repo.replace('.git', '')
        result['clone_url'] = f"https://github.com/{owner}/{repo}.git"
        return result
    
    # Gitee仓库格式
    gitee_repo_pattern = r'https://gitee\.com/([^/]+)/([^/]+)'
    match = re.match(gitee_repo_pattern, normalized_url)
    if match:
        owner, repo = match.groups()
        result['owner'] = owner
        result['name'] = repo.replace('.git', '')
        result['clone_url'] = f"https://gitee.com/{owner}/{repo}.git"
        return result
    
    # GitLab仓库格式
    gitlab_repo_pattern = r'https://gitlab\.com/([^/]+)/([^/]+)'
    match = re.match(gitlab_repo_pattern, normalized_url)
    if match:
        owner, repo = match.groups()
        result['owner'] = owner
        result['name'] = repo.replace('.git', '')
        result['clone_url'] = f"https://gitlab.com/{owner}/{repo}.git"
        return result
    
    # SourceForge仓库格式 - 注意：第一部分是项目名，第二部分是仓库名
    sourceforge_repo_pattern = r'https://sourceforge\.net/p/([^/]+)/([^/]+)'
    match = re.search(sourceforge_repo_pattern, normalized_url)
    if match:
        project, repo = match.groups()
        result['owner'] = project  # 项目名作为owner
        result['name'] = repo      # 仓库名
        
        # SourceForge的克隆URL格式
        result['clone_url'] = f"https://git.code.sf.net/p/{project}/{repo}"
        return result
    
    # 简单的SourceForge项目URL - 只有项目名，没有明确的仓库名
    simple_sf_pattern = r'https://sourceforge\.net/p/([^/]+)/?$'
    match = re.search(simple_sf_pattern, normalized_url)
    if match:
        project = match.group(1)
        result['owner'] = project
        result['name'] = 'code'  # 默认仓库名
        result['clone_url'] = f"https://git.code.sf.net/p/{project}/code"
        return result
    
    raise ValueError("无效的仓库 URL")

# 保持向后兼容性
def parse_github_url(url):
    """处理输入可能是patch_url或repo_url的情况，支持GitHub和Gitee"""
    try:
        return parse_repo_url(url)
    except ValueError:
        raise ValueError("无效的 GitHub 或 Gitee 仓库 URL")

def download_patch(patch_url: str, output_path: Path = None) -> Path:
    """
    下载补丁文件，支持多种代码托管平台
    
    :param patch_url: 补丁URL
    :param output_path: 输出路径
    :return: 保存的文件路径
    """
    # 获取GitHub令牌
    dotenv.load_dotenv()
    github_token = os.getenv('GITHUB_TOKEN')
    headers = {
        'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
        'Accept': 'application/json, application/vnd.github+json',
        'Connection': 'keep-alive'
    }
    
    if github_token and 'github.com' in patch_url:
        headers['Authorization'] = f'token {github_token}'
        headers['Host'] = 'api.github.com'
    
    # 确保输出路径存在
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # 创建临时文件
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"temp_patch_{timestamp}.patch")
    
    # 根据URL类型选择下载方法
    if 'github.com' in patch_url:
        return _download_github_patch(patch_url, output_path, headers)
    elif 'gitee.com' in patch_url:
        return _download_direct_patch(patch_url, output_path, headers)
    elif 'gitlab.com' in patch_url:
        return _download_gitlab_patch(patch_url, output_path, headers)
    elif 'sourceforge.net' in patch_url:
        # 检查是否包含ci/，表示这是一个提交URL
        if '/ci/' in patch_url:
            return _download_sourceforge_patch(patch_url, output_path, headers)
        else:
            logger.error(f"SourceForge URL必须包含具体的提交路径 (/ci/): {patch_url}")
            raise ValueError(f"SourceForge URL必须包含具体的提交路径 (/ci/): {patch_url}")
    else:
        # 默认尝试直接下载
        return _download_direct_patch(patch_url, output_path, headers)

def _download_github_patch(patch_url: str, output_path: Path, headers: dict) -> Path:
    """下载GitHub补丁，优先使用API"""
    try:
        # 解析URL获取owner/repo/commit
        parts = patch_url.split('/')
        logger.info(f"GitHub patch URL parts: {parts}")
        if len(parts) >= 7:
            owner = parts[3]
            repo = parts[4]
            commit_sha = parts[6].replace('.patch', '')
            
            # 构建API URL (注意：不要在API URL后面加.patch)
            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
            logger.info(f"使用GitHub Commit API下载patch: {api_url}")
            
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
                logger.info(f"下载GitHub补丁成功，补丁已保存到: {output_path}")
                return output_path
    except Exception as e:
        logger.error(f"使用GitHub API下载patch失败: {e}")
    
    # 如果API下载失败，尝试直接下载
    return _download_direct_patch(patch_url, output_path, headers)

def _download_gitlab_patch(patch_url: str, output_path: Path, headers: dict) -> Path:
    """下载GitLab补丁"""
    try:
        # 确保URL以.patch结尾
        if not patch_url.endswith('.patch'):
            if '/-/commit/' in patch_url:
                patch_url = patch_url + '.patch'
            else:
                logger.error(f"无效的GitLab补丁URL格式: {patch_url}")
                raise ValueError(f"无效的GitLab补丁URL格式: {patch_url}")
        
        logger.info(f"下载GitLab补丁: {patch_url}")
        return _download_direct_patch(patch_url, output_path, headers)
    except Exception as e:
        logger.error(f"下载GitLab补丁失败: {e}")
        raise

def _download_sourceforge_patch(patch_url: str, output_path: Path, headers: dict) -> Path:
    """
    下载SourceForge特定commit的patch内容。
    (Downloads the patch content for a specific SourceForge commit.)

    Args:
        patch_url (str): SourceForge commit页面的URL. 
                         (The URL of the SourceForge commit page.)
                         Example: "https://sourceforge.net/p/mcj/fig2dev/ci/c8a87d22036e62bac0c6f7836078d8103caa6457/"
        output_path (Path): 下载的patch文件保存路径。
                            (The path where the downloaded patch file will be saved.)
        headers (dict): 用于HTTP请求的headers。
                        (Headers to use for the HTTP request.)

    Returns:
        Path: 指向已下载patch文件的路径。
              (Path to the downloaded patch file.)

    Raises:
        ValueError: 如果无法解析SourceForge URL。
                    (If the SourceForge URL cannot be parsed.)
        requests.exceptions.RequestException: 如果下载过程中发生网络错误。
                                            (If a network error occurs during download.)
        Exception: 其他处理过程中发生的错误。
                   (For other errors during processing.)
    """
    try:
        # 从URL中提取基础commit URL部分
        # (Extract the base commit URL part from the input URL)
        # Regex to capture the main commit URL, e.g., "https://sourceforge.net/p/project/repo/ci/commit_hash"
        # It handles an optional trailing slash.
        sf_pattern = r'(https://sourceforge\.net/p/[^/]+/[^/]+/ci/[^/]+)/?'
        match = re.search(sf_pattern, patch_url)
        
        if not match:
            logger.error(f"无法解析SourceForge URL (Invalid SourceForge URL format): {patch_url}")
            raise ValueError(f"无法解析SourceForge URL (Invalid SourceForge URL format): {patch_url}")
            
        base_commit_url = match.group(1).rstrip('/') # 获取捕获组并移除末尾斜杠 (Get the captured group and remove trailing slash)
        
        # 尝试从base_commit_url中提取项目、仓库和提交SHA，主要用于日志记录
        # (Attempt to extract project, repo, and commit SHA from base_commit_url, mainly for logging)
        project, repo, commit_sha = "unknown", "unknown", "unknown"
        detailed_match = re.search(r'https://sourceforge\.net/p/([^/]+)/([^/]+)/ci/([^/]+)', base_commit_url)
        if detailed_match:
            project, repo, commit_sha = detailed_match.groups()
        
        logger.info(f"解析SourceForge URL: 项目(Project)={project}, 仓库(Repo)={repo}, 提交(Commit)={commit_sha}")
        logger.info(f"基础Commit URL (Base Commit URL): {base_commit_url}")
        
        # 构建统一diff视图的URL (Construct the URL for the unified diff view)
        # This specific URL format provides the raw diff text.
        diff_url = f"{base_commit_url}/diff/?diff_format=u"
        logger.info(f"尝试从以下URL下载diff (Attempting to download diff from): {diff_url}")
        
        # 发起HTTP GET请求下载diff内容 (Make an HTTP GET request to download the diff content)
        response = requests.get(diff_url, headers=headers, timeout=30) # Added timeout
        response.raise_for_status()  # 如果HTTP状态码表示错误，则抛出HTTPError (Raises HTTPError for bad responses (4XX or 5XX))
        
        patch_content = response.text
        
        if not patch_content.strip():
            logger.warning(f"下载的diff内容为空 (Downloaded diff content is empty from): {diff_url}")
            # 根据需求，这里可以选择抛出错误或创建一个空的patch文件
            # (Depending on requirements, you might choose to raise an error here or create an empty patch file)

        # 将diff内容写入输出文件 (Write the diff content to the output file)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(patch_content)
        
        logger.info(f"SourceForge补丁已成功下载并保存到 (SourceForge patch successfully downloaded and saved to): {output_path}")
        return output_path
        
    except requests.exceptions.Timeout:
        logger.error(f"下载SourceForge补丁超时 (Timeout while downloading SourceForge patch from URL): {diff_url if 'diff_url' in locals() else patch_url}")
        # _write_error_placeholder(output_path, patch_url, diff_url if 'diff_url' in locals() else 'N/A', "Request timed out.")
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"下载SourceForge补丁时发生HTTP错误 (HTTP error while downloading SourceForge patch): {e.response.status_code} {e.response.reason} from {e.request.url}")
        # _write_error_placeholder(output_path, patch_url, e.request.url, f"HTTP Error: {e.response.status_code} {e.response.reason}")
        raise
    except requests.exceptions.RequestException as e:
        # 处理其他网络相关的错误 (Handle other network-related errors)
        logger.error(f"下载SourceForge补丁时发生网络错误 (Network error while downloading SourceForge patch): {e}")
        # _write_error_placeholder(output_path, patch_url, diff_url if 'diff_url' in locals() else 'N/A', str(e))
        raise 
    except Exception as e:
        # 处理其他所有潜在错误 (Handle any other potential errors)
        logger.error(f"处理SourceForge补丁失败 (Failed to process SourceForge patch): {e}", exc_info=True)
        # exc_info=True 会记录堆栈跟踪 (exc_info=True will log the stack trace)
        # _write_error_placeholder(output_path, patch_url, diff_url if 'diff_url' in locals() else 'N/A', f"An unexpected error occurred: {str(e)}")
        raise

# def _write_error_placeholder(output_path: Path, original_url: str, attempted_url: str, error_message: str):
#     """辅助函数，用于在发生错误时写入占位/错误文件。"""
#     """Helper function to write a placeholder/error file when an error occurs."""
#     try:
#         with open(output_path, 'w', encoding='utf-8') as f:
#             f.write(f"# SourceForge补丁下载失败 (SourceForge Patch Download Failed)\n")
#             f.write(f"# 原始请求URL (Original Requested URL): {original_url}\n")
#             f.write(f"# 尝试下载的Diff URL (Attempted Diff URL): {attempted_url}\n")
#             f.write(f"# 错误信息 (Error Message): {error_message}\n")
#             f.write(f"#\n")
#             f.write(f"# 请尝试手动访问原始URL并导航到 'Diff' -> 'Unified' 视图来获取补丁。\n")
#             f.write(f"# (Please try manually visiting the original URL and navigating to the 'Diff' -> 'Unified' view to get the patch.)\n")
#         logger.info(f"已在 {output_path} 创建错误提示文件 (Error placeholder file created at {output_path})")
#     except Exception as e_write:
#         logger.error(f"写入错误提示文件失败 (Failed to write error placeholder file at {output_path}): {e_write}")



def _download_direct_patch(patch_url: str, output_path: Path, headers: dict) -> Path:
    """直接下载补丁文件"""
    try:
        logger.info(f"直接下载补丁文件: {patch_url}")
        
        # 修正URL，确保没有重复的.patch后缀
        direct_url = patch_url
        if direct_url.endswith('.patch.patch'):
            direct_url = direct_url[:-6]  # 移除重复的.patch
        
        # 如果URL不以.patch结尾且不是SourceForge，添加.patch后缀
        if not direct_url.endswith('.patch') and 'sourceforge.net' not in direct_url:
            direct_url += '.patch'
        
        # 设置重试策略
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        
        response = session.get(direct_url, headers=headers)
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
        logger.error(f"直接下载patch失败: {e}")
        raise ValueError(f"无法下载补丁: {patch_url} - {str(e)}")


# def download_patch_by_commit_info(repo_owner: str = None, repo_name: str = None, 
#                   commit_sha: str = None, output_path: Path = None, resource_type: str = 'github') -> Path:
#     if resource_type == 'github':
#         patch_url = f"https://github.com/{repo_owner}/{repo_name}/commit/{commit_sha}.patch"
#         return download_patch(patch_url, output_path)
#     else:
#         raise ValueError(f"不支持的资源类型: {resource_type}")

def generate_patch_from_git(commit_sha: str, repo_path: Path, output_path: Path) -> Path:
    """
    通过git format-patch命令从本地仓库生成标准格式的补丁文件
    
    Args:
        commit_sha: 提交的SHA
        repo_path: 本地仓库路径
        output_path: 输出补丁文件路径
        
    Returns:
        生成的补丁文件路径
    """
    try:
        logger.info(f"尝试从本地仓库生成补丁: {commit_sha}")
        
        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用git format-patch命令生成标准格式的补丁
        # -1: 只生成一个提交的补丁
        # --stdout: 输出到标准输出而不是文件
        # --no-stat: 不包含统计信息
        # --no-numbered: 不在文件名中包含序号
        # --keep-subject: 保持原始提交信息
        result = subprocess.run(
            ['git', 'format-patch', '-1', '--stdout', '--no-stat', commit_sha],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode != 0:
            logger.error(f"从本地仓库生成补丁失败: {result.stderr}")
            return None
        
        # 将输出写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result.stdout)
        
        logger.info(f"成功从本地仓库生成补丁: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"从本地仓库生成补丁时出错: {e}")
        return None
