#!/usr/bin/env python3
"""
自定义函数上下文提取测试脚本
此脚本允许用户测试从自己的文件中提取函数上下文
用法: python test_my_function_context.py <文件路径> <开始行号> <结束行号>
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from modules.llm_adapter import LLMAdapterModule

def extract_function_context(file_path, start_line, end_line):
    """从指定文件中提取函数上下文"""
    # 创建LLMAdapterModule实例
    config = {"repo_path": "/tmp"}
    module = LLMAdapterModule(config)
    
    # 读取文件内容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
    except Exception as e:
        print(f"读取文件时出错: {e}")
        return None
    
    # 提取函数上下文
    context = module._extract_function_context(file_content, start_line, end_line)
    return context

def extract_from_patch(file_path, patch_path):
    """从补丁文件中提取修改的行号，并获取函数上下文"""
    try:
        # 读取补丁文件
        with open(patch_path, 'r', encoding='utf-8') as f:
            patch_content = f.read()
        
        # 简单解析补丁获取行号（这是一个简化的实现）
        # 查找形如 @@ -123,5 +123,6 @@ 的行
        import re
        hunk_headers = re.findall(r'@@ -\d+,\d+ \+(\d+),\d+ @@', patch_content)
        
        if not hunk_headers:
            print("在补丁中未找到修改行号")
            return None
        
        # 使用第一个修改块的开始行号
        start_line = int(hunk_headers[0])
        
        # 简单估计结束行号（实际应用中可能需要更复杂的逻辑）
        # 这里假设修改只有几行
        end_line = start_line + 5
        
        # 提取函数上下文
        return extract_function_context(file_path, start_line, end_line)
    
    except Exception as e:
        print(f"处理补丁文件时出错: {e}")
        return None

def main():
    """主函数"""
    # 检查命令行参数
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <文件路径> [<开始行号> <结束行号> | <补丁文件路径>]")
        return 1
    
    file_path = sys.argv[1]
    
    # 判断是提供了行号还是补丁文件
    if len(sys.argv) == 3:
        # 假设提供的是补丁文件
        patch_path = sys.argv[2]
        print(f"使用补丁文件 {patch_path} 来分析 {file_path}")
        context = extract_from_patch(file_path, patch_path)
    elif len(sys.argv) >= 4:
        # 提供了开始和结束行号
        start_line = int(sys.argv[2])
        end_line = int(sys.argv[3])
        print(f"从 {file_path} 提取第 {start_line}-{end_line} 行所在的函数")
        context = extract_function_context(file_path, start_line, end_line)
    else:
        print("参数不足")
        return 1
    
    # 显示结果
    if context:
        print("\n提取的函数上下文:")
        print("="*80)
        print(context)
        print("="*80)
    else:
        print("未能提取函数上下文，可能指定的行不在函数内或文件格式不受支持")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 