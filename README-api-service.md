# 补丁适配服务 API

本文档介绍如何设置和使用补丁适配服务API，这是对现有补丁移植工具的HTTP服务包装层。

## 功能特点

- 通过HTTP API提供补丁适配功能
- 支持CVE数据库查询
- 任务管理与状态跟踪
- Docker容器化部署
- 提供REST风格的接口

## 安装与部署

### 环境要求

- Python 3.8+
- Git
- SQLite3
- Docker & Docker Compose (可选)

### 方法1: Docker部署

1. 复制环境变量示例文件并填写相关配置:

```bash
cp .env.example .env
# 编辑.env文件，填入API密钥等信息
```

2. 使用Docker Compose启动服务:

```bash
docker-compose up -d
```

服务将在 http://localhost:8000 上运行，数据库管理界面在 http://localhost:8001

### 方法2: 本地部署

1. 安装依赖:

```bash
pip install -r requirements.txt
pip install fastapi uvicorn pydantic
```

2. 创建必要的目录:

```bash
mkdir -p data logs cache workspace results
```

3. 复制环境变量示例文件并填写相关配置:

```bash
cp .env.example .env
# 编辑.env文件
```

4. 启动API服务:

```bash
python api_server.py
```

## API使用说明

API服务运行后，可通过以下方式使用:

### API文档

访问 http://localhost:8000/docs 查看交互式API文档(Swagger UI)

### 主要接口

#### 处理补丁

```
POST /api/patch/process
```

请求参数示例:

```json
{
  "patch_url": "https://github.com/linux-kernel/linux/commit/abc123.patch",
  "target_version": "5.10",
  "repo_path": "/path/to/repo",
  "cve_id": "CVE-2023-1234",
  "enabled_modules": ["direct_apply", "chunk_analyzer", "llm_adapter"]
}
```

响应示例:

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "任务已提交，正在处理中"
}
```

#### 查询任务状态

```
GET /api/task/{task_id}
```

响应示例:

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "message": "直接应用成功",
  "start_time": "2023-08-01T12:34:56",
  "end_time": "2023-08-01T12:36:20",
  "result_path": "/app/results/patch_550e8400.patch"
}
```

#### 获取CVE信息

```
GET /api/cve/{cve_id}
```

响应示例:

```json
{
  "cve_id": "CVE-2023-1234",
  "description": "Linux内核中的安全漏洞...",
  "affected_versions": ["5.10", "5.11", "5.12"],
  "fixed_versions": ["5.13", "5.14"],
  "patch_urls": ["https://github.com/linux-kernel/linux/commit/abc123.patch"],
  "severity": "高",
  "cwe_id": "CWE-123"
}
```

#### 添加CVE信息

```
POST /api/cve
```

请求参数示例:

```json
{
  "cve_id": "CVE-2023-5678",
  "description": "新发现的安全漏洞...",
  "affected_versions": ["5.15", "5.16"],
  "fixed_versions": ["5.17"],
  "patch_urls": ["https://github.com/linux-kernel/linux/commit/def456.patch"],
  "severity": "中",
  "cwe_id": "CWE-456"
}
```

#### 搜索CVE

```
GET /api/cve/search/{keyword}
```

## 配置说明

主要配置文件位于 `configs/service_config.yaml`，可配置项包括:

- 仓库路径
- 使用的AI模型
- 启用的处理模块
- 服务监听地址和端口
- 任务超时时间
- 日志配置
- 数据库设置
- 缓存配置

## 数据库管理

系统使用SQLite数据库存储CVE信息和任务状态，可通过以下方式管理:

1. 使用Docker Compose启动时，访问 http://localhost:8001 使用Web界面管理
2. 直接通过SQLite命令行工具:

```bash
sqlite3 data/cve_database.db
```

## 故障排除

常见问题及解决方案:

1. 服务无法启动
   - 检查环境变量和API密钥配置
   - 查看日志文件 `logs/api_service.log`

2. 补丁处理失败
   - 确保仓库路径正确可访问
   - 检查补丁URL是否有效
   - 在日志中查找详细错误信息

## 开发与扩展

想要扩展API服务功能:

1. 在`core/api_service.py`中添加新的路由和处理逻辑
2. 更新服务类`PatchAdaptationService`添加新方法
3. 修改数据库schema添加新表

## 许可证

与原项目相同的许可证 