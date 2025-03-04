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
        """处理模式1: 单个补丁"""
        # # 从补丁URL提取仓库信息
        # url_info = parse_github_url(self.config.patch_url)
        # if not url_info:
        #     raise ValueError(f"无法解析补丁URL: {self.config.patch_url}")
            
        # 提取补丁信息
        # patch_info = {
        #     'commit_sha': self.config.commit_sha,
        #     'patch_url': self.config.patch_url,
        #     'repo_owner': url_info['owner'],
        #     'repo_name': url_info['repo'],
        #     'base_dir': Path("workspace") / f"{url_info['owner']}_{url_info['repo']}" / self.config.commit_sha[:8],
        #     'repo_path': self.config.repo_path if hasattr(self.config, 'repo_path') else Path.cwd()
        # }
        
        # 创建提交上下文
        commit_context = CommitContext.create_for_mode1(self.config)
        
        # 创建模块上下文
        context = ModuleContext(
            config=self.config,
            commit=commit_context
        )
        
        # 创建处理流水线
        pipeline = AdaptationPipeline(self.config)
        
        # 处理补丁
        context = pipeline.process_patch(context)
        
        # 保存结果
        self._save_results(context)
        
        # 打印摘要
        self._print_summary(context)
    
    def _process_mode2(self):
        """处理模式2: 多个补丁"""
        # 获取 commits 提交列表（包含上下游提交）
        commits_list = self._get_commits_list()
        logger.info(f"找到 {len(commits_list)} 个上游提交")
        
        # 创建处理流水线
        pipeline = AdaptationPipeline(self.config)
        
        # 统计变量
        start = 12
        end = 13
        total_commits = len(commits_list[start:end])
        successful_commits = 0
        failed_commits = []
        
        # 处理每个提交
        for idx, commit_info in enumerate(commits_list[start:end], start+1):
            upstream_sha = commit_info['upstream_sha']
            logger.info(f"处理提交 {idx}/{total_commits}: {upstream_sha[:6]}")
            
            # 创建提交上下文
            commit_context = CommitContext.create_for_mode2(self.config, commit_info)
            
            # 创建模块上下文
            context = ModuleContext(
                config=self.config,
                commit=commit_context
            )
            
            # 处理补丁
            context = pipeline.process_patch(context)
            
            # 保存结果
            self._save_results(context)
            
            # 打印摘要
            self._print_summary(context)
            
            # 更新统计
            direct_success = bool(context.direct_apply_result and context.direct_apply_result.get('success'))
            llm_success = bool(context.adapted_patches)
            
            if direct_success or llm_success:
                successful_commits += 1
            else:
                failed_commits.append({
                    'sha': upstream_sha[:6],
                    'error': context.last_error
                })
        
        # 打印总体统计
        self._print_mode2_statistics(total_commits, successful_commits, failed_commits)
    
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
        result_dir = Path("results") / f"{self.config.target_version}_{commit_sha}_{timestamp}"
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
        
        # 保存上下文信息
        result = {
            'commit': commit_info,
            'config': {
                'mode': self.config.mode,
                'target_version': self.config.target_version,
                'enabled_modules': self.config.enabled_modules
            },
            'results': {
                'direct_apply': context.direct_apply_result,
                # 'llm_response': {
                #     'status': context.llm_response.get('status') if context.llm_response else None,
                #     'timestamp': context.llm_response.get('timestamp') if context.llm_response else None,
                #     'response_path': context.llm_response.get('response_path') if context.llm_response else None
                # } if context.llm_response else None,
                # 'adapted_patches': [
                #     {
                #         'file': patch.get('file'),
                #         'success': patch.get('success')
                #     } for patch in context.adapted_patches
                # ] if context.adapted_patches else [],
                'last_error': context.last_error
            },
            'summary': {
                'success': bool(context.direct_apply_result and context.direct_apply_result.get('success')) or
                          bool(context.adapted_patches),
                'method': 'direct_apply' if (context.direct_apply_result and 
                                           context.direct_apply_result.get('success')) else 'llm_adapted',
                'timestamp': datetime.now().isoformat()
            }
        }
        
        # 保存结果JSON
        result_file = result_dir / "result.json"
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        # 复制关键文件
        if context.direct_apply_result and context.direct_apply_result.get('patch_path'):
            patch_path = Path(context.direct_apply_result.get('patch_path'))
            if patch_path.exists():
                shutil.copy(patch_path, result_dir / "original.patch")
        
        # if context.llm_response and context.llm_response.get('response_path'):
        #     response_path = Path(context.llm_response.get('response_path'))
        #     if response_path.exists():
        #         shutil.copy(response_path, result_dir / "llm_response.patch")
        
        logger.info(f"结果已保存到: {result_file}")
        return result_dir
    
    def _print_summary(self, context: ModuleContext):
        """打印处理摘要"""
        commit_sha = context.commit.commit_sha[:6]
        
        # 确定处理结果
        direct_success = bool(context.direct_apply_result and context.direct_apply_result.get('success'))
        llm_success = bool(context.llm_output and context.llm_output.get('success'))
        logger.info(f"context.patch_adapter_result: {context.patch_adapter_result}")
        patch_adapter_success = bool(context.patch_adapter_result and context.patch_adapter_result.get('success'))
        
        
        if direct_success:
            result = "直接应用成功"
            method = "direct_apply"
        elif llm_success:
            result = "LLM适配成功"
            method = "llm_adapter"
        elif patch_adapter_success:
            result = "补丁适配成功"
            method = "patch_adapter"
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

    def _print_mode2_statistics(self, total, successful, failed_commits):
        """打印模式2的统计信息"""
        success_rate = (successful / total) * 100 if total > 0 else 0
        
        # 从上下文中提取处理方法信息 (不使用不存在的self.processed_commits属性)
        direct_apply_count = 0
        patch_adapter_count = 0
        llm_adapter_count = 0
        failed_count = len(failed_commits)
        
        # 从result.json文件中获取详细信息
        results_dir = Path("results")
        if results_dir.exists():
            # 遍历results目录下的所有结果文件
            for result_dir in results_dir.iterdir():
                if not result_dir.is_dir() or not (result_dir / "result.json").exists():
                    continue
                    
                with open(result_dir / "result.json", "r") as f:
                    result_data = json.load(f)
                    
                # 检查处理方法
                if "summary" in result_data and "method" in result_data["summary"]:
                    method = result_data["summary"]["method"]
                    if method == "direct_apply":
                        direct_apply_count += 1
                    elif method == "patch_adapter":
                        patch_adapter_count += 1
                    elif method == "llm_adapter":
                        llm_adapter_count += 1
        
        # 计算适配成功率（排除直接应用成功的情况）
        adapt_required = total - direct_apply_count
        adapt_successful = patch_adapter_count + llm_adapter_count
        adapt_success_rate = (adapt_successful / adapt_required) * 100 if adapt_required > 0 else 0
        
        logger.info("=" * 60)
        logger.info(f"模式2处理统计")
        logger.info("=" * 60)
        logger.info(f"总提交数: {total}")
        logger.info(f"直接应用成功: {direct_apply_count}")
        logger.info(f"需要适配数量: {adapt_required}")
        logger.info(f"适配成功数量: {adapt_successful}")
        logger.info(f"- 补丁适配成功: {patch_adapter_count}")
        logger.info(f"- LLM适配成功: {llm_adapter_count}")
        logger.info(f"适配失败数量: {failed_count}")
        logger.info(f"总体成功率: {success_rate:.2f}%")
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
            'direct_apply_success': direct_apply_count,
            'adaptation_required': adapt_required,
            'adaptation_successful': adapt_successful,
            'patch_adapter_success': patch_adapter_count,
            'llm_adapter_success': llm_adapter_count,
            'failed_commits': failed_count,
            'overall_success_rate': success_rate,
            'adaptation_success_rate': adapt_success_rate,
            'failed_details': failed_commits
        }
        
        with open(stats_file, 'w') as f:
            json.dump(stats_data, f, indent=2)
        
        logger.info(f"统计结果已保存到: {stats_file}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="补丁移植工具")
    parser.add_argument('--config', '-c', type=str, default="configs/new_inputs.yaml",
                       help="配置文件路径 (默认: configs/new_inputs.yaml)")
    args = parser.parse_args()
    
    # 创建并运行工具
    tool = PatchBackportTool(args.config)
    tool.run()


if __name__ == "__main__":
    main()