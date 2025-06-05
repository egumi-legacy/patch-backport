# Gitee Upstream Extractor

这个工具用于从Gitee提交URL中提取上游提交哈希。它可以处理单个或多个URL，支持从文件读取URL列表，并可以将结果输出到文件或控制台。

## 功能

- 从Gitee提交URL提取上游提交哈希
- 支持从文件读取URL列表
- 支持命令行直接输入URL
- 支持输出到文件或控制台
- 详细日志记录
- 支持详细模式，显示更多信息

## 安装

1. 确保已安装Python 3.6+
2. 安装依赖库：
```bash
pip install requests loguru python-dotenv
```

## 配置

创建一个`.env`文件，设置Gitee API令牌：

```
# Gitee API令牌
# 请在Gitee个人设置中生成令牌: https://gitee.com/profile/personal_access_tokens
# 确保令牌具有 projects 权限
GITEE_TOKEN=your_gitee_access_token_here
```

## 使用方法

### 从命令行输入URL

```bash
python gitee_upstream_extractor.py -u https://gitee.com/openeuler/kernel/commit/0c1bc63a96e15761181c880ba5c4f2adc33d6789
```

### 处理多个URL

```bash
python gitee_upstream_extractor.py -u https://gitee.com/openeuler/kernel/commit/0c1bc63a96e15761181c880ba5c4f2adc33d6789 https://gitee.com/openeuler/kernel/commit/another_commit_hash
```

### 从文件读取URL

```bash
python gitee_upstream_extractor.py -f urls.txt
```

文件格式示例（每行一个URL）：
```
https://gitee.com/openeuler/kernel/commit/0c1bc63a96e15761181c880ba5c4f2adc33d6789
https://gitee.com/openeuler/kernel/commit/another_commit_hash
```

### 输出到文件

```bash
python gitee_upstream_extractor.py -u https://gitee.com/openeuler/kernel/commit/0c1bc63a96e15761181c880ba5c4f2adc33d6789 -o results.txt
```

### 详细模式

```bash
python gitee_upstream_extractor.py -u https://gitee.com/openeuler/kernel/commit/0c1bc63a96e15761181c880ba5c4f2adc33d6789 -v
```

## 参数说明

- `-f, --file`: 包含Gitee提交URL的文件（每行一个URL）
- `-u, --urls`: Gitee提交URL列表
- `-o, --output`: 输出文件路径（默认输出到控制台）
- `-v, --verbose`: 显示详细信息

## 输出格式

### 默认模式

每行一个上游提交哈希：

```
a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
```

### 详细模式

包含原始提交哈希和上游提交哈希的映射：

```
0c1bc63a -> a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
another_c -> q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2

失败的URL:
https://gitee.com/openeuler/kernel/commit/invalid_hash - 未找到上游提交引用
```

## 日志

日志文件保存在`logs`目录下，格式为`gitee_extractor_[PID].log`。 