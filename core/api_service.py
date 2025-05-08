from fastapi import FastAPI, HTTPException, BackgroundTasks, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional, Union
import yaml
import os
import json
import sqlite3
from pathlib import Path
import logging
from datetime import datetime
import asyncio
import uuid
import time
import uvicorn
from loguru import logger
import dotenv

from core.parameter_manager import BaseConfig, Mode1Config
from core.adaptation_pipeline import AdaptationPipeline
from core.parameter_manager import ModuleContext, CommitContext

class PatchRequest(BaseModel):
    """补丁处理请求模型"""
    patch_url: str = Field(..., description="补丁URL")
    target_version: Union[str, List[str]] = Field(..., description="目标版本，可以是字符串或字符串列表")
    repo_path: Optional[str] = Field(None, description="仓库路径，如果为空则使用配置中的默认值")
    cve_id: Optional[str] = Field(None, description="CVE ID，用于查询漏洞信息")
    enabled_modules: Optional[List[str]] = Field(None, description="启用的模块列表")

class CVEInfo(BaseModel):
    """CVE信息模型"""
    cve_id: str
    description: str
    affected_versions: List[str]
    fixed_versions: List[str]
    patch_urls: List[str]
    severity: Optional[str] = None
    cwe_id: Optional[str] = None

class TaskStatus(BaseModel):
    """任务状态模型"""
    task_id: str
    status: str
    message: Optional[str] = None
    start_time: str
    end_time: Optional[str] = None
    result_path: Optional[str] = None
    
class PatchAdaptationService:
    """补丁适配服务类"""
    def __init__(self, config_path: str = "configs/service_config.yaml", db_path: str = "data/cve_database.db"):
        """初始化补丁适配服务"""
        dotenv.load_dotenv()
        self.config_path = config_path
        self.db_path = db_path
        self._load_config()
        self._init_database()
        self.tasks = {}
        
    def _load_config(self):
        """加载服务配置"""
        # 确保配置文件存在
        config_file = Path(self.config_path)
        if not config_file.exists():
            logger.info(f"配置文件 {self.config_path} 不存在，使用默认配置")
            self.config = {
                "repo_path": "../backport-test/linux",
                "model": "qwen-plus",
                "enabled_modules": [
                    "direct_apply", 
                    "chunk_analyzer", 
                    "llm_adapter", 
                    "patch_adapter"
                ],
                "task_timeout": 3600,  # 任务超时时间（秒）
                "max_concurrent_tasks": 3,
                "result_retention_days": 7,
                "api_log_path": "logs/api_service.log"
            }
            # 创建默认配置文件
            os.makedirs(config_file.parent, exist_ok=True)
            with open(config_file, 'w') as f:
                yaml.dump(self.config, f)
        else:
            with open(config_file, 'r') as f:
                self.config = yaml.safe_load(f)
                
        # 确保数据目录存在
        os.makedirs(Path(self.db_path).parent, exist_ok=True)
    
    def _init_database(self):
        """初始化CVE数据库"""
        # 如果数据库不存在，创建它
        if not Path(self.db_path).exists():
            logger.info(f"数据库 {self.db_path} 不存在，创建新数据库")
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 创建CVE表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS cve (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cve_id TEXT UNIQUE,
                description TEXT,
                severity TEXT,
                cwe_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # 创建受影响版本表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS affected_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cve_id TEXT,
                version TEXT,
                FOREIGN KEY (cve_id) REFERENCES cve(cve_id),
                UNIQUE(cve_id, version)
            )
            ''')
            
            # 创建修复版本表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS fixed_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cve_id TEXT,
                version TEXT,
                FOREIGN KEY (cve_id) REFERENCES cve(cve_id),
                UNIQUE(cve_id, version)
            )
            ''')
            
            # 创建补丁URL表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS patch_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cve_id TEXT,
                url TEXT,
                FOREIGN KEY (cve_id) REFERENCES cve(cve_id),
                UNIQUE(cve_id, url)
            )
            ''')
            
            # 创建任务记录表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT,
                message TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                result_path TEXT,
                patch_url TEXT,
                target_version TEXT,
                cve_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            conn.commit()
            conn.close()
    
    def get_cve_info(self, cve_id: str) -> Optional[CVEInfo]:
        """从数据库获取CVE信息"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取CVE基本信息
        cursor.execute('''
        SELECT * FROM cve WHERE cve_id = ?
        ''', (cve_id,))
        cve_record = cursor.fetchone()
        
        if not cve_record:
            conn.close()
            return None
        
        # 获取受影响版本
        cursor.execute('''
        SELECT version FROM affected_versions WHERE cve_id = ?
        ''', (cve_id,))
        affected_versions = [row['version'] for row in cursor.fetchall()]
        
        # 获取修复版本
        cursor.execute('''
        SELECT version FROM fixed_versions WHERE cve_id = ?
        ''', (cve_id,))
        fixed_versions = [row['version'] for row in cursor.fetchall()]
        
        # 获取补丁URL
        cursor.execute('''
        SELECT url FROM patch_urls WHERE cve_id = ?
        ''', (cve_id,))
        patch_urls = [row['url'] for row in cursor.fetchall()]
        
        conn.close()
        
        return CVEInfo(
            cve_id=cve_id,
            description=cve_record['description'],
            affected_versions=affected_versions,
            fixed_versions=fixed_versions,
            patch_urls=patch_urls,
            severity=cve_record['severity'],
            cwe_id=cve_record['cwe_id']
        )
    
    def add_cve_info(self, cve_info: CVEInfo) -> bool:
        """添加CVE信息到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 添加CVE基本信息
            cursor.execute('''
            INSERT OR REPLACE INTO cve (cve_id, description, severity, cwe_id)
            VALUES (?, ?, ?, ?)
            ''', (cve_info.cve_id, cve_info.description, cve_info.severity, cve_info.cwe_id))
            
            # 添加受影响版本
            for version in cve_info.affected_versions:
                cursor.execute('''
                INSERT OR IGNORE INTO affected_versions (cve_id, version)
                VALUES (?, ?)
                ''', (cve_info.cve_id, version))
            
            # 添加修复版本
            for version in cve_info.fixed_versions:
                cursor.execute('''
                INSERT OR IGNORE INTO fixed_versions (cve_id, version)
                VALUES (?, ?)
                ''', (cve_info.cve_id, version))
            
            # 添加补丁URL
            for url in cve_info.patch_urls:
                cursor.execute('''
                INSERT OR IGNORE INTO patch_urls (cve_id, url)
                VALUES (?, ?)
                ''', (cve_info.cve_id, url))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"添加CVE信息失败: {e}")
            conn.rollback()
            conn.close()
            return False
    
    def search_cve(self, keyword: str) -> List[CVEInfo]:
        """搜索包含指定关键字的CVE信息"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 搜索包含关键字的CVE ID或描述
        cursor.execute('''
        SELECT cve_id FROM cve 
        WHERE cve_id LIKE ? OR description LIKE ?
        ''', (f'%{keyword}%', f'%{keyword}%'))
        
        results = []
        for row in cursor.fetchall():
            cve_id = row['cve_id']
            cve_info = self.get_cve_info(cve_id)
            if cve_info:
                results.append(cve_info)
        
        conn.close()
        return results
    
    def process_patch(self, request: PatchRequest) -> str:
        """处理补丁请求并返回任务ID"""
        task_id = str(uuid.uuid4())
        start_time = datetime.now().isoformat()
        
        # 创建任务记录
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO tasks (task_id, status, start_time, patch_url, target_version, cve_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            task_id, 
            'pending', 
            start_time, 
            request.patch_url, 
            json.dumps(request.target_version) if isinstance(request.target_version, list) else request.target_version,
            request.cve_id
        ))
        conn.commit()
        conn.close()
        
        # 记录任务
        self.tasks[task_id] = {
            'status': 'pending',
            'start_time': start_time,
            'request': request.dict()
        }
        
        # 启动后台任务
        asyncio.create_task(self._execute_task(task_id, request))
        
        return task_id
    
    async def _execute_task(self, task_id: str, request: PatchRequest):
        """执行补丁适配任务"""
        try:
            # 更新任务状态为运行中
            self._update_task_status(task_id, 'running')
            
            # 准备配置
            config_dict = {
                'mode': 1,
                'repo_path': request.repo_path or self.config['repo_path'],
                'target_version': request.target_version,
                'enabled_modules': request.enabled_modules or self.config['enabled_modules'],
                'model': self.config['model'],
                'patch_url': request.patch_url,
                'use_cached_patches': True,
                'prompt_template_file': "configs/test_prompts.json",
                'prompt_id': "backport"
            }
            
            # CVE信息处理
            if request.cve_id:
                cve_info = self.get_cve_info(request.cve_id)
                if cve_info:
                    # 如果未指定目标版本，使用CVE中的受影响版本
                    if not request.target_version:
                        config_dict['target_version'] = cve_info.affected_versions
            
            # 创建配置对象
            config = Mode1Config(**config_dict)
            
            # 创建提交上下文
            commit_context = CommitContext.create_for_mode1(config)
            
            # 创建模块上下文
            context = ModuleContext(
                config=config,
                commit=commit_context
            )
            
            # 创建处理流水线
            pipeline = AdaptationPipeline(config)
            
            # 处理补丁
            processed_context = pipeline.process_patch(context)
            
            # 分析结果
            result_path = None
            success = False
            message = ""
            
            # 检查不同模块的处理结果
            if processed_context.direct_apply_result and processed_context.direct_apply_result.get('success'):
                success = True
                message = "直接应用成功"
                result_path = processed_context.direct_apply_result.get('patch_path')
            elif processed_context.chunk_analyzer_result and processed_context.chunk_analyzer_result.get('success'):
                success = True
                message = "块分析应用成功"
                # 获取所有应用成功的块
                result_path = "|".join(processed_context.chunk_analyzer_result.get('applied_chunk_patches', []))
            elif processed_context.patch_adapter_result and processed_context.patch_adapter_result.get('success'):
                success = True
                message = "补丁适配成功"
                result_path = processed_context.patch_adapter_result.get('adapted_patch_path')
            else:
                success = False
                message = processed_context.last_error or "所有适配方法失败"
            
            # 更新任务状态
            self._update_task_status(
                task_id, 
                'completed' if success else 'failed',
                message=message,
                result_path=result_path,
                end_time=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"任务 {task_id} 执行失败: {e}")
            self._update_task_status(
                task_id, 
                'failed', 
                message=str(e),
                end_time=datetime.now().isoformat()
            )
    
    def _update_task_status(self, task_id: str, status: str, message: str = None, result_path: str = None, end_time: str = None):
        """更新任务状态"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        update_fields = ['status']
        update_values = [status]
        
        if message:
            update_fields.append('message')
            update_values.append(message)
        
        if result_path:
            update_fields.append('result_path')
            update_values.append(result_path)
        
        if end_time:
            update_fields.append('end_time')
            update_values.append(end_time)
        
        update_query = f'''
        UPDATE tasks SET {', '.join(f'{field} = ?' for field in update_fields)}
        WHERE task_id = ?
        '''
        
        cursor.execute(update_query, update_values + [task_id])
        conn.commit()
        conn.close()
        
        # 更新内存中的任务记录
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = status
            if message:
                self.tasks[task_id]['message'] = message
            if result_path:
                self.tasks[task_id]['result_path'] = result_path
            if end_time:
                self.tasks[task_id]['end_time'] = end_time
    
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM tasks WHERE task_id = ?
        ''', (task_id,))
        
        task = cursor.fetchone()
        conn.close()
        
        if not task:
            return None
        
        return TaskStatus(
            task_id=task['task_id'],
            status=task['status'],
            message=task['message'],
            start_time=task['start_time'],
            end_time=task['end_time'],
            result_path=task['result_path']
        )

    def get_recent_tasks(self, limit: int = 10) -> List[TaskStatus]:
        """获取最近的任务列表"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM tasks
        ORDER BY created_at DESC
        LIMIT ?
        ''', (limit,))
        
        tasks = []
        for row in cursor.fetchall():
            tasks.append(TaskStatus(
                task_id=row['task_id'],
                status=row['status'],
                message=row['message'],
                start_time=row['start_time'],
                end_time=row['end_time'],
                result_path=row['result_path']
            ))
        
        conn.close()
        return tasks

# 创建API实例
app = FastAPI(title="补丁适配服务API", description="提供补丁适配、CVE查询等功能")
service = PatchAdaptationService()

# 添加跨域支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/patch/process", response_model=Dict[str, str])
async def process_patch(request: PatchRequest, background_tasks: BackgroundTasks):
    """处理补丁请求"""
    task_id = service.process_patch(request)
    return {"task_id": task_id, "message": "任务已提交，正在处理中"}

@app.get("/api/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """获取任务状态"""
    status = service.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return status

@app.get("/api/tasks/recent", response_model=List[TaskStatus])
async def get_recent_tasks(limit: int = 10):
    """获取最近的任务列表"""
    return service.get_recent_tasks(limit)

@app.get("/api/cve/{cve_id}", response_model=CVEInfo)
async def get_cve_info(cve_id: str):
    """获取CVE信息"""
    info = service.get_cve_info(cve_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"CVE {cve_id} 不存在")
    return info

@app.post("/api/cve", response_model=Dict[str, bool])
async def add_cve_info(cve_info: CVEInfo):
    """添加CVE信息"""
    success = service.add_cve_info(cve_info)
    return {"success": success}

@app.get("/api/cve/search/{keyword}", response_model=List[CVEInfo])
async def search_cve(keyword: str):
    """搜索CVE信息"""
    return service.search_cve(keyword)

@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """运行API服务器"""
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    run_server() 