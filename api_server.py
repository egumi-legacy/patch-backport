#!/usr/bin/env python3
"""
补丁适配服务 API 服务器启动脚本
"""
import os
import sys
import argparse
import yaml
from pathlib import Path
from loguru import logger

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# 导入API服务模块
from core.api_service import run_server

def load_config(config_path: str = "configs/service_config.yaml"):
    """加载配置文件"""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        # 使用默认配置
        return {
            "service": {
                "host": "0.0.0.0",
                "port": 8000,
                "debug": False,
                "log_level": "info",
                "workers": 4
            }
        }

def setup_logger(log_path: str = "logs/api_service.log", level: str = "INFO"):
    """设置日志配置"""
    # 创建日志目录
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # 配置日志格式和输出
    logger.remove()  # 移除默认处理器
    
    # 添加控制台处理器
    logger.add(
        sys.stdout, 
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level.upper()
    )
    
    # 添加文件处理器
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        compression="zip"
    )
    
    logger.info(f"API服务日志文件: {log_path}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="补丁适配服务API服务器")
    parser.add_argument('--config', '-c', type=str, default="configs/service_config.yaml",
                       help="配置文件路径 (默认: configs/service_config.yaml)")
    parser.add_argument('--host', type=str, help="主机地址")
    parser.add_argument('--port', type=int, help="端口号")
    parser.add_argument('--debug', action='store_true', help="启用调试模式")
    parser.add_argument('--log-level', type=str, choices=['debug', 'info', 'warning', 'error', 'critical'],
                        help="日志级别")
    
    args = parser.parse_args()
    
    # 加载配置
    config = load_config(args.config)
    service_config = config.get('service', {})
    
    # 命令行参数优先于配置文件
    host = args.host or service_config.get('host', '0.0.0.0')
    port = args.port or service_config.get('port', 8000)
    debug = args.debug or service_config.get('debug', False)
    log_level = args.log_level or service_config.get('log_level', 'info')
    
    # 设置日志
    log_path = config.get('logging', {}).get('api_log_path', 'logs/api_service.log')
    setup_logger(log_path, log_level)
    
    # 打印启动信息
    logger.info(f"API服务启动 - 监听: {host}:{port}")
    logger.info(f"调试模式: {'开启' if debug else '关闭'}")
    logger.info(f"日志级别: {log_level.upper()}")
    
    # 启动服务器
    run_server(host=host, port=port)

if __name__ == "__main__":
    main() 