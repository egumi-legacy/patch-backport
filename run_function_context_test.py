#!/usr/bin/env python3
"""
函数上下文提取测试运行器
此脚本运行专门针对_extract_function_context函数的单元测试，
并展示该函数如何从各种编程语言的文件中提取函数上下文。
"""

import os
import sys
import unittest
from pathlib import Path
import json

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 导入测试模块
from tests.test_extract_function_context import TestExtractFunctionContext
from modules.llm_adapter import LLMAdapterModule


def run_tests():
    """运行单元测试并返回结果"""
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestExtractFunctionContext)
    
    # 运行测试
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    
    return result


def show_function_example():
    """展示函数上下文提取的示例"""
    # 创建LLMAdapterModule实例
    config = {"repo_path": "/tmp"}
    module = LLMAdapterModule(config)
    
    # 示例C语言代码
    c_code = """
#include <stdio.h>

// 计算两个数的和
int add(int a, int b) {
    // 这是要修改的行
    int result = a + b;
    return result;
}

int main() {
    printf("Sum: %d\\n", add(5, 10));
    return 0;
}
"""
    
    # 提取修改行所在的函数上下文
    target_line = 6  # "int result = a + b;"
    function_context = module._extract_function_context(c_code, target_line, target_line)
    
    # 显示结果
    print("\n" + "="*80)
    print("示例: 从C代码中提取函数上下文")
    print("="*80)
    print("原始代码:")
    print(c_code)
    print("-"*80)
    print(f"目标修改行 ({target_line}): int result = a + b;")
    print("-"*80)
    print("提取的函数上下文:")
    print(function_context)
    print("="*80)


def main():
    """主函数"""
    print("运行函数上下文提取测试")
    print("="*80)
    
    # 运行测试
    result = run_tests()
    
    print("\n测试结果:")
    print(f"- 运行测试数: {result.testsRun}")
    print(f"- 成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"- 失败: {len(result.failures)}")
    print(f"- 错误: {len(result.errors)}")
    
    # 展示示例
    show_function_example()
    
    # 输出测试评估信息
    output_dir = Path("evaluations") / "function_context_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建测试评估文件
    assessment = {
        "测试总数": result.testsRun,
        "成功测试": result.testsRun - len(result.failures) - len(result.errors),
        "失败测试": len(result.failures),
        "错误测试": len(result.errors),
        "成功率": (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun if result.testsRun > 0 else 0,
        "测试描述": {
            "test_extract_c_function": "测试从C代码中提取函数上下文",
            "test_extract_python_function": "测试从Python代码中提取函数上下文",
            "test_extract_python_method": "测试从Python代码中提取类方法上下文",
            "test_extract_nested_function": "测试从Python代码中提取嵌套函数上下文",
            "test_extract_js_function": "测试从JavaScript代码中提取函数上下文",
            "test_extract_js_method": "测试从JavaScript代码中提取类方法上下文",
            "test_extract_js_arrow_function": "测试从JavaScript代码中提取箭头函数上下文",
        }
    }
    
    # 保存评估信息
    with open(output_dir / "test_assessment.json", "w", encoding="utf-8") as f:
        json.dump(assessment, f, indent=2, ensure_ascii=False)
    
    print(f"\n测试评估信息已保存到: {output_dir / 'test_assessment.json'}")
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main()) 