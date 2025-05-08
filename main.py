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
        # 解析仓库名称
        repo_name = repo_url.rstrip('/').split('/')[-1]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        
        # 检查可能的仓库路径
        potential_paths = [
            repo_base_path / repo_name,  # 直接用仓库名
            repo_base_path / repo_name.lower(),  # 小写仓库名
        ]
        
        # 检查每个潜在路径是否是一个git仓库
        for path in potential_paths:
            logger.info(f"path:{path}")
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
        
        # 克隆仓库
        result = subprocess.run(
            ['git', 'clone', repo_url, str(target_dir)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"克隆仓库失败: {result.stderr}")
            return False
            
        logger.info(f"成功克隆仓库到 {target_dir}")
        return True
    except Exception as e:
        logger.error(f"克隆仓库时出错: {e}")
        return False


def get_base_repo_path(path: str) -> Path:
    """
    获取合适的基础仓库路径
    如果提供的路径本身是git仓库，则使用其父目录
    
    Args:
        path: 路径字符串
        
    Returns:
        基础仓库路径
    """
    p = Path(path)
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
    
    # 从URL解析仓库名称
    repo_name = repo_url.rstrip('/').split('/')[-1]
    if repo_name.endswith('.git'):
        repo_name = repo_name[:-4]
        
    # 查找是否存在该仓库
    existing_repo = find_existing_repo(base_path, repo_url)
    if existing_repo:
        logger.info(f"使用已存在的仓库: {existing_repo}")
        return str(base_path), str(existing_repo)
    
    # 仓库不存在，需要克隆
    target_dir = base_path / repo_name
    if clone_repo(repo_url, target_dir):
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
        self._print_multi_version_summary(version_results)
        
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
        result_dir = Path("results") / f"{context.config.target_version}_{commit_sha}_{timestamp}"
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
        execution_time = None
        if start_time:
            execution_time = (end_time - start_time).total_seconds()
        
        # 保存上下文信息
        result = {
            'commit': commit_info,
            'config': {
                'mode': context.config.mode,
                'target_version': context.config.target_version,
                'enabled_modules': context.config.enabled_modules
            },
            'results': {
                'direct_apply': context.direct_apply_result,
                'llm_adapter': context.llm_output,
                'patch_adapter': context.patch_adapter_result,
                'chunk_analyzer': context.chunk_analyzer_result,
                'final_patch_path': str(context.commit.patch_path) if hasattr(context.commit, 'patch_path') and context.commit.patch_path else None,
                'last_error': context.last_error
            },
            'timing': {
                'start_time': start_time.isoformat() if start_time else None,
                'end_time': end_time.isoformat() if end_time else None,
                'execution_time_seconds': execution_time,
                'module_times': context.execution_times if hasattr(context, 'execution_times') else {}
            },
            'summary': {
                'success': bool(context.direct_apply_result and context.direct_apply_result.get('success')) or
                          bool(context.patch_adapter_result and context.patch_adapter_result.get('success')) or
                          bool(context.chunk_analyzer_result and context.chunk_analyzer_result.get('applied_chunks') == context.chunk_analyzer_result.get('total_chunks')),
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
            }
        }
        
        # 保存结果JSON
        result_file = result_dir / "result.json"
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        # 创建和保存详细的输出报告
        self._save_detailed_report(context, result_dir, final_patch_content, llm_output, execution_time)
        
        logger.info(f"结果已保存到: {result_file}")
        return result_dir
        
    def _save_detailed_report(self, context: ModuleContext, result_dir: Path, 
                             final_patch_content: str = None, llm_output: str = None,
                             execution_time: float = None) -> None:
        """
        保存详细的输出报告，包含补丁内容、执行成功状态等
        
        Args:
            context: 模块上下文
            result_dir: 结果目录
            final_patch_content: 最终补丁内容
            llm_output: LLM输出内容
            execution_time: 执行时间（秒）
        """
        # 计算模块成功状态
        modules_status = {
            "direct_apply": bool(context.direct_apply_result and context.direct_apply_result.get('success')),
            "chunk_analyzer": bool(context.chunk_analyzer_result and context.chunk_analyzer_result.get('applied_chunks') > 0),
            "llm_adapter": bool(context.llm_output and context.llm_output.get('success')),
            "patch_adapter": bool(context.patch_adapter_result and context.patch_adapter_result.get('success')),
            "compilation": bool(context.compilation_result and context.compilation_result.get('success'))
        }
        
        # 整体是否成功
        overall_success = modules_status["direct_apply"] or modules_status["patch_adapter"] or \
                         (modules_status["chunk_analyzer"] and context.chunk_analyzer_result.get('applied_chunks') == context.chunk_analyzer_result.get('total_chunks'))
        
        # 使用的模型
        model = context.config.model
        
        # 获取执行时间
        execution_time = context.execution_time  # 使用新添加的属性
        
        # 创建详细报告
        report = {
            "success": overall_success,
            "patch_content": final_patch_content,
            "llm_output": llm_output,
            "model": model,
            "modules_status": modules_status,
            "execution_time_seconds": execution_time,
            "module_execution_times": context.execution_times,  # 添加各模块执行时间
            "important_info": {
                "target_version": context.config.target_version,
                "commit_sha": context.commit.commit_sha,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        # 添加一些其他重要信息
        if context.chunk_analyzer_result:
            chunks_info = {
                "total_chunks": context.chunk_analyzer_result.get('total_chunks', 0),
                "applied_chunks": context.chunk_analyzer_result.get('applied_chunks', 0)
            }
            report["important_info"]["chunks_info"] = chunks_info
            
        if context.patch_adapter_result:
            report["important_info"]["adaptation_method"] = context.patch_adapter_result.get('adaptation_method', 'unknown')
        
        # 添加执行路径信息
        execution_path = self._determine_execution_path(context)
        if execution_path:
            report["important_info"]["execution_path"] = execution_path
            
        # 保存详细报告JSON
        detailed_report_file = result_dir / "detailed_report.json"
        with open(detailed_report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
            
        logger.info(f"详细报告已保存到: {detailed_report_file}")
        
        return report
    
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
        
        if direct_success:
            result = "直接应用成功"
            method = "direct_apply"
        elif llm_success:
            result = "LLM适配成功"
            method = "llm_adapter"
        elif patch_adapter_success:
            result = "补丁适配成功"
            method = "patch_adapter"
        elif compilation_success:
            result = "编译成功"
            method = "compiler"
        else:
            result = "处理失败"
            method = "failed"
        
        # 打印摘要
        logger.info("=" * 50)
        logger.info(f"处理摘要 - 提交: {commit_sha}")
        logger.info(f"结果: {result} (方法: {method})")
        
        if context.last_error:
            logger.info(f"最后错误: {context.last_error}")
        
        logger.info("=" * 50)

    def _print_mode2_statistics(self, total, direct_success_count, llm_success_count, patch_adapter_success_count, compiler_success_count, failed_commits):
        """打印模式2的统计信息"""
        # success_rate = (compiler_success_count) / total * 100 if total > 0 else 0
        
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
        stats_file = stats_dir / f"mode2_stats_{self.config.target_version}_{timestamp}.json"
        
        stats_data = {
            'timestamp': datetime.now().isoformat(),
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
                if 'applied_patch_paths' in chunk_results:
                    chunk_patches = [Path(p) for p in chunk_results['applied_patch_paths'] if p]
                    
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
                    merged_patch_content = self._combine_patch_files(chunk_patches)
                    
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
                
                # 先合并所有chunk补丁
                chunk_merged_content = self._combine_patch_files(chunk_patches)
                
                # 再与patch_adapter补丁合并
                with open(patch_adapter_path, 'r', encoding='utf-8') as f:
                    adapter_content = f.read()
                
                # 提取两个补丁的文件修改
                chunk_files = self._parse_patch_files(chunk_merged_content)
                adapter_files = self._parse_patch_files(adapter_content)
                
                # 选择最终的文件修改
                final_files = {**chunk_files, **adapter_files}  # patch_adapter优先
                
                # 提取补丁头信息
                patch_header = self._extract_patch_header(adapter_content)
                
                # 写入最终合并的补丁
                with open(merged_patch_path, 'w', encoding='utf-8') as f:
                    f.write(patch_header)
                    
                    # 写入每个文件的修改
                    for file_path, content in final_files.items():
                        f.write(content)
                
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
        合并多个补丁文件内容
        
        Args:
            patch_files: 补丁文件路径列表
            
        Returns:
            合并后的补丁内容
        """
        if not patch_files:
            return ""
            
        # 读取所有补丁文件内容
        file_contents = []
        for path in patch_files:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    file_contents.append(f.read())
        
        if not file_contents:
            return ""
            
        # 使用第一个补丁的头信息
        patch_header = self._extract_patch_header(file_contents[0])
        
        # 提取每个补丁的文件修改
        all_file_changes = {}
        for content in file_contents:
            file_changes = self._parse_patch_files(content)
            all_file_changes.update(file_changes)  # 后面的优先
        
        # 构建合并后的补丁内容
        merged_content = patch_header
        for file_path, content in all_file_changes.items():
            merged_content += content
            
        return merged_content
    
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


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="补丁移植工具")
    parser.add_argument('--config', '-c', type=str, default="configs/new_inputs.yaml",
                       help="配置文件路径 (默认: configs/new_inputs.yaml)")
    parser.add_argument('--repo-url', '-r', type=str, required=False,
                       help="Git仓库URL (必填)")
    parser.add_argument('--mode', '-m', type=int, choices=[1, 2], default=1,
                       help="处理模式: 1=单个补丁, 2=批量处理 (默认: 1)")
    parser.add_argument('--patch', '-p', type=str,
                       help="补丁URL或commit hash (模式1下必填)")
    parser.add_argument('--target', '-t', type=str, required=False,
                       help="目标版本，可以是tag或commit hash (必填)")
    args = parser.parse_args()
    
    # 加载配置文件
    config_path = args.config
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        sys.exit(1)


    # 检查必需参数
    if args.mode == 1 and not (args.patch or config_data['mode1'].get('patch_url')):
        print("错误: 模式1下必须指定补丁URL或commit hash")
        sys.exit(1)
        
    if not (args.target or config_data['common'].get('target_version')):
        print("错误: 必须指定目标版本")
        sys.exit(1)
        
    if not (args.repo_url or 
            (args.mode == 1 and config_data['common'].get('repo_url')) or 
            (args.mode == 2 and config_data['mode2'].get('repo_url'))):
        print("错误: 必须指定Git仓库URL")
        sys.exit(1)
        
    # 根据命令行参数更新配置
    if args.mode:
        config_data['common']['mode'] = args.mode
        
    if args.target:
        config_data['common']['target_version'] = args.target
        
    if args.repo_url:
        # 处理repo_url并更新repo_path和repo_base_path
        base_repo_path, repo_path = handle_repo_url(args.repo_url, config_data)
        config_data['common']['repo_base_path'] = base_repo_path
        config_data['common']['repo_path'] = repo_path
        logger.info(f"更新repo_base_path为: {base_repo_path}")
        logger.info(f"更新repo_path为: {repo_path}")
        
        if args.mode == 1:
            # 模式1: 更新repo_url
            config_data['common']['repo_url'] = args.repo_url
        else:
            # 模式2: 更新repo_url
            config_data['mode2']['repo_url'] = args.repo_url
            
    if args.patch and args.mode == 1:
        # 如果提供的是commit hash而不是完整URL，需要构建完整URL
        if not args.patch.startswith('http'):
            # 从repo_url解析owner和repo
            from patch_utils import parse_github_url
            info = parse_github_url(args.repo_url)
            if info:
                patch_url = f"https://github.com/{info['owner']}/{info['repo']}/commit/{args.patch}.patch"
                config_data['mode1']['patch_url'] = patch_url
        else:
            config_data['mode1']['patch_url'] = args.patch
    
    
    
    # 保存更新后的配置
    try:
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False)
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        sys.exit(1)
    
    # 创建并运行工具
    tool = PatchBackportTool(config_path)
    tool.run()


if __name__ == "__main__":
    main()