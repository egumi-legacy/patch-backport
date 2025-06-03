#!/usr/bin/env python3
from pathlib import Path
import argparse
from pydantic import ValidationError
import yaml
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import traceback
import requests
import copy

# 第三方库
from loguru import logger
from ruamel.yaml import YAML
import pprint
import yaml
import dotenv
import subprocess

# 本地模块
from core.adaptation_pipeline import AdaptationPipeline
from core.parameter_manager import (
    BaseConfig, CommitContext, Mode1Config, Mode2Config, ModuleContext
)
from git_operations import GitOperations
from llm_assistant import LLMAssistant
from patch_evaluator import PatchEvaluator
from patch_processor import PatchProcessor
# from utils.git_operations import parse_github_url
from patch_utils import parse_repo_url as patch_utils_parse_repo_url, download_patch, generate_patch_from_git


def find_existing_repo(repo_base_path: Path, repo_url: str) -> Optional[Path]:
    """
    在指定的基础目录下查找与repo_url对应的git仓库
    
    Args:
        repo_base_path: 包含多个仓库的基础目录路径
        repo_url: 仓库URL
        
    Returns:
        如果找到，返回仓库路径；否则返回None
    """
    try:
        # 解析仓库信息
        repo_info = parse_repo_url(repo_url)
        repo_owner = repo_info['owner']
        repo_name = repo_info['name']
        
        # 使用owner_name格式作为本地仓库名称
        local_repo_name = f"{repo_owner}_{repo_name}"
        
        # 检查可能的仓库路径
        potential_paths = [
            repo_base_path / local_repo_name,  # owner_name格式
            repo_base_path / repo_name,  # 直接用仓库名
            repo_base_path / repo_name.lower(),  # 小写仓库名
        ]
        
        # 检查每个潜在路径是否是一个git仓库
        for path in potential_paths:
            logger.info(f"检查潜在仓库路径: {path}")
            git_dir = path / '.git'
            if git_dir.exists() and git_dir.is_dir():
                # 验证远程URL是否匹配
                result = subprocess.run(
                    ['git', 'config', '--get', 'remote.origin.url'],
                    cwd=path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.returncode == 0:
                    remote_url = result.stdout.strip()
                    # 简单验证URL是否匹配(忽略.git后缀和协议差异)
                    if normalize_git_url(remote_url) == normalize_git_url(repo_url):
                        logger.info(f"在 {path} 找到已存在的仓库")
                        return path
        
        return None
    except Exception as e:
        logger.error(f"查找已存在仓库时出错: {e}")
        return None


def normalize_git_url(url: str) -> str:
    """标准化git URL以便比较"""
    # 移除协议前缀
    url = re.sub(r'^(https?|git|ssh)://', '', url)
    # 移除用户名
    url = re.sub(r'^.+@', '', url)
    # 移除.git后缀
    url = re.sub(r'\.git$', '', url)
    # 移除尾部斜杠
    url = url.rstrip('/')
    return url


def parse_repo_url(url: str) -> Dict[str, str]:
    """
    从不同格式的仓库URL中解析owner和name信息，并提供正确的克隆URL
    
    使用patch_utils.py中的实现，保持一致性
    
    Args:
        url: 仓库URL
        
    Returns:
        包含owner、name和clone_url的字典
    """
    result = patch_utils_parse_repo_url(url)
    # 只保留我们需要的字段
    return {
        'owner': result['owner'],
        'name': result['name'],
        'clone_url': result['clone_url']
    }


def clone_repo(repo_url: str, target_dir: Path) -> bool:
    """
    克隆仓库到指定目录
    
    Args:
        repo_url: 仓库URL
        target_dir: 目标目录
        
    Returns:
        是否成功
    """
    try:
        logger.info(f"正在克隆仓库 {repo_url} 到 {target_dir}")
        
        # 确保目标目录存在
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # 获取正确的克隆URL
        repo_info = parse_repo_url(repo_url)
        clone_url = repo_info['clone_url']
        logger.info(f"使用克隆URL: {clone_url}")
        
        # 克隆仓库
        result = subprocess.run(
            ['git', 'clone', clone_url, str(target_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"克隆仓库失败: {result.stderr}")
            return False
            
        logger.info(f"成功克隆仓库到: {target_dir}")
        return True
    except Exception as e:
        logger.error(f"克隆仓库时出错: {e}")
        return False


def expand_path(path_str: str) -> Path:
    """
    扩展路径，处理波浪号等特殊字符
    
    Args:
        path_str: 路径字符串
        
    Returns:
        扩展后的Path对象
    """
    # 处理波浪号(~)，将其扩展为用户主目录
    if path_str.startswith('~'):
        expanded_path = str(Path.home()) + path_str[1:]
        return Path(expanded_path)
    return Path(path_str)


def get_base_repo_path(path: str) -> Path:
    """
    获取合适的基础仓库路径
    如果提供的路径本身是git仓库，则使用其父目录
    
    Args:
        path: 路径字符串
        
    Returns:
        基础仓库路径
    """
    # 先扩展路径中的特殊字符
    p = expand_path(path)
    # 检查是否是git仓库
    if (p / '.git').exists() and (p / '.git').is_dir():
        logger.info(f"检测到 {p} 是一个git仓库，使用其父目录作为基础路径")
        return p.parent
    return p


def handle_repo_url(repo_url: str, config_data: dict) -> tuple:
    """
    处理仓库URL，检查是否存在或需要克隆
    
    Args:
        repo_url: 仓库URL
        config_data: 配置数据
        
    Returns:
        (base_repo_path, repo_path) 元组，分别是基础仓库路径和具体仓库路径
    """
    # 获取或创建repo_base_path字段
    if 'repo_base_path' not in config_data['common']:
        # 如果没有repo_base_path，使用repo_path作为初始值
        base_path_str = config_data['common'].get('repo_path', '../backport-test')
        base_path = get_base_repo_path(base_path_str)
        config_data['common']['repo_base_path'] = str(base_path)
    else:
        # 已有repo_base_path，确保它不是git仓库
        base_path = get_base_repo_path(config_data['common']['repo_base_path'])
        config_data['common']['repo_base_path'] = str(base_path)
    
    logger.info(f"使用基础仓库路径: {base_path}")
    
    # 解析仓库URL，获取owner和name
    repo_info = parse_repo_url(repo_url)
    repo_owner = repo_info['owner']
    repo_name = repo_info['name']
    clone_url = repo_info['clone_url']
    
    # 使用owner_name格式作为本地仓库名称
    local_repo_name = f"{repo_owner}_{repo_name}"
    
    # 查找是否存在该仓库
    existing_repo = find_existing_repo(base_path, repo_url)
    if existing_repo:
        logger.info(f"使用已存在的仓库: {existing_repo}")
        return str(base_path), str(existing_repo)
    
    # 仓库不存在，需要克隆
    target_dir = base_path / local_repo_name
    if clone_repo(clone_url, target_dir):
        return str(base_path), str(target_dir)
    else:
        # 克隆失败，使用原始路径
        logger.warning(f"仓库克隆失败，使用默认路径: {base_path}")
        return str(base_path), str(base_path)


class PatchBackportTool:
    """补丁移植工具"""
    def __init__(self, config_path: str = "configs/new_inputs.yaml"):
        """初始化"""
        self.config_path = config_path
        self.config = self._load_config()
        dotenv.load_dotenv()
        self.github_token = os.getenv('GITHUB_TOKEN')
        # GitHub API请求头
        self.headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Accept': 'application/json, application/vnd.github+json',
            'Authorization': f'token {self.github_token}',
            'Host': 'api.github.com',
            'Connection': 'keep-alive'
        }        
        # 初始化日志
        self._setup_logger()
    
    def _load_config(self) -> BaseConfig:
        """加载配置"""
        with open(self.config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # 获取公共配置和模式
        common_config = config_data.get('common', {})
        mode = common_config.get('mode', 1)
        
        # 合并公共配置与模式专用配置
        try:
            if mode == 1:
                mode_specific = config_data.get('mode1', {})
                combined = {**common_config, **mode_specific}
                return Mode1Config(**combined)
            elif mode == 2:
                mode_specific = config_data.get('mode2', {})
                combined = {**common_config, **mode_specific}
                return Mode2Config(**combined)
            else:
                raise ValueError(f"不支持的模式: {mode}")
        except ValidationError as e:
            print(f"配置验证失败:\n{e.json(indent=2)}")
            sys.exit(1)

    def _setup_logger(self):
        """设置日志"""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"backport_{timestamp}.log"
        
        # 配置日志格式和输出
        logger.remove()  # 移除默认处理器
        
        # 添加控制台处理器
        logger.add(
            sys.stdout, 
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level="INFO"
        )
        
        # 添加文件处理器
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="10 MB",
            compression="zip"
        )
        
        logger.info(f"日志文件: {log_file}")
    
    def run(self):
        """运行工具"""
        logger.info(f"开始执行 模式{self.config.mode}")
        
        try:
            # 根据模式执行对应处理
            if self.config.mode == 1:
                self._process_mode1()
            else:
                self._process_mode2()
                
            logger.info("处理完成")
            
        except Exception as e:
            logger.error(f"执行过程发生错误: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            sys.exit(1)
    
    def _process_mode1(self):
        """处理模式1: 单个补丁多个版本"""
        # 获取补丁URL
        patch_url = self.config.patch_url
        logger.info(f"处理补丁: {patch_url}")
        
        # 创建处理流水线
        pipeline = AdaptationPipeline(self.config)
        
        # 获取所有目标版本
        target_versions = self.config.target_version
        logger.info(f"目标版本: {target_versions}")
        
        # 各个版本的结果
        version_results = {}
        
        # 处理每个版本
        for target_version in target_versions:
            logger.info(f"开始处理版本: {target_version}")
            
            # 创建当前版本的配置副本
            version_config = copy.deepcopy(self.config)
            version_config.target_version = target_version
            
            # 创建提交上下文
            commit_context = CommitContext.create_for_mode1(version_config)
            
            # 创建模块上下文
            context = ModuleContext(
                config=version_config,
                commit=commit_context
            )
            
            # 记录开始时间
            context.start_time = datetime.now()
            
            # 处理补丁
            processed_context = pipeline.process_patch(context)
            
            # 记录结束时间
            processed_context.end_time = datetime.now()
            
            # 合并处理结果的补丁
            final_patch = self._merge_patches(processed_context)
            if final_patch:
                logger.info(f"成功合并补丁到: {final_patch}")
                processed_context.commit.patch_path = final_patch
            
            # 保存结果
            result_path = self._save_results(processed_context)
            
            # 打印摘要
            self._print_summary(processed_context)
            
            # 存储此版本的结果
            version_results[target_version] = {
                'context': processed_context,
                'result_path': result_path
            }
        
        # 打印所有版本的汇总结果
        # self._print_multi_version_summary(version_results)
        
        return version_results
    
    def _process_mode2(self):
        """处理模式2: 多个补丁"""
        # 获取 commits 提交列表（包含上下游提交）
        commits_list = self._get_commits_list()
        logger.info(f"找到 {len(commits_list)} 个上游提交")
        
        # 创建处理流水线
        pipeline = AdaptationPipeline(self.config)
        
        # 统计变量
        start = 75 # 30
        end = 250 # 65
        total_commits = len(commits_list[start:end])
        # total_commits = end - start + 1
        successful_commits = 0
        direct_success_count = 0
        llm_success_count = 0
        patch_adapter_success_count = 0
        compiler_success_count = 0
        failed_commits = []
        
        # 处理每个提交
        for idx, commit_info in enumerate(commits_list[start:end], start+1):
            upstream_sha = commit_info['upstream_sha']
            # 单个测试
            # if upstream_sha != "82a0a3e6f8c02b3236b55e784a083fa4ee07c321": #backapply用例
            # if upstream_sha != "a2fad248947d702ed3dcb52b8377c1a3ae201e44": #enhanced用例
            # if upstream_sha != "79504249d7e27cad4a3eeb9afc6386e418728ce0": #bug
            if upstream_sha != "2844ddbd540fc84d7571cca65d6c43088e4d6952":
            # if upstream_sha != "4ccacf86491d33d2486b62d4d44864d7101b299d": #chunk analyzer用例
                continue
            else:
                total_commits = 1

            logger.info(f"处理提交 {idx}/{total_commits}: {upstream_sha[:6]}")
            
            # 创建提交上下文
            commit_context = CommitContext.create_for_mode2(self.config, commit_info)
            
            # 创建模块上下文
            context = ModuleContext(
                config=self.config,
                commit=commit_context
            )
            
            # 记录开始时间
            context.start_time = datetime.now()
            
            # 处理补丁
            context = pipeline.process_patch(context)
            
            # 记录结束时间
            context.end_time = datetime.now()
            
            # 合并处理结果的补丁
            final_patch = self._merge_patches(context)
            if final_patch:
                logger.info(f"成功合并补丁到: {final_patch}")
                context.commit.patch_path = final_patch
            
            # 保存结果
            self._save_results(context)
            
            # 打印摘要
            self._print_summary(context)
            
            # 更新统计
            direct_success = bool(context.direct_apply_result and context.direct_apply_result.get('success'))
            if direct_success:
                direct_success_count += 1
            llm_success = bool(context.llm_output.get('apply_result') and context.llm_output.get('apply_result').get('success'))
            patch_adapter_success = bool(context.patch_adapter_result and context.patch_adapter_result.get('success'))
            compilation_success = bool(context.compilation_result and context.compilation_result.get('success'))
            
            if llm_success:
                llm_success_count += 1
            if patch_adapter_success:
                patch_adapter_success_count += 1
            if compilation_success:
                compiler_success_count += 1
            if direct_success or llm_success or patch_adapter_success or compilation_success:
                successful_commits += 1
            else:
                failed_commits.append({
                    'sha': upstream_sha[:6],
                    'error': context.last_error
                })
        
        # 打印总体统计
        self._print_mode2_statistics(total_commits, 
                                     direct_success_count, 
                                     llm_success_count, 
                                     patch_adapter_success_count, 
                                     compiler_success_count, 
                                     failed_commits)
        

    def _print_multi_version_summary(self, version_results):
        """打印多个版本的汇总结果"""
        logger.info("=" * 80)
        logger.info("多版本补丁适配汇总")
        logger.info("=" * 80)
        
        success_count = 0
        for version, result in version_results.items():
            context = result['context']
            success = False
            
            # 检查各个模块的成功状态
            if context.direct_apply_result and context.direct_apply_result.get('success'):
                method = "直接应用"
                success = True
            elif context.chunk_analyzer_result and context.chunk_analyzer_result.get('applied_chunks', 0) > 0:
                method = f"块分析器 ({context.chunk_analyzer_result.get('applied_chunks', 0)}/{context.chunk_analyzer_result.get('total_chunks', 0)})"
                success = context.chunk_analyzer_result.get('applied_chunks', 0) == context.chunk_analyzer_result.get('total_chunks', 0)
            elif context.patch_adapter_result and context.patch_adapter_result.get('success'):
                method = "补丁适配器"
                success = True
            else:
                method = "所有方法失败"
                
            status = "成功" if success else "失败"
            logger.info(f"版本 {version}: {status} (方法: {method})")
            
            if success:
                success_count += 1
        
        success_rate = success_count / len(version_results) * 100
        logger.info(f"总成功率: {success_rate:.1f}% ({success_count}/{len(version_results)})")
        
        # 保存统计结果到文件
        stats_dir = Path("statistics")
        stats_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        repo_name = version_results[list(version_results.keys())[0]]['context'].commit.repo_name
        commit_sha = version_results[list(version_results.keys())[0]]['context'].commit.commit_sha[:6]
        stats_file = stats_dir / f"{repo_name}_multi_version_stats_{commit_sha}_{timestamp}.json"
        
        # 构建统计数据
        stats_data = {
            'timestamp': datetime.now().isoformat(),
            'repo_name': repo_name,
            'commit_sha': commit_sha,
            'versions': list(version_results.keys()),
            'success_count': success_count,
            'total_versions': len(version_results),
            'success_rate': success_rate,
            'version_details': {}
        }
        
        # 添加每个版本的详细信息
        for version, result in version_results.items():
            context = result['context']
            # 确定是否需要适配和适配结果
            direct_success = bool(context.direct_apply_result and context.direct_apply_result.get('success'))
            need_adapt = not direct_success  # 如果直接应用失败，则需要适配
            adapt_success = success if need_adapt else None  # 只有需要适配时才有适配结果
            
            stats_data['version_details'][version] = {
                'need_adapt': need_adapt,
                'adapt_success': adapt_success,
                'success': success,
                'method': method,
                'execution_time': context.execution_time,
            }
            
            # 如果有块分析结果，添加块统计
            if context.chunk_analyzer_result:
                chunks_info = {
                    'total_chunks': context.chunk_analyzer_result.get('total_chunks', 0),
                    'no_conflict_chunks': context.chunk_analyzer_result.get('applied_chunks', 0)
                }
                # 添加详细的块信息（如果有）
                if hasattr(context, 'chunks_detailed_info'):
                    chunks_info.update(context.chunks_detailed_info)
                
                stats_data['version_details'][version]['chunks_info'] = chunks_info
        
        # 保存统计结果
        with open(stats_file, 'w') as f:
            json.dump(stats_data, f, indent=2)
            
        logger.info(f"多版本统计结果已保存到: {stats_file}")
        
        return stats_data
    
    def _get_commits_list(self) -> List[Dict[str, str]]:
        """获取上游提交信息"""
        # 检查是否有缓存文件
        commits_file = self.config.cached_commits_file_path
        logger.info(f"commits_file:{str(commits_file)}")
        logger.info(f"use_cached_commits:{self.config.use_cached_commits}")

        if hasattr(self.config, 'use_cached_commits') and self.config.use_cached_commits and commits_file.exists():
            logger.info("从缓存文件加载commits信息")
            with open(commits_file, 'r') as f:
                return json.load(f)
        
        # 扫描提交历史
        upstream_commits = self._scan_commits(
            self.config.branch
        )
        
        # 缓存结果
        logger.info("保存commits信息到缓存文件")
        with open(commits_file, 'w') as f:
            json.dump(upstream_commits, f, indent=2)
        
        return upstream_commits
    
    def _scan_commits(self, branch, start_page=1, end_page=1, per_page=100) -> List[Dict[str, str]]:
        """
        扫描提交历史，查找包含上游提交引用的提交
        
        :param branch: 分支名
        :param owner: 仓库所有者
        :param repo: 仓库名
        :param start_page: 起始页码
        :param end_page: 结束页码
        :param per_page: 每页数量
        :return: 上游提交列表
        """
        if branch is None:
            raise ValueError("branch 为空，无法扫描提交历史")
        
        # 使用配置中的值
        if hasattr(self.config, 'commits_pages_start') and self.config.commits_pages_start is not None:
            start_page = self.config.commits_pages_start
        if hasattr(self.config, 'commits_pages_end') and self.config.commits_pages_end is not None:
            end_page = self.config.commits_pages_end
        if hasattr(self.config, 'commits_per_page') and self.config.commits_per_page is not None:
            per_page = self.config.commits_per_page
            
        logger.info(f"扫描提交历史: 页码范围={start_page}-{end_page}, 每页={per_page}")
        
        all_upstream_commits = []
        
        # 遍历所有页面
        for page in range(start_page, end_page + 1):
            commits_url = f"https://api.github.com/repos/{self.config.repo_owner}/{self.config.repo_name}/commits"
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
    
    def _extract_upstream_commit(self, commit_message: str) -> Optional[str]:
        """从提交信息中提取上游提交的 SHA"""
        patterns = [
            r'(?i)commit\s+([a-f0-9]+)\s+upstream',           # commit hash upstream
            r'(?i)\[\s*upstream\s+commit\s+([a-f0-9]+)\s*\]', # [upstream commit hash]
            r'(?i)upstream:?\s+([a-f0-9]+)',                  # upstream: hash
            r'(?i)upstream\s+commit:?\s+([a-f0-9]+)',         # upstream commit: hash
            r'(?i)\(upstream\s*(?:commit)?\s*([a-f0-9]+)\)',  # (upstream commit hash)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, commit_message)
            if match:
                logger.info(f"提取上游提交: {match.group(1)}")
                return match.group(1)
        
        logger.info(f"未提取到上游提交: {commit_message}")
        return None
    
    def _save_results(self, context: ModuleContext) -> Path:
        """保存处理结果"""
        # 创建结果目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        commit_sha = context.commit.commit_sha[:6]
        repo_name = context.commit.repo_name  # 获取仓库名称
        
        # 使用仓库名称作为前缀创建结果目录
        result_dir = Path("results") / f"{repo_name}_{context.config.target_version}_{commit_sha}_{timestamp}"
        result_dir.mkdir(parents=True, exist_ok=True)
        
        # 准备提交信息
        commit_info = {
            'sha': context.commit.commit_sha,
            'patch_url': context.commit.patch_url,
        }
        
        # 添加下游提交信息（如果有）
        if hasattr(context.commit, 'downstream_sha'):
            commit_info['downstream_sha'] = context.commit.downstream_sha
        if hasattr(context.commit, 'downstream_message'):
            commit_info['downstream_message'] = context.commit.downstream_message
        
        # 添加最终补丁路径信息
        final_patch_content = None
        if hasattr(context.commit, 'patch_path') and context.commit.patch_path:
            commit_info['final_patch_path'] = str(context.commit.patch_path)
            # 复制最终补丁到结果目录
            final_patch_filename = context.commit.patch_path.name
            result_patch_path = result_dir / final_patch_filename
            try:
                shutil.copy2(context.commit.patch_path, result_patch_path)
                logger.info(f"已复制最终补丁到结果目录: {result_patch_path}")
                
                # 读取补丁内容
                with open(context.commit.patch_path, 'r', encoding='utf-8') as f:
                    final_patch_content = f.read()
                    
            except Exception as e:
                logger.error(f"复制补丁文件时出错: {e}")
        
        # 提取LLM输出
        llm_output = None
        if context.llm_output and 'response_path' in context.llm_output:
            response_path = context.llm_output.get('response_path')
            try:
                with open(response_path, 'r', encoding='utf-8') as f:
                    llm_output = f.read()
            except Exception as e:
                logger.error(f"读取LLM输出时出错: {e}")
        
        # 计算运行时间
        start_time = context.start_time if hasattr(context, 'start_time') else None
        end_time = context.end_time if hasattr(context, 'end_time') else datetime.now()
        total_seconds = None
        if start_time:
            total_seconds = (end_time - start_time).total_seconds()
        
        # 确定适配状态
        direct_success = bool(context.direct_apply_result and context.direct_apply_result.get('success'))
        patch_adapter_success = bool(context.patch_adapter_result and context.patch_adapter_result.get('success'))
        chunk_analyzer_success = bool(context.chunk_analyzer_result and context.chunk_analyzer_result.get('applied_chunks') == context.chunk_analyzer_result.get('total_chunks'))
        overall_success = direct_success or patch_adapter_success or chunk_analyzer_success
        
        # 确定是否需要适配和适配结果
        need_adapt = not direct_success  # 如果直接应用失败，则需要适配
        adapt_success = patch_adapter_success or chunk_analyzer_success if need_adapt else None  # 只有需要适配时才有适配结果
            
        # 更新上下文中的适配状态（保留旧字段以维持兼容性）
        context.adaptation_status = None if not need_adapt else adapt_success
        # 添加新的字段
        context.need_adapt = need_adapt
        context.adapt_success = adapt_success
        
        # 准备块分析信息
        chunks_info = {
            "total_chunks": 0,
            "no_conflict_chunks": 0,
            "adapt_succeeded_chunks": 0,
            "adapt_failed_chunks": 0,
            "compilation_failed_chunks": 0
        }
        
        # 从chunk_analyzer_result和chunks_detailed_info获取信息
        if context.chunk_analyzer_result:
            # 从结果获取基本信息
            chunks_info["total_chunks"] = context.chunk_analyzer_result.get('total_chunks', 0)
            chunks_info["no_conflict_chunks"] = context.chunk_analyzer_result.get('applied_chunks', 0)
        
        # 合并详细的chunk信息
        if hasattr(context, 'chunks_detailed_info'):
            chunks_info.update(context.chunks_detailed_info)
        
        # 计算模块成功状态
        modules_status = {
            "direct_apply": bool(context.direct_apply_result and context.direct_apply_result.get('success')),
            "chunk_analyzer": bool(context.chunk_analyzer_result and context.chunk_analyzer_result.get('applied_chunks') > 0),
            "llm_adapter": bool(context.llm_output and context.llm_output.get('success')),
            "patch_adapter": bool(context.patch_adapter_result and context.patch_adapter_result.get('success')),
            "compilation": bool(context.compilation_result and context.compilation_result.get('success'))
        }
            
        # 添加执行路径信息
        execution_path = self._determine_execution_path(context)
        
        # 构建合并后的结果对象
        result = {
            # 摘要信息放在最前面
            'summary': {
                'need_adapt': need_adapt,  # 是否需要适配：True-需要适配，False-不需要适配(直接应用成功)
                'adapt_success': adapt_success,  # 适配结果：True-适配成功，False-适配失败，None-不需要适配
                'chunks_info': chunks_info,  # 块分析详细信息
                'method': next(
                    method for method, condition in [
                        ('direct_apply', context.direct_apply_result and context.direct_apply_result.get('success')),
                        ('chunk_analyzer', context.chunk_analyzer_result and context.chunk_analyzer_result.get('applied_chunks') > 0),
                        ('compiler', context.compilation_result and context.compilation_result.get('success')),
                        ('llm_adapter', context.llm_output and context.llm_output.get('success')),
                        ('patch_adapter', context.patch_adapter_result and context.patch_adapter_result.get('success')),
                        ('failed', True)
                    ] if condition
                ),
                'timestamp': datetime.now().isoformat()
            },
            'to_adapt_commit': commit_info,
            'config': {
                'mode': context.config.mode,
                'target_version': context.config.target_version,
                'enabled_modules': context.config.enabled_modules
            },
            'results': {
                'direct_apply': context.direct_apply_result,
                'chunk_analyzer': context.chunk_analyzer_result,
                'llm_adapter': context.llm_output,
                'patch_adapter': context.patch_adapter_result,
                'final_patch_path': str(context.commit.patch_path) if hasattr(context.commit, 'patch_path') and context.commit.patch_path else None,
                'last_error': context.last_error
            },
            'timing': {
                'start_time': start_time.isoformat() if start_time else None,
                'end_time': end_time.isoformat() if end_time else None,
                'total_seconds': total_seconds,
                'module_execution_seconds': context.execution_times if hasattr(context, 'execution_times') else {}
            },
            # 详细报告部分
            'detailed': {
                'need_adapt': need_adapt,
                'adapt_success': adapt_success,
                'patch_content': final_patch_content,
                'llm_output': llm_output,
                'model': context.config.model,
                'modules_status': modules_status,
                'input_parameters': {
                    'target_version': context.config.target_version,
                    'commit_sha': context.commit.commit_sha,
                    'timestamp': datetime.now().isoformat(),
                    'execution_path': execution_path
                }
            }
        }
        
        # 添加补丁适配方法（如果有）
        if context.patch_adapter_result:
            result['detailed']['input_parameters']['adaptation_method'] = context.patch_adapter_result.get('adaptation_method', 'unknown')
        
        # 保存结果JSON
        result_file = result_dir / "result.json"
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        logger.info(f"结果已保存到: {result_file}")
        return result_dir
        
    def _determine_execution_path(self, context: ModuleContext) -> str:
        """
        确定执行路径，用于报告中显示主要的执行流程
        
        Args:
            context: 模块上下文
            
        Returns:
            执行路径描述
        """
        if context.direct_apply_result and context.direct_apply_result.get('success'):
            return "direct_apply"
            
        execution_path = []
        
        if context.chunk_analyzer_result and context.chunk_analyzer_result.get('applied_chunks') > 0:
            if context.chunk_analyzer_result.get('applied_chunks') == context.chunk_analyzer_result.get('total_chunks'):
                return "chunk_analyzer (all chunks)"
            else:
                execution_path.append(f"chunk_analyzer ({context.chunk_analyzer_result.get('applied_chunks')}/{context.chunk_analyzer_result.get('total_chunks')} chunks)")
                
        if context.llm_output and context.llm_output.get('success'):
            execution_path.append("llm_adapter")
            
        if context.patch_adapter_result and context.patch_adapter_result.get('success'):
            execution_path.append("patch_adapter")
            
        if not execution_path:
            return "failed (no successful modules)"
            
        return " -> ".join(execution_path)
    
    def _print_summary(self, context: ModuleContext):
        """打印处理摘要"""
        commit_sha = context.commit.commit_sha[:6]
        
        # 确定处理结果
        direct_success = bool(context.direct_apply_result and context.direct_apply_result.get('success'))
        llm_success = bool(context.llm_output and context.llm_output.get('success'))
        logger.info(f"context.patch_adapter_result: {context.patch_adapter_result}")
        patch_adapter_success = bool(context.patch_adapter_result and context.patch_adapter_result.get('success'))
        compilation_success = bool(context.compilation_result and context.compilation_result.get('success'))
        
        # 确定适配状态
        if direct_success:
            adaptation_status = "无需适配 (直接应用成功)"
            method = "direct_apply"
        elif llm_success or patch_adapter_success or compilation_success:
            adaptation_status = "适配成功"
            if llm_success:
                method = "llm_adapter"
            elif patch_adapter_success:
                method = "patch_adapter"
            elif compilation_success:
                method = "compiler"
            else:
                method = "unknown"
        else:
            adaptation_status = "适配失败"
            method = "failed"
        
        # 打印摘要
        logger.info("=" * 50)
        logger.info(f"处理摘要 - 提交: {commit_sha}")
        logger.info(f"适配状态: {adaptation_status} (方法: {method})")
        
        # 打印块分析结果（如果有）
        if hasattr(context, 'chunks_detailed_info') and context.chunks_detailed_info:
            chunks_info = context.chunks_detailed_info
            logger.info("块分析统计:")
            logger.info(f"- 总块数: {chunks_info.get('total_chunks', 0)}")
            logger.info(f"- 无冲突块数: {chunks_info.get('no_conflict_chunks', 0)}")
            logger.info(f"- 成功适配块数: {chunks_info.get('adapt_succeeded_chunks', 0)}")
            logger.info(f"- 适配失败块数: {chunks_info.get('adapt_failed_chunks', 0)}")
            logger.info(f"- 编译失败块数: {chunks_info.get('compilation_failed_chunks', 0)}")
        
        # 打印执行时间
        if hasattr(context, 'execution_time') and context.execution_time:
            logger.info(f"总执行时间: {context.execution_time:.2f}秒")
        
        if context.last_error:
            logger.info(f"最后错误: {context.last_error}")
        
        logger.info("=" * 50)

    def _print_mode2_statistics(self, total, direct_success_count, llm_success_count, patch_adapter_success_count, compiler_success_count, failed_commits):
        """打印模式2的统计信息"""
        # 从上下文中提取处理方法信息 (不使用不存在的self.processed_commits属性)
        direct_apply_count = 0
        patch_adapter_count = 0
        llm_adapter_count = 0
        compiler_count = 0
        failed_count = len(failed_commits)
        
        # 从result.json文件中获取详细信息
        results_dir = Path("results")
        # if results_dir.exists():
        #     # 遍历results目录下的所有结果文件
        #     for result_dir in results_dir.iterdir():
        #         logger.info(f"result_dir: {result_dir.resolve()}")
        #         if not result_dir.is_dir() or not (result_dir / "result.json").exists():
        #             continue
                    
        #         with open(result_dir / "result.json", "r") as f:
        #             result_data = json.load(f)
                    
        #         # 检查处理方法
        #         if "summary" in result_data and "method" in result_data["summary"]:
        #             method = result_data["summary"]["method"]
        #             logger.info(f"method: {method}")
        #             if method == "direct_apply":
        #                 direct_apply_count += 1
        #             elif method == "patch_adapter":
        #                 patch_adapter_count += 1
        #             elif method == "llm_adapter":
        #                 llm_adapter_count += 1
        #             elif method == "compiler":
        #                 compiler_count += 1
        
        # 计算适配成功率（排除直接应用成功的情况）
        adapt_required = total - direct_success_count
        adapt_successful = compiler_success_count
        adapt_success_rate = (adapt_successful / adapt_required) * 100 if adapt_required > 0 else 0
        
        logger.info("=" * 60)
        logger.info(f"模式2处理统计")
        logger.info("=" * 60)
        logger.info(f"总提交数: {total}")
        logger.info(f"直接应用成功: {direct_success_count}")
        logger.info(f"需要适配数量: {adapt_required}")
        logger.info(f"适配成功数量: {adapt_successful}")
        logger.info(f"- LLM适配成功: {llm_success_count}")
        logger.info(f"- 补丁适配成功: {patch_adapter_success_count}")
        logger.info(f"- 编译成功: {compiler_success_count}")
        logger.info(f"适配失败数量: {failed_count}")
        # logger.info(f"总体成功率: {success_rate:.2f}%")
        logger.info(f"适配成功率: {adapt_success_rate:.2f}%")
        
        if failed_commits:
            logger.info("\n失败的提交:")
            for commit in failed_commits:
                logger.info(f"  - {commit['sha']}: {commit.get('error', '未知错误')}")
        
        logger.info("=" * 60)
        
        # 保存统计结果到文件
        stats_dir = Path("statistics")
        stats_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        repo_name = self.config.repo_name  # 获取仓库名称
        stats_file = stats_dir / f"{repo_name}_mode2_stats_{self.config.target_version}_{timestamp}.json"
        
        stats_data = {
            'timestamp': datetime.now().isoformat(),
            'repo_name': repo_name,
            'target_version': self.config.target_version,
            'total_commits': total,
            'direct_apply_success': direct_success_count,
            'adaptation_required': adapt_required,
            'adaptation_successful': adapt_successful,
            'patch_adapter_success': patch_adapter_success_count,
            'llm_adapter_success': llm_success_count,
            'compiler_success': compiler_success_count,
            'failed_commits': failed_count,
            # 'overall_success_rate': success_rate,
            'adaptation_success_rate': adapt_success_rate,
            'failed_details': failed_commits
        }
        
        with open(stats_file, 'w') as f:
            json.dump(stats_data, f, indent=2)
        
        logger.info(f"统计结果已保存到: {stats_file}")

    def _merge_patches(self, context: ModuleContext) -> Optional[Path]:
        """
        合并不同模块生成的补丁
        
        Args:
            context: 模块上下文
            
        Returns:
            合并后的补丁路径，失败则返回None
        """
        logger.info("开始合并补丁...")
        
        # 检查chunk_analyzer结果
        chunk_results = context.chunk_analyzer_result
        patch_adapter_results = context.patch_adapter_result
        
        # 如果没有任何结果，直接返回
        if not chunk_results and not patch_adapter_results:
            logger.warning("没有找到任何可合并的补丁结果")
            return None
            
        # 创建补丁目录
        patch_dir = context.commit.patch_dir
        patch_dir.mkdir(parents=True, exist_ok=True)
        
        # 合并后的补丁路径
        merged_patch_path = patch_dir / f"merged_{context.config.target_version}.patch"
        
        try:
            chunk_applied = False
            all_chunks_applied = False
            chunk_patches = []
            
            # 处理chunk_analyzer结果
            if isinstance(chunk_results, dict) and chunk_results.get('applied_chunks'):
                chunk_applied = True
                applied_chunks = chunk_results.get('applied_chunks', 0)
                total_chunks = chunk_results.get('total_chunks', 0)
                all_chunks_applied = applied_chunks == total_chunks and total_chunks > 0
                
                # 收集应用成功的chunk补丁
                # logger.info("chunk_results1:")
                # pprint.pprint(chunk_results)
                if 'applied_chunk_patches' in chunk_results:
                    chunk_patches = [Path(p) for p in chunk_results['applied_chunk_patches'] if p]
                    logger.info("chunk_results2:")
                    pprint.pprint(chunk_results)
                    logger.info(f"chunk_patches: {chunk_patches}")
                    
                logger.info(f"Chunk分析器应用了 {applied_chunks}/{total_chunks} 个chunks")
                
            # 如果所有chunk都应用成功，跳过patch_adapter
            if all_chunks_applied:
                logger.info("所有chunks都已成功应用，跳过patch_adapter")
                
                # 如果只有一个补丁，直接使用它
                if len(chunk_patches) == 1:
                    context.commit.patch_path = chunk_patches[0]
                    logger.info(f"使用唯一的chunk补丁: {context.commit.patch_path}")
                    return context.commit.patch_path
                    
                # 合并多个chunk补丁
                elif len(chunk_patches) > 1:
                    # 使用新的方法通过Git操作来合并补丁
                    merged_patch_content = self._combine_patch_files(chunk_patches)
                    
                    if not merged_patch_content:
                        logger.error("合并chunk补丁失败，使用第一个补丁作为后备方案")
                        context.commit.patch_path = chunk_patches[0]
                        return context.commit.patch_path
                    
                    with open(merged_patch_path, 'w', encoding='utf-8') as f:
                        f.write(merged_patch_content)
                        
                    context.commit.patch_path = merged_patch_path
                    logger.info(f"合并了 {len(chunk_patches)} 个chunk补丁到: {merged_patch_path}")
                    return merged_patch_path
            
            # 如果有chunk_analyzer的部分结果，但需要与patch_adapter结合
            patch_adapter_path = None
            if isinstance(patch_adapter_results, dict) and patch_adapter_results.get('success'):
                patch_adapter_path = patch_adapter_results.get('adapted_patch_path')
                if patch_adapter_path:
                    patch_adapter_path = Path(patch_adapter_path)
                    logger.info(f"找到patch_adapter成功的补丁: {patch_adapter_path}")
            
            # 合并chunk补丁和patch_adapter补丁
            if chunk_applied and patch_adapter_path:
                if not chunk_patches:
                    # 如果没有成功的chunk补丁，直接使用patch_adapter的补丁
                    context.commit.patch_path = patch_adapter_path
                    logger.info(f"没有成功的chunk补丁，使用patch_adapter补丁: {patch_adapter_path}")
                    return patch_adapter_path
                
                # 合并chunk补丁和patch_adapter补丁
                logger.info(f"合并 {len(chunk_patches)} 个chunk补丁和patch_adapter补丁")
                
                # 合并所有需要应用的补丁，包括chunk补丁和patch_adapter补丁
                all_patches = chunk_patches + [patch_adapter_path]
                
                # 使用新的方法通过Git操作来合并补丁
                merged_content = self._combine_patch_files(all_patches)
                
                if not merged_content:
                    logger.error("合并补丁失败，使用patch_adapter的补丁作为后备方案")
                    context.commit.patch_path = patch_adapter_path
                    return patch_adapter_path
                
                # 写入最终合并的补丁
                with open(merged_patch_path, 'w', encoding='utf-8') as f:
                    f.write(merged_content)
                
                context.commit.patch_path = merged_patch_path
                logger.info(f"成功合并chunk补丁和patch_adapter补丁到: {merged_patch_path}")
                return merged_patch_path
            
            # 如果只有patch_adapter结果
            elif patch_adapter_path:
                context.commit.patch_path = patch_adapter_path
                logger.info(f"只使用patch_adapter补丁: {patch_adapter_path}")
                return patch_adapter_path
                
            # 如果只有chunk_analyzer结果
            elif chunk_applied and chunk_patches:
                # 合并chunk补丁
                merged_content = self._combine_patch_files(chunk_patches)
                
                with open(merged_patch_path, 'w', encoding='utf-8') as f:
                    f.write(merged_content)
                    
                context.commit.patch_path = merged_patch_path
                logger.info(f"只合并chunk补丁到: {merged_patch_path}")
                return merged_patch_path
            
            logger.warning("没有找到可合并的补丁")
            return None
            
        except Exception as e:
            logger.error(f"合并补丁时出错: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def _combine_patch_files(self, patch_files: List[Path]) -> str:
        """
        通过实际应用补丁到测试分支上，然后使用git format-patch生成最终的合并补丁
        
        Args:
            patch_files: 补丁文件路径列表
            
        Returns:
            合并后的补丁内容
        """
        if not patch_files:
            return ""
        
        # 确保所有补丁文件都存在
        valid_patches = [p for p in patch_files if p.exists()]
        if not valid_patches:
            logger.error("没有有效的补丁文件")
            return ""
        
        # 创建临时工作目录
        temp_dir = Path("temp_patch_merge")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 确定仓库路径和目标版本
        repo_path = self.config.repo_path
        # 确保target_version是字符串而不是列表
        target_version = self.config.target_version
        if isinstance(target_version, list):
            target_version = target_version[0]  # 取第一个元素作为字符串
        
        # 创建临时分支名称
        import uuid
        branch_name = f"patch_merge_{uuid.uuid4().hex[:8]}"
        
        try:
            # 准备临时测试分支
            logger.info(f"创建临时测试分支: {branch_name}")
            
            # 先切换到目标版本 (确保target_version是字符串)
            target_version_str = target_version
            if isinstance(target_version_str, list):
                target_version_str = target_version_str[0]
                
            result = subprocess.run(
                ['git', 'checkout', target_version_str],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.error(f"切换到目标版本失败: {result.stderr}")
                return ""
            
            # 创建新分支
            result = subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                logger.error(f"创建临时分支失败: {result.stderr}")
                return ""
            
            # 清理工作区
            subprocess.run(['git', 'reset', '--hard', 'HEAD'], cwd=repo_path)
            subprocess.run(['git', 'clean', '-fd'], cwd=repo_path)
            
            # 依次应用每个补丁
            for patch_path in valid_patches:
                logger.info(f"应用补丁: {patch_path}")
                
                # 尝试使用git apply而不是git am，因为apply不会自动提交
                logger.info(f"执行命令: git apply --ignore-whitespace {str(patch_path)}")
                result = subprocess.run(
                    ['git', 'apply', '--ignore-whitespace', str(patch_path)],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
                
                # 打印应用结果以便调试
                if result.returncode == 0:
                    logger.info(f"成功应用补丁: {patch_path}")
                else:
                    logger.info(f"应用补丁失败，返回码: {result.returncode}")
                    if result.stderr:
                        logger.info(f"错误输出: {result.stderr}")
                
                if result.returncode != 0:
                    logger.warning(f"应用补丁 {patch_path} 失败: {result.stderr}")
                    # 尝试使用 -3way 选项来处理冲突
                    result = subprocess.run(
                        ['git', 'apply', '--ignore-whitespace', '--3way', str(patch_path)],
                        cwd=repo_path,
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"尝试3way应用补丁 {patch_path} 也失败: {result.stderr}")
                        # 中止合并
                        subprocess.run(['git', 'reset', '--hard', 'HEAD'], cwd=repo_path)
                        continue
                    else:
                        # 检查是否有冲突
                        result = subprocess.run(
                            ['git', 'diff', '--name-only', '--diff-filter=U'],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        
                        if result.stdout.strip():
                            logger.error(f"应用补丁 {patch_path} 时有未解决的冲突")
                            # 中止合并
                            subprocess.run(['git', 'reset', '--hard', 'HEAD'], cwd=repo_path)
                            continue
            
            # 检查是否有更改
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD'],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if not result.stdout.strip():
                logger.warning("合并后没有任何更改")
                return ""
            
            # 添加所有更改并提交
            subprocess.run(['git', 'add', '-A'], cwd=repo_path)
            
            # 创建提交
            commit_msg = f"合并补丁：{len(valid_patches)}个补丁文件"
            result = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"创建提交失败: {result.stderr}")
                return ""
            
            # 使用format-patch生成最终的补丁
            merged_patch_path = temp_dir / "merged.patch"
            logger.info(f"执行命令: git format-patch -1 HEAD --stdout > {merged_patch_path}")
            
            try:
                result = subprocess.run(
                    ['git', 'format-patch', '-1', 'HEAD', '--stdout'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
            except Exception as e:
                logger.error(f"执行git format-patch命令失败: {e}")
                # 尝试检查git状态，收集更多信息
                try:
                    status_result = subprocess.run(
                        ['git', 'status'],
                        cwd=repo_path,
                        capture_output=True,
                        text=True
                    )
                    logger.info(f"Git状态: {status_result.stdout}")
                except:
                    pass
                raise
            
            if result.returncode != 0:
                logger.error(f"生成合并补丁失败: {result.stderr}")
                return ""
            
            # 保存合并后的补丁内容
            merged_content = result.stdout
            
            # 检查内容是否为空
            if not merged_content.strip():
                logger.error("生成的补丁内容为空")
                return ""
                
            # 写入文件
            with open(merged_patch_path, 'w', encoding='utf-8') as f:
                f.write(merged_content)
            
            # 验证文件是否存在并且有内容
            if merged_patch_path.exists() and merged_patch_path.stat().st_size > 0:
                logger.info(f"成功生成合并补丁: {merged_patch_path} (大小: {merged_patch_path.stat().st_size} 字节)")
            else:
                logger.error(f"生成补丁文件失败: {merged_patch_path}")
                return ""
            return merged_content
            
        except Exception as e:
            logger.error(f"合并补丁过程中发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""
            
        finally:
            # 清理：切换回原分支并删除临时分支
            try:
                logger.info(f"清理临时分支: {branch_name}")
                # 确保使用正确的字符串格式
                checkout_version = target_version
                if isinstance(checkout_version, list):
                    checkout_version = checkout_version[0]
                    
                subprocess.run(['git', 'checkout', checkout_version], cwd=repo_path)
                subprocess.run(['git', 'branch', '-D', branch_name], cwd=repo_path)
            except Exception as e:
                logger.warning(f"清理临时分支时发生错误: {e}")
    
    def _extract_patch_header(self, patch_content: str) -> str:
        """
        提取补丁文件的头信息
        
        Args:
            patch_content: 补丁文件内容
            
        Returns:
            头信息字符串
        """
        header = ""
        for line in patch_content.splitlines():
            if line.startswith('diff --git'):
                break
            header += line + "\n"
        return header
    
    def _parse_patch_files(self, patch_content: str) -> Dict[str, str]:
        """
        解析补丁内容中的文件修改
        
        Args:
            patch_content: 补丁内容
            
        Returns:
            文件路径与对应修改内容的字典
        """
        result = {}
        current_file = None
        current_content = ""
        
        lines = patch_content.splitlines(True)  # 保留换行符
        i = 0
        
        # 跳过头信息
        while i < len(lines) and not lines[i].startswith('diff --git'):
            i += 1
            
        # 处理每个文件的修改
        while i < len(lines):
            line = lines[i]
            
            # 新文件开始
            if line.startswith('diff --git'):
                # 保存之前的文件内容
                if current_file:
                    result[current_file] = current_content
                
                # 提取新文件名
                parts = line.split()
                if len(parts) >= 3:
                    # 格式: diff --git a/path/to/file b/path/to/file
                    current_file = parts[2][2:]  # 移除 "b/"
                    current_content = line
                else:
                    current_file = None
                    current_content = ""
            else:
                # 累积当前文件的内容
                if current_file:
                    current_content += line
                    
            i += 1
            
        # 保存最后一个文件的内容
        if current_file:
            result[current_file] = current_content
            
        return result


def get_default_config_path() -> Path:
    """获取默认配置文件路径"""
    config_dir = Path.home() / '.config' / 'port-patch'
    config_file = config_dir / 'new_inputs.yaml'
    
    # 确保配置目录存在
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # 如果配置文件不存在，创建默认配置
    if not config_file.exists():
        # logger.error(f"配置文件不存在，请检查是否存在{config_file}")
        raise FileNotFoundError(f"配置文件不存在，请检查是否存在{config_file}")
        # default_config = {
        #     'common': {
        #         'mode': 1,
        #         'target_version': '',
        #         'repo_url': '',
        #         'repo_path': '',
        #         'repo_base_path': ''
        #     },
        #     'mode1': {
        #         'patch_url': ''
        #     },
        #     'mode2': {
        #         'repo_url': '',
        #         'branch': 'main'
        #     }
        # }
        
        # # 确保目录存在
        # config_dir.mkdir(parents=True, exist_ok=True)
        
        # # 写入默认配置
        # with open(config_file, 'w') as f:
        #     yaml.dump(default_config, f, default_flow_style=False)
            
    return config_file

def validate_commit_arg(arg_value):
    """
    验证commit参数是否为URL或hash格式。
    返回格式化后的commit列表。
    """
    # 分割输入，支持多个commit输入（以逗号分隔）
    commits = [c.strip() for c in arg_value.split(',') if c.strip()]
    
    valid_commits = []
    for commit in commits:
        # 检查是否是URL格式 - 支持多种平台
        if commit.startswith("http") and (
            "/commit/" in commit or  # GitHub/Gitee格式
            ("/ci/" in commit and "sourceforge.net" in commit)  # SourceForge格式
        ):
            valid_commits.append(commit)
        # 检查是否是Commit Hash格式
        elif re.fullmatch(r'[0-9a-fA-F]+', commit) and len(commit) >= 6:
            valid_commits.append(commit)
        else:
            raise argparse.ArgumentTypeError(
                f"'{commit}' 不是有效的补丁URL（需以http开头并包含/commit/或/ci/）或commit hash"
            )
    
    if not valid_commits:
        raise argparse.ArgumentTypeError("必须提供至少一个有效的commit")
    
    return valid_commits

def find_or_clone_repo(repo_url: str, repo_base_path: Path) -> Path:
    """
    在指定的基础目录下查找或克隆仓库
    
    Args:
        repo_url: 仓库URL
        repo_base_path: 基础目录路径
        
    Returns:
        仓库路径
    """
    try:
        # 确保基础目录存在
        repo_base_path.mkdir(parents=True, exist_ok=True)
        
        # 解析仓库信息
        repo_info = parse_repo_url(repo_url)
        repo_owner = repo_info['owner']
        repo_name = repo_info['name']
        clone_url = repo_info['clone_url']
        
        # 使用owner_name格式作为本地仓库名称
        local_repo_name = f"{repo_owner}_{repo_name}"
        
        # 检查可能的仓库路径
        potential_paths = [
            repo_base_path / local_repo_name,  # owner_name格式
            repo_base_path / repo_name,  # 直接用仓库名
            repo_base_path / repo_name.lower(),  # 小写仓库名
        ]
        
        # 检查每个潜在路径是否是一个git仓库
        for path in potential_paths:
            logger.info(f"检查潜在仓库路径: {path}")
            git_dir = path / '.git'
            if git_dir.exists() and git_dir.is_dir():
                # 验证远程URL是否匹配
                result = subprocess.run(
                    ['git', 'config', '--get', 'remote.origin.url'],
                    cwd=path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.returncode == 0:
                    remote_url = result.stdout.strip()
                    # 简单验证URL是否匹配(忽略.git后缀和协议差异)
                    if normalize_git_url(remote_url) == normalize_git_url(clone_url):
                        logger.info(f"找到已存在的仓库: {path}")
                        return path
        
        # 如果没有找到匹配的仓库，克隆一个新的
        logger.info(f"没有找到仓库，开始克隆: {clone_url}")
        clone_path = repo_base_path / local_repo_name
        
        # 如果路径已存在但不是正确的仓库，先删除
        if clone_path.exists():
            logger.warning(f"路径已存在但不是正确的仓库，删除: {clone_path}")
            if clone_path.is_dir():
                shutil.rmtree(clone_path)
            else:
                clone_path.unlink()
        
        # 使用解析得到的clone_url进行克隆
        logger.info(f"使用克隆URL: {clone_url}")
        result = subprocess.run(
            ['git', 'clone', clone_url, str(clone_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"克隆仓库失败: {result.stderr}")
            raise RuntimeError(f"克隆仓库失败: {result.stderr}")
        
        logger.info(f"成功克隆仓库到: {clone_path}")
        return clone_path
        
    except Exception as e:
        logger.error(f"查找或克隆仓库时出错: {e}")
        logger.error(traceback.format_exc())
        raise

def verify_commit_exists(commit: str, repo_path: Path) -> bool:
    """
    验证commit是否存在于仓库中
    
    Args:
        commit: commit hash
        repo_path: 仓库路径
        
    Returns:
        commit是否存在
    """
    try:
        # 提取纯hash（如果是URL格式）
        commit_hash = commit
        if commit.startswith("http") and "/commit/" in commit:
            commit_hash = commit.split("/commit/")[1].split(".")[0]  # 移除可能的.patch后缀
        
        # 检查commit是否存在
        result = subprocess.run(
            ['git', 'cat-file', '-t', commit_hash],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        return result.returncode == 0 and 'commit' in result.stdout
    except Exception as e:
        logger.error(f"验证commit存在性时出错: {e}")
        return False

def process_multiple_commits(commits: list, config_data: dict, repo_path: Path, config_path: str) -> None:
    """
    处理多个commit
    
    Args:
        commits: commit列表（URL或hash）
        config_data: 配置数据
        repo_path: 仓库路径
        config_path: 配置文件路径
    """
    logger.info(f"处理 {len(commits)} 个commit")
    
    # 创建工具实例
    tool = PatchBackportTool(config_path=config_path)
    
    for idx, commit in enumerate(commits, 1):
        logger.info(f"处理第 {idx}/{len(commits)} 个commit: {commit}")
        
        try:
            # 提取commit信息
            commit_info = extract_commit_info(commit, repo_path, config_data)
            if not commit_info:
                logger.error(f"无法提取commit信息: {commit}")
                continue
            
            # 更新配置
            updated_config = config_data.copy()
            updated_config['mode1']['patch_url'] = commit_info['patch_url']
            
            # 如果commit_info中直接提供了patch_path，添加到配置中
            if 'patch_path' in commit_info:
                logger.info(f"使用本地生成的补丁文件: {commit_info['patch_path']}")
                if 'patch_path' not in updated_config['mode1']:
                    updated_config['mode1']['patch_path'] = commit_info['patch_path']
            
            # 保存更新后的配置
            updated_config_path = f"temp_config_{idx}.yaml"
            with open(updated_config_path, 'w') as f:
                yaml.dump(updated_config, f)
            
            # 创建并运行工具
            commit_tool = PatchBackportTool(config_path=updated_config_path)
            commit_tool.run()
            
            # 清理临时配置文件
            if Path(updated_config_path).exists():
                Path(updated_config_path).unlink()
                
        except Exception as e:
            logger.error(f"处理commit {commit} 时出错: {e}")
            logger.error(traceback.format_exc())

def extract_commit_info(commit: str, repo_path: Path, config_data: dict) -> Optional[Dict[str, str]]:
    """
    提取commit信息
    
    Args:
        commit: commit URL或hash
        repo_path: 仓库路径
        config_data: 配置数据
        
    Returns:
        commit信息字典，包含patch_url等
    """
    # 提取URL中的hash部分（如果是URL格式）
    commit_hash = commit
    repo_owner = config_data['common'].get('repo_owner', '')
    repo_name = config_data['common'].get('repo_name', '')
    
    if commit.startswith("http"):
        # 解析不同格式的URL
        repo_info = patch_utils_parse_repo_url(commit)
        repo_owner = repo_info['owner']
        repo_name = repo_info['name']
        
        if repo_info['commit_sha']:
            commit_hash = repo_info['commit_sha']
        else:
            # 尝试从URL中提取commit hash
            if "/commit/" in commit:
                # GitHub/Gitee格式
                commit_hash = commit.split("/commit/")[1].split(".")[0]  # 移除可能的.patch后缀
            elif "/-/commit/" in commit:
                # GitLab特殊格式
                commit_hash = commit.split("/-/commit/")[1].split(".")[0]
            elif "/ci/" in commit:
                # SourceForge格式
                commit_hash = commit.split("/ci/")[1].split("/")[0]
    
    # 验证commit是否存在于仓库中
    if verify_commit_exists(commit_hash, repo_path):
        logger.info(f"Commit {commit_hash} 存在于仓库中")
        
        # 构建patch URL
        if not repo_owner or not repo_name:
            logger.error(f"无法从配置或URL中提取仓库所有者和名称")
            return None
        
        # 根据不同平台构建不同的patch URL
        patch_url = None
        repo_url = config_data['common'].get('repo_url', '')
        
        if "github.com" in repo_url:
            patch_url = f"https://github.com/{repo_owner}/{repo_name}/commit/{commit_hash}.patch"
        elif "gitee.com" in repo_url:
            patch_url = f"https://gitee.com/{repo_owner}/{repo_name}/commit/{commit_hash}.patch"
        elif "gitlab.com" in repo_url:
            patch_url = f"https://gitlab.com/{repo_owner}/{repo_name}/-/commit/{commit_hash}.patch"
        elif "sourceforge.net" in repo_url or "sf.net" in repo_url:
            # SourceForge URL格式：项目名/仓库名
            patch_url = f"https://sourceforge.net/p/{repo_owner}/{repo_name}/ci/{commit_hash}/"
        else:
            # 默认使用GitHub格式
            patch_url = f"https://github.com/{repo_owner}/{repo_name}/commit/{commit_hash}.patch"
        
        return {
            'commit_sha': commit_hash,
            'patch_url': patch_url,
            'repo_owner': repo_owner,
            'repo_name': repo_name
        }
    else:
        logger.warning(f"Commit {commit_hash} 不存在于仓库中，尝试下载或生成补丁")
        
        # 创建临时目录用于下载补丁
        temp_dir = Path("temp_patches")
        temp_dir.mkdir(exist_ok=True)
        
        patch_path = temp_dir / f"{commit_hash[:8]}.patch"
        patch_url = None
        
        # 如果是URL格式，尝试下载补丁
        if commit.startswith("http"):
            # 构建patch URL
            if "github.com" in commit:
                if not commit.endswith('.patch'):
                    patch_url = f"{commit}.patch"
                else:
                    patch_url = commit
            elif "gitee.com" in commit:
                if not commit.endswith('.patch'):
                    patch_url = f"{commit}.patch"
                else:
                    patch_url = commit
            elif "gitlab.com" in commit:
                # GitLab使用特殊格式
                if "/-/commit/" in commit:
                    base_url = commit.split("/-/commit/")[0]
                    commit_id = commit.split("/-/commit/")[1].split(".")[0]
                    patch_url = f"{base_url}/-/commit/{commit_id}.patch"
                else:
                    # 尝试标准格式
                    if not commit.endswith('.patch'):
                        patch_url = f"{commit}.patch"
                    else:
                        patch_url = commit
            elif "sourceforge.net" in commit:
                # SourceForge不提供直接的补丁下载，使用原始URL
                patch_url = commit
            
            if patch_url:
                try:
                    # 尝试下载补丁
                    from patch_utils import download_patch
                    if download_patch(patch_url, patch_path).exists():
                        logger.info(f"成功下载补丁: {patch_path}")
                        return {
                            'commit_sha': commit_hash,
                            'patch_url': patch_url,
                            'repo_owner': repo_owner,
                            'repo_name': repo_name
                        }
                    else:
                        logger.warning(f"下载补丁失败: {patch_url}")
                except Exception as e:
                    logger.warning(f"下载补丁出错: {e}")
        
        # 尝试从本地仓库生成补丁
        try:
            from patch_utils import generate_patch_from_git
            if generate_patch_from_git(commit_hash, repo_path, patch_path):
                logger.info(f"成功从本地仓库生成补丁: {patch_path}")
                
                # 构造一个虚拟的patch_url
                if not patch_url:
                    patch_url = f"local://{repo_path}/{commit_hash}"
                
                return {
                    'commit_sha': commit_hash,
                    'patch_url': patch_url,
                    'repo_owner': repo_owner,
                    'repo_name': repo_name,
                    'patch_path': str(patch_path)  # 直接提供patch_path
                }
        except Exception as e:
            logger.error(f"从本地仓库生成补丁失败: {e}")
        
        logger.error(f"无法获取提交 {commit_hash} 的补丁")
        return None
    
def clean_config(config_data: dict, config_path: str):
    config_data['mode1']['branch'] = None
    config_data['mode1']['repo_url'] = None
    config_data['mode2']['branch'] = None
    config_data['mode2']['repo_url'] = None
    # 写入配置文件
    with open(config_path, 'w') as f:
        yaml.dump(config_data, f)
    logger.info(f"清理配置文件: {config_path}")

def main():
    """主函数"""
    # 获取默认配置文件路径
    try:
        default_config_path = get_default_config_path()
        
        parser = argparse.ArgumentParser(description="补丁移植工具")
        parser.add_argument('commit_pos', type=validate_commit_arg, nargs='?', default=None,
                        help="补丁URL或commit hash（位置参数，多个用逗号分隔）")
        parser.add_argument('--config', '-c', type=str, default=str(default_config_path),
                        help=f"配置文件路径 (默认: {default_config_path})")
        parser.add_argument('--repo-url', '-r', type=str, required=False,
                        help="Git仓库URL (必填)")
        parser.add_argument('--mode', '-m', type=int, choices=[1, 2], default=1,
                        help="处理模式: 1=单个补丁, 2=批量处理 (默认: 1)")
        # parser.add_argument('--commit', '-p', type=str, required=False,
        #                     help="补丁URL或commit hash（命名参数）")
        parser.add_argument('--target', '-t', type=str, required=False,
                        help="目标版本，可以是tag或commit hash (必填)")
        
        # 先解析参数，不检查未知参数，用于处理URL中可能包含的特殊字符
        args, unknown = parser.parse_known_args()
        
        # 检查是否在未知参数中有完整的URL，如果有可能是commit参数
        if unknown and args.commit_pos is None:
            # 尝试找出看起来像URL的参数
            valid_commits = []
            for arg in unknown:
                if (arg.startswith("http") and "/commit/" in arg) or \
                (re.fullmatch(r'[0-9a-fA-F]+', arg) and len(arg) >= 6):
                    valid_commits.append(arg)
                    unknown.remove(arg)
            
            if valid_commits:
                args.commit_pos = valid_commits
        
        # 如果还有未知参数，报错
        if unknown:
            parser.error(f"未识别的参数: {' '.join(unknown)}")
        
        # 加载配置文件
        config_path = args.config
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
                # print("config_data:")
                # pprint.pprint(config_data)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            sys.exit(1)

        # 确保有commits或配置中已有patch_url
        if args.mode == 1 and not (args.commit_pos or config_data['mode1'].get('patch_url')):
            print("错误: 模式1下必须指定补丁URL或commit hash")
            sys.exit(1)
            
        if not (args.target or config_data['common'].get('target_version')):
            print("错误: 必须指定目标版本")
            sys.exit(1)
            
        # 处理仓库URL并获取仓库路径
        repo_url = args.repo_url or config_data['common'].get('repo_url', '')
        if not repo_url:
            print("错误: 必须指定Git仓库URL")
            sys.exit(1)
        
        # 根据命令行参数更新配置
        if args.mode:
            config_data['common']['mode'] = args.mode
            
        if args.target:
            config_data['common']['target_version'] = args.target
            
        # 如果branch未指定或为None，设置为与target_version相同
        if args.mode == 1:
            # 确保mode1中存在branch配置
            if 'branch' not in config_data['mode1'] or config_data['mode1']['branch'] is None:
                target_version = config_data['common']['target_version']
                # 如果target_version是列表，使用第一个值
                if isinstance(target_version, list):
                    branch_value = target_version[0]
                else:
                    branch_value = target_version
                config_data['mode1']['branch'] = branch_value
                logger.info(f"branch未指定，设置为与target_version相同: {branch_value}")
        # 对mode2也做同样处理
        elif args.mode == 2:
            if 'branch' not in config_data['mode2'] or config_data['mode2']['branch'] is None:
                target_version = config_data['common']['target_version']
                # 如果target_version是列表，使用第一个值
                if isinstance(target_version, list):
                    branch_value = target_version[0]
                else:
                    branch_value = target_version
                config_data['mode2']['branch'] = branch_value
                logger.info(f"branch未指定，设置为与target_version相同: {branch_value}")
        
        
        # 查找或克隆仓库
        try:
            # 获取repo_base_path，默认使用 ~/.cache/port_patch/
            repo_base_path = config_data['common'].get('repo_base_path', '')
            if not repo_base_path:
                repo_base_path = Path.home() / '.cache' / 'port_patch'
                config_data['common']['repo_base_path'] = str(repo_base_path)
            else:
                # 扩展路径中的特殊字符
                repo_base_path = expand_path(repo_base_path)
            
            # 查找或克隆仓库
            repo_path = find_or_clone_repo(repo_url, repo_base_path)
            config_data['common']['repo_path'] = str(repo_path)
            logger.info(f"使用仓库路径: {repo_path}")
            
            # # 更新repo_url配置
            # if args.mode == 1:
            #     config_data['common']['repo_url'] = repo_url
            # else:
            #     config_data['mode2']['repo_url'] = repo_url
                
        # if commit_param and args.mode == 1:
        #     # 如果提供的是commit hash而不是完整URL，需要构建完整URL
        #     if not commit_param.startswith('http'):
        #         # 从repo_url解析owner和repo
        #         from patch_utils import parse_github_url
        #         info = parse_github_url(args.repo_url)
        #         if info:
        #             patch_url = f"https://github.com/{info['owner']}/{info['repo']}/commit/{commit_param}.patch"
        #             config_data['mode1']['patch_url'] = patch_url
        #     else:
        #         # 如果是完整的commit URL，根据是否包含.patch后缀处理
        #         if commit_param.endswith('.patch'):
        #             config_data['mode1']['patch_url'] = commit_param
        #         else:
        #             config_data['mode1']['patch_url'] = f"{commit_param}.patch"
        #     # 保存更新后的配置
        #     with open(config_path, 'w') as f:
        #         yaml.dump(config_data, f)         
        # except Exception as e:
        #     logger.error(f"处理仓库路径时出错: {e}")
        #     sys.exit(1)
        except Exception as e:
            logger.error(f"处理仓库路径时出错: {e}")
            sys.exit(1)
        
        # 从仓库URL解析owner和name
        repo_info = parse_repo_url(repo_url)
        config_data['common']['repo_owner'] = repo_info['owner']
        config_data['common']['repo_name'] = repo_info['name']
        
        # 更新repo_url配置
        if args.mode == 1:
            config_data['common']['repo_url'] = repo_url
        else:
            config_data['mode2']['repo_url'] = repo_url
        
        print("config_data:")
        pprint.pprint(config_data)
        # 保存更新后的配置
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # 根据模式处理
        if args.mode == 1:
            # 如果有commit参数，处理它们
            if args.commit_pos:
                # 将输入的单个字符串转为列表
                commits = args.commit_pos
                if isinstance(commits, str):
                    commits = [commits]
                
                # 如果只有一个commit，使用普通流程
                if len(commits) == 1:
                    # 提取commit信息
                    commit_info = extract_commit_info(commits[0], repo_path, config_data)
                    if commit_info:
                        config_data['mode1']['patch_url'] = commit_info['patch_url']
                        
                        # 保存更新后的配置
                        with open(config_path, 'w') as f:
                            yaml.dump(config_data, f)
                        
                        # 创建并运行工具
                        tool = PatchBackportTool(config_path=config_path)
                        tool.run()
                    else:
                        logger.error(f"无法处理commit: {commits[0]}")
                        sys.exit(1)
                else:
                    # 处理多个commit
                    process_multiple_commits(commits, config_data, repo_path, config_path)
            else:
                # 使用配置文件中的patch_url
                tool = PatchBackportTool(config_path=config_path)
                tool.run()
        else:
            # 模式2：批量处理
            try:
                with open(config_path, 'w') as f:
                    yaml.dump(config_data, f, default_flow_style=False)
            except Exception as e:
                print(f"保存配置文件失败: {e}")
                sys.exit(1)
            tool = PatchBackportTool(config_path=config_path)
            tool.run()
    except Exception as e:
        logger.error(f"处理时出错: {e}")
        logger.error(f"错误信息: {traceback.format_exc()}")
        
    finally:
        clean_config(config_data, config_path)
        



if __name__ == "__main__":
    main()