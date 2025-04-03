import unittest
import os
import sys
from pathlib import Path
import tempfile

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.llm_adapter import LLMAdapterModule

class TestExtractFunctionContext(unittest.TestCase):
    """测试提取函数上下文功能"""
    
    def setUp(self):
        """测试前准备"""
        # 创建一个简化的配置供LLMAdapterModule初始化使用
        self.config = {
            "repo_path": "/tmp"  # 仅用于初始化，测试中不会真正使用
        }
        
        # 创建模块实例
        self.module = LLMAdapterModule(self.config)
        
        # 用于测试的C语言示例
        self.c_code_sample = """
#include <stdio.h>
#include <stdlib.h>

// 一个简单的求和函数
int sum(int a, int b) {
    int result = a + b;
    return result;
}

/* 
 * 乘法函数
 * 用于计算两个数的乘积
 */
int multiply(int a, int b) {
    // 初始化结果
    int result = 0;
    
    // 使用累加实现乘法
    for (int i = 0; i < b; i++) {
        result += a;
    }
    
    return result;
}

// 主函数
int main() {
    int x = 5;
    int y = 10;
    
    printf("Sum: %d\\n", sum(x, y));
    printf("Product: %d\\n", multiply(x, y));
    
    return 0;
}
"""

        # 用于测试的Python示例
        self.python_code_sample = """#!/usr/bin/env python3
# 这是一个示例Python文件

import sys
import os

def calculate_sum(a, b):
    # 计算两个数的和
    result = a + b
    return result

class Calculator:
    def __init__(self, initial_value=0):
        self.value = initial_value
    
    def add(self, x):
        # 将x加到当前值上
        self.value += x
        return self.value
    
    def multiply(self, x):
        # 将当前值乘以x
        self.value *= x
        return self.value

# 嵌套函数的例子
def outer_function(x):
    def inner_function(y):
        return x + y
    
    return inner_function

if __name__ == "__main__":
    # 测试代码
    print(calculate_sum(5, 10))
    
    calc = Calculator(5)
    print(calc.add(10))
    print(calc.multiply(2))
"""

        # 用于测试的JavaScript示例
        self.js_code_sample = """// 这是一个JavaScript示例文件

/**
 * 计算两个数的和
 * @param {number} a - 第一个数
 * @param {number} b - 第二个数
 * @returns {number} 两数之和
 */
function sum(a, b) {
    return a + b;
}

// 一个计算器类
class Calculator {
    constructor(initialValue = 0) {
        this.value = initialValue;
    }
    
    // 加法方法
    add(x) {
        this.value += x;
        return this.value;
    }
    
    // 乘法方法
    multiply(x) {
        this.value *= x;
        return this.value;
    }
}

// 箭头函数示例
const subtract = (a, b) => {
    return a - b;
};

// 立即执行函数
(function() {
    const x = 5;
    const y = 10;
    console.log(`Sum: ${sum(x, y)}`);
    
    const calc = new Calculator(5);
    console.log(`After adding 10: ${calc.add(10)}`);
    console.log(`After multiplying by 2: ${calc.multiply(2)}`);
})();
"""

    def test_extract_c_function(self):
        """测试从C代码中提取函数上下文"""
        # 测试提取乘法函数
        multiply_start_line = 13  # 'int multiply(int a, int b) {'
        multiply_end_line = 17    # '    result += a;'
        multiply_context = self.module._extract_function_context(
            self.c_code_sample, multiply_start_line, multiply_end_line
        )
        
        # 验证提取结果
        self.assertIn("int multiply(int a, int b) {", multiply_context)
        self.assertIn("result += a;", multiply_context)
        self.assertIn("return result;", multiply_context)
        
        # 确保包含了整个函数，直到结束大括号
        self.assertIn("}", multiply_context.strip()[-1])
        
        # 确保不包含其他函数
        self.assertNotIn("int sum(int a, int b)", multiply_context)
        self.assertNotIn("int main()", multiply_context)
    
    def test_extract_python_function(self):
        """测试从Python代码中提取函数上下文"""
        # 测试提取calculate_sum函数
        sum_start_line = 7  # 'def calculate_sum(a, b):'
        sum_end_line = 8    # '    result = a + b'
        sum_context = self.module._extract_function_context(
            self.python_code_sample, sum_start_line, sum_end_line
        )
        
        # 验证提取结果
        self.assertIn("def calculate_sum(a, b):", sum_context)
        self.assertIn('"""计算两个数的和"""', sum_context)
        self.assertIn("result = a + b", sum_context)
        self.assertIn("return result", sum_context)
        
        # 确保不包含其他函数或类
        self.assertNotIn("class Calculator", sum_context)
    
    def test_extract_python_method(self):
        """测试从Python代码中提取类方法上下文"""
        # 测试提取Calculator.multiply方法
        multiply_start_line = 19  # '    def multiply(self, x):'
        multiply_end_line = 20    # '        """将当前值乘以x"""'
        multiply_context = self.module._extract_function_context(
            self.python_code_sample, multiply_start_line, multiply_end_line
        )
        
        # 验证提取结果
        self.assertIn("def multiply(self, x):", multiply_context)
        self.assertIn('"""将当前值乘以x"""', multiply_context)
        self.assertIn("self.value *= x", multiply_context)
        self.assertIn("return self.value", multiply_context)
        
        # 确保不包含其他方法
        self.assertNotIn("def add(self, x):", multiply_context)
    
    def test_extract_nested_function(self):
        """测试从Python代码中提取嵌套函数上下文"""
        # 测试提取outer_function的内部函数inner_function
        inner_start_line = 26  # '    def inner_function(y):'
        inner_end_line = 27    # '        return x + y'
        context = self.module._extract_function_context(
            self.python_code_sample, inner_start_line, inner_end_line
        )
        
        # 验证提取结果 - 应该包含外部函数和内部函数
        self.assertIn("def outer_function(x):", context)
        self.assertIn("def inner_function(y):", context)
        self.assertIn("return x + y", context)
        self.assertIn("return inner_function", context)
    
    def test_extract_js_function(self):
        """测试从JavaScript代码中提取函数上下文"""
        # 测试提取sum函数
        sum_start_line = 8  # 'function sum(a, b) {'
        sum_end_line = 9    # '    return a + b;'
        sum_context = self.module._extract_function_context(
            self.js_code_sample, sum_start_line, sum_end_line
        )
        
        # 验证提取结果
        self.assertIn("function sum(a, b) {", sum_context)
        self.assertIn("return a + b;", sum_context)
        self.assertIn("/**", sum_context)  # 应包含函数注释
        self.assertIn("@param", sum_context)  # 应包含参数文档
        
        # 确保不包含其他函数或类
        self.assertNotIn("class Calculator", sum_context)
    
    def test_extract_js_method(self):
        """测试从JavaScript代码中提取类方法上下文"""
        # 测试提取Calculator.multiply方法
        multiply_start_line = 24  # '    multiply(x) {'
        multiply_end_line = 25    # '        this.value *= x;'
        multiply_context = self.module._extract_function_context(
            self.js_code_sample, multiply_start_line, multiply_end_line
        )
        
        # 验证提取结果
        self.assertIn("multiply(x) {", multiply_context)
        self.assertIn("this.value *= x;", multiply_context)
        self.assertIn("return this.value;", multiply_context)
        self.assertIn("// 乘法方法", multiply_context)  # 应包含方法注释
        
        # 确保不包含其他方法
        self.assertNotIn("add(x) {", multiply_context)
    
    def test_extract_js_arrow_function(self):
        """测试从JavaScript代码中提取箭头函数上下文"""
        # 测试提取subtract箭头函数
        subtract_start_line = 31  # 'const subtract = (a, b) => {'
        subtract_end_line = 32    # '    return a - b;'
        subtract_context = self.module._extract_function_context(
            self.js_code_sample, subtract_start_line, subtract_end_line
        )
        
        # 验证提取结果
        self.assertIn("const subtract = (a, b) => {", subtract_context)
        self.assertIn("return a - b;", subtract_context)
        self.assertIn("// 箭头函数示例", subtract_context)  # 应包含函数注释
        
        # 确保不包含其他函数
        self.assertNotIn("function sum", subtract_context)
    
    def test_start_line_equals_end_line(self):
        """测试当开始行等于结束行的情况"""
        line = 8  # 'return a + b;' 在js示例中
        context = self.module._extract_function_context(
            self.js_code_sample, line, line
        )
        
        # 验证仍然提取了整个函数
        self.assertIn("function sum(a, b) {", context)
        self.assertIn("return a + b;", context)
        self.assertIn("}", context)
    
    def test_out_of_bounds_lines(self):
        """测试行号超出范围的情况"""
        # 测试开始行为0的情况
        context = self.module._extract_function_context(
            self.c_code_sample, 0, 5
        )
        self.assertIsNone(context)
        
        # 测试结束行超出文件总行数的情况
        total_lines = len(self.c_code_sample.split('\n'))
        context = self.module._extract_function_context(
            self.c_code_sample, 10, total_lines + 10
        )
        self.assertIsNone(context)
    
    def test_invalid_code(self):
        """测试处理无效代码的情况"""
        # 空文件
        context = self.module._extract_function_context("", 1, 2)
        self.assertIsNone(context)
        
        # 只有注释的文件
        comments_only = "// 这只是一个注释\n/* 另一个注释 */"
        context = self.module._extract_function_context(comments_only, 1, 1)
        self.assertIsNone(context)
    
    def test_lines_not_in_function(self):
        """测试行号不在任何函数内的情况"""
        # 测试指向文件顶部导入语句的行
        import_line = 4  # 'import sys' 在python示例中
        context = self.module._extract_function_context(
            self.python_code_sample, import_line, import_line
        )
        
        # 应该返回None或者有限的上下文
        if context is not None:
            self.assertNotIn("def ", context)  # 不应该包含任何函数定义
    
    def test_unclosed_braces(self):
        """测试处理未闭合括号的情况"""
        # 创建一个包含未闭合括号的代码示例
        unclosed_code = """
function badFunction() {
    if (true) {
        console.log("This is bad");
        // 缺少右括号
    }
// 缺少右括号
        """
        
        # 测试是否能正确处理
        context = self.module._extract_function_context(
            unclosed_code, 3, 3
        )
        
        # 应该仍然尝试提取整个函数
        if context is not None:
            self.assertIn("function badFunction()", context)
    
    def test_trailing_code_extraction(self):
        """测试正确处理尾随代码和注释的情况"""
        # 创建一个在函数后有额外代码和注释的示例
        code_with_trailing = """
function testFunction() {
    return "test";
} // 函数结束

// 一些注释
const x = 10;
        """
        
        context = self.module._extract_function_context(
            code_with_trailing, 2, 2
        )
        
        # 应该只包含函数定义，不包含后面的注释和代码
        self.assertIn("function testFunction()", context)
        self.assertIn("return \"test\";", context)
        self.assertNotIn("const x = 10;", context)

if __name__ == '__main__':
    unittest.main() 