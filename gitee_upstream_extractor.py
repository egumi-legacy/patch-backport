#!/usr/bin/env python3
import os
import re
import sys
import argparse
import requests
import dotenv
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from loguru import logger
from datetime import datetime
import json

def setup_logger():
    """设置日志记录器"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 配置日志格式和输出
    logger.remove()  # 移除默认处理器
    
    # 添加控制台处理器
    logger.add(
        sys.stdout, 
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # 添加文件处理器
    log_file = log_dir / f"gitee_extractor_{os.getpid()}.log"
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        compression="zip"
    )
    
    logger.info(f"日志文件: {log_file}")

def load_env_token() -> str:
    """从.env文件加载Gitee令牌"""
    dotenv.load_dotenv()
    token = os.getenv('GITEE_TOKEN')
    if not token:
        logger.error("未找到GITEE_TOKEN环境变量，请在.env文件中设置")
        sys.exit(1)
    return token

def parse_gitee_url(url: str) -> Tuple[str, str, str]:
    """
    解析Gitee URL，提取所有者、仓库名和commit hash
    
    Args:
        url: Gitee commit URL
        
    Returns:
        (owner, repo, commit_hash) 元组
    """
    # 支持两种URL格式:
    # https://gitee.com/openeuler/kernel/commit/0c1bc63a96e15761181c880ba5c4f2adc33d6789
    # https://gitee.com/openeuler/kernel/commits/0c1bc63a96e15761181c880ba5c4f2adc33d6789
    
    pattern = r'https://gitee\.com/([^/]+)/([^/]+)/commit(?:s)?/([0-9a-fA-F]+)'
    match = re.match(pattern, url)
    
    if not match:
        raise ValueError(f"无效的Gitee提交URL: {url}")
    
    owner = match.group(1)
    repo = match.group(2)
    commit_hash = match.group(3)
    
    return owner, repo, commit_hash

def get_commit_detail(owner: str, repo: str, commit_hash: str, token: str) -> Dict:
    """
    使用Gitee API获取提交详情
    
    Args:
        owner: 仓库所有者
        repo: 仓库名称
        commit_hash: 提交哈希
        token: Gitee API令牌
        
    Returns:
        提交详情字典
    """
    url = f"https://gitee.com/api/v5/repos/{owner}/{repo}/commits/{commit_hash}"
    
    headers = {
        'User-Agent': 'GiteeUpstreamExtractor/1.0',
        'Accept': 'application/json',
        'Content-Type': 'application/json;charset=UTF-8',
        'Authorization': f'token {token}'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"获取提交详情失败: {e}")
        if hasattr(response, 'text'):
            logger.error(f"API响应: {response.text}")
        return {}

def extract_upstream_commit(commit_message: str) -> Optional[str]:
    """
    从提交信息中提取上游提交哈希
    
    Args:
        commit_message: 提交信息
        
    Returns:
        上游提交哈希，如果未找到则返回None
    """
    patterns = [
        r'(?i)commit\s+([a-f0-9]{7,40})\s+upstream',           # commit hash upstream
        r'(?i)\[\s*upstream\s+commit\s+([a-f0-9]{7,40})\s*\]', # [upstream commit hash]
        r'(?i)upstream:?\s+([a-f0-9]{7,40})',                  # upstream: hash
        r'(?i)upstream\s+commit:?\s+([a-f0-9]{7,40})',         # upstream commit: hash
        r'(?i)\(upstream\s*(?:commit)?\s*([a-f0-9]{7,40})\)',  # (upstream commit hash)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, commit_message)
        if match:
            return match.group(1)
    
    return None

def process_url(url: str, token: str) -> Dict:
    """
    处理单个Gitee URL
    
    Args:
        url: Gitee commit URL
        token: Gitee API令牌
        
    Returns:
        包含处理结果的字典
    """
    try:
        owner, repo, commit_hash = parse_gitee_url(url)
        logger.info(f"处理提交: {owner}/{repo} {commit_hash[:8]}")
        
        commit_detail = get_commit_detail(owner, repo, commit_hash, token)
        if not commit_detail:
            logger.error(f"获取提交详情失败: {owner}/{repo} {commit_hash}")
            return {
                'url': url,
                'commit_hash': commit_hash,
                'success': False,
                'error': '获取提交详情失败'
            }
        
        commit_message = commit_detail.get('commit', {}).get('message', '')
        if not commit_message:
            logger.error(f"提交信息为空: {owner}/{repo} {commit_hash}")
            return {
                'url': url,
                'commit_hash': commit_hash,
                'success': False,
                'error': '提交信息为空'
            }
        
        upstream_hash = extract_upstream_commit(commit_message)
        if not upstream_hash:
            logger.error(f"未找到上游提交引用: {owner}/{repo} {commit_hash}")
            return {
                'url': url,
                'commit_hash': commit_hash,
                'success': False,
                'error': '未找到上游提交引用'
            }
        
        return {
            'url': url,
            'commit_hash': commit_hash,
            'success': True,
            'upstream_hash': upstream_hash,
            'commit_message': commit_message
        }
        
    except Exception as e:
        logger.error(f"处理URL时出错: {e}")
        return {
            'url': url,
            'success': False,
            'error': str(e)
        }

def process_urls(urls: List[str], token: str) -> List[Dict]:
    """
    处理多个Gitee URL
    
    Args:
        urls: Gitee commit URL列表
        token: Gitee API令牌
        
    Returns:
        处理结果列表
    """
    results = []
    
    for url in urls:
        url = url.strip()
        if not url:
            continue
            
        result = process_url(url, token)
        results.append(result)
    
    return results

def read_urls_from_file(file_path: str) -> List[str]:
    """
    从文件读取URL列表
    
    Args:
        file_path: 文件路径
        
    Returns:
        URL列表
    """
    try:
        with open(file_path, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        return []

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="从Gitee提交URL提取上游提交哈希")
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('-f', '--file', type=str, help="包含Gitee提交URL的文件（每行一个URL）")
    input_group.add_argument('-u', '--urls', type=str, nargs='+', help="Gitee提交URL列表")
    
    parser.add_argument('-o', '--output', type=str, help="输出文件路径（默认输出到控制台）")
    parser.add_argument('-v', '--verbose', action='store_true', help="显示详细信息")
    parser.add_argument('-m', '--show-message', action='store_true', help="显示提交信息")
    parser.add_argument('-j', '--json', action='store_true', help="以JSON格式输出结果")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logger()
    
    # 加载Gitee令牌
    token = load_env_token()
    
    # 获取URL列表
    urls = []
    if args.file:
        urls = read_urls_from_file(args.file)
        logger.info(f"从文件 {args.file} 读取了 {len(urls)} 个URL")
    else:
        urls = args.urls
        logger.info(f"从命令行读取了 {len(urls)} 个URL")
    
    if not urls:
        logger.error("没有找到有效的URL")
        sys.exit(1)
    
    # 处理URL
    start_time = datetime.now()
    results = process_urls(urls, token)
    processing_time = (datetime.now() - start_time).total_seconds()
    
    # 输出结果
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    logger.info(f"处理完成: 成功 {len(successful)}/{len(results)} 耗时: {processing_time:.2f}秒")
    
    # 如果请求JSON格式输出
    if args.json:
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'total': len(results),
            'successful': len(successful),
            'failed': len(failed),
            'success_rate': (len(successful) / len(results) * 100) if results else 0,
            'processing_time': processing_time,
            'results': results
        }
        
        output_content = json.dumps(output_data, indent=2, ensure_ascii=False)
    else:
        # 准备输出内容
        output_lines = []
        
        # 添加成功的结果
        for result in successful:
            if args.verbose:
                message_info = f" | {result['commit_message'].split('\n')[0][:50]}..." if args.show_message and 'commit_message' in result else ""
                output_lines.append(f"{result['commit_hash'][:8]} -> {result['upstream_hash']}{message_info}")
            else:
                output_lines.append(result['upstream_hash'])
        
        # 添加失败的结果（如果verbose模式）
        if args.verbose and failed:
            output_lines.append("\n失败的URL:")
            for result in failed:
                output_lines.append(f"{result['url']} - {result.get('error', '未知错误')}")
        
        # 添加摘要
        if args.verbose:
            output_lines.append(f"\n总结:")
            output_lines.append(f"总URL数: {len(results)}")
            output_lines.append(f"成功数: {len(successful)}")
            output_lines.append(f"失败数: {len(failed)}")
            output_lines.append(f"成功率: {(len(successful) / len(results) * 100):.2f}%")
            output_lines.append(f"处理时间: {processing_time:.2f}秒")
        
        output_content = "\n".join(output_lines)
    
    # 输出结果
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_content)
            logger.info(f"结果已保存到 {args.output}")
        except Exception as e:
            logger.error(f"写入输出文件失败: {e}")
            print(output_content)
    else:
        print(output_content)

if __name__ == "__main__":
    main() 