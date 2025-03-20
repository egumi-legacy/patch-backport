#!/usr/bin/env python3
import argparse
import json
import yaml
import os
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger
import pprint

# 第三方库
import dotenv

# 本地模块
from core.parameter_manager import Mode1Config, CommitContext, ModuleContext
from modules.backtrack_apply import BacktrackApplyModule
from patch_utils import parse_github_url

def setup_logger(log_level='INFO'):
    """设置日志"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"backtrack_{timestamp}.log"
    
    # 配置日志格式和输出
    logger.remove()  # 移除默认处理器
    
    # 添加控制台处理器
    logger.add(
        sys.stdout, 
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level
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

def create_config_from_args(args):
    """从命令行参数创建配置"""
    # 解析补丁URL
    info = parse_github_url(args.patch_url)
    if not info:
        raise ValueError(f"无法解析补丁URL: {args.patch_url}")
    
    # 创建基础配置
    config_dict = {
        'mode': 1,
        'repo_path': args.repo_path,
        'target_version': args.target_version or 'HEAD',
        'enabled_modules': ['backtrack_apply'],
        'patch_url': args.patch_url,
        'repo_name': info['repo'],
        'repo_owner': info['owner'],
        'commit_sha': info['commit_sha'],
        'module_configs': {
            'backtrack_apply': {
                'stop_at': args.stop_at,
                'max_attempts': args.max_attempts
            }
        }
    }
    
    # 创建配置对象
    return Mode1Config(**config_dict)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="回溯补丁应用工具")
    parser.add_argument('--patch-url', '-p', required=True, help='补丁URL')
    parser.add_argument('--repo-path', '-r', required=True, help='本地仓库路径')
    parser.add_argument('--target-version', '-t', help='目标版本（分支或标签）')
    parser.add_argument('--stop-at', '-s', help='停止点（分支、标签或提交哈希）')
    parser.add_argument('--max-attempts', '-m', type=int, default=50, help='最大尝试次数')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    # 设置日志级别
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger(log_level)
    
    try:
        # 加载环境变量
        dotenv.load_dotenv()
        
        # 创建配置
        config = create_config_from_args(args)
        logger.debug(f"配置: {config}")
        
        # 创建上下文
        commit_context = CommitContext.create_for_mode1(config)
        context = ModuleContext(config=config, commit=commit_context)
        
        # 创建模块
        module = BacktrackApplyModule(config)
        
        # 执行回溯
        logger.info(f"开始回溯应用补丁: {config.patch_url}")
        result_context = module.execute(context)
        
        # 显示结果
        if result_context.backtrack_result:
            if result_context.backtrack_result['success']:
                logger.info("回溯应用成功!")
                logger.info(f"补丁可以应用于版本: {result_context.backtrack_result['applicable_version']}")
                logger.info(f"尝试次数: {result_context.backtrack_result['attempt_count']}")
            else:
                logger.error("回溯应用失败!")
                logger.error(f"错误: {result_context.backtrack_result['error']}")
                logger.error(f"尝试次数: {result_context.backtrack_result.get('attempt_count', 0)}")
            
            # 保存结果
            result_dir = Path("results")
            result_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            commit_sha = config.commit_sha[:6]
            result_file = result_dir / f"backtrack_{commit_sha}_{timestamp}.json"
            
            with open(result_file, 'w') as f:
                json.dump(result_context.backtrack_result, f, indent=2)
            
            logger.info(f"结果已保存到: {result_file}")
        
    except Exception as e:
        logger.error(f"执行过程发生错误: {e}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 