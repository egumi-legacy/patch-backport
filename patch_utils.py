import subprocess
from pathlib import Path
from loguru import logger

def download_patch(patch_url, output_path, use_cached_patches=False):
    """
    下载patch文件，支持缓存
    
    :param patch_url: patch的URL
    :param output_path: 输出路径
    :param use_cached_patches: 是否使用缓存
    :return: patch文件路径
    """
    # # 如果启用缓存且文件存在，直接返回
    # if use_cached_patches and output_path.exists():
    #     logger.info(f"使用缓存的patch文件: {output_path}")
    #     return output_path
    
    # 如果启用缓存且文件存在，直接返回
    if use_cached_patches: 
        if output_path.exists():
            logger.info(f"使用缓存的patch文件: {output_path}")
            return output_path
        else:
            logger.info(f"缓存文件不存在, 下载patch: {output_path}")

    # logger.info(f"hello")

    # 下载patch
    patch_url = f"{patch_url}.patch"
    try:
        result = subprocess.run(
            ['curl', '-L', patch_url, '-o', str(output_path)],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"下载patch文件成功: {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"下载patch失败: {e.stderr}")
        return None