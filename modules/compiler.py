from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from loguru import logger
import json
import os
import re
import subprocess
import traceback
from datetime import datetime
import shutil
from .base_module import BaseModule, ModuleType
from core.parameter_manager import ModuleContext

class CompilerModule(BaseModule):
    """编译模块 - 对适配后的文件进行单文件编译测试"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.type = ModuleType.COMPILER
        self.name = "compiler"
        self.metrics = {
            'total_attempts': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'execution_time': 0,
            'compilation_success': 0,
            'compilation_failures': 0,
            'retries': 0,
            'error_types': {},
            'compiled_files': []
        }
    
    def execute(self, context: ModuleContext) -> ModuleContext:
        """执行编译测试"""
        if not self._should_run(context):
            return context
            
        start_time = datetime.now()
        self.metrics['total_attempts'] += 1
        
        try:
            # 确保补丁适配结果存在
            if not hasattr(context, 'patch_adapter_result') or not context.patch_adapter_result:
                logger.warning("缺少补丁适配结果，跳过编译测试")
                self._update_metrics(False, error_type="MissingAdapterResult")
                self._save_metrics(context)
                return context
            
            # 检查补丁适配是否成功
            if not context.patch_adapter_result.get('success', False):
                logger.warning("补丁适配失败，跳过编译测试")
                self._update_metrics(False, error_type="AdapterFailed")
                self._save_metrics(context)
                return context

            # 创建编译目录
            compile_dir = self._create_compile_dir(context)
            
            # 获取需要编译的文件列表
            files_to_compile = self._get_modified_files(context)
            if not files_to_compile:
                logger.warning("没有找到需要编译的文件")
                self._update_metrics(True, compiled_success=True)
                self._save_metrics(context)
                return context
            
            # 编译每个文件并收集结果
            compilation_results = []
            overall_success = True
            
            for file_path in files_to_compile:
                result = self._compile_file(context, file_path)
                compilation_results.append(result)
                
                if not result['success']:
                    overall_success = False
                    
                    # 如果配置了失败重试，则进行重试
                    if context.config.retry_with_feedback and not result.get('retried', False):
                        retry_result = self._retry_with_feedback(context, result)
                        if retry_result:
                            # 替换原来的结果
                            compilation_results[-1] = retry_result
                            if retry_result['success']:
                                # 如果重试成功，重新评估整体成功状态
                                overall_success = all(r['success'] for r in compilation_results)
                
                # 如果配置了失败停止，则中断
                if not result['success'] and context.config.stop_on_failure:
                    logger.info("编译失败，且配置为停止于失败，中断编译")
                    break
            
            # 更新上下文和指标
            context.compilation_result = {
                'success': overall_success,
                'results': compilation_results,
                'compile_dir': str(compile_dir)
            }
            
            self._update_metrics(True, 
                              compiled_success=overall_success,
                              compilation_results=compilation_results,
                              execution_time=(datetime.now() - start_time).total_seconds())
            
            self._save_metrics(context)
            return context
            
        except Exception as e:
            logger.error(f"编译测试过程发生错误: {str(e)}")
            if self.verbose:
                logger.error(f"错误堆栈: {traceback.format_exc()}")
            
            # 更新上下文和指标
            error_type = type(e).__name__
            self._update_metrics(False, error_type=error_type, 
                               execution_time=(datetime.now() - start_time).total_seconds())
            
            context.compilation_result = {
                'success': False,
                'error': str(e)
            }
            
            self._save_metrics(context)
            return context
    
    def _create_compile_dir(self, context: ModuleContext) -> Path:
        """创建编译目录"""
        compile_dir = context.commit.base_dir / "compilation"
        compile_dir.mkdir(parents=True, exist_ok=True)
        return compile_dir
    
    def _get_modified_files(self, context: ModuleContext) -> List[Path]:
        """获取已修改的文件列表"""
        modified_files = []
        
        # 从适配目录中查找修改的文件
        adapted_dir = context.commit.base_dir / f"adapted_{context.config.target_version}"
        if adapted_dir.exists():
            for file_path in adapted_dir.glob('**/*'):
                if file_path.is_file():
                    # 获取相对路径
                    rel_path = file_path.relative_to(adapted_dir)
                    # 检查源文件是否存在
                    source_file = context.commit.base_dir / context.config.target_version / rel_path
                    if source_file.exists():
                        modified_files.append(rel_path)
        
        # 也可以从patch文件中获取修改的文件列表
        if context.patch_adapter_result.get('adapted_patch_path'):
            patch_path = Path(context.patch_adapter_result['adapted_patch_path'])
            if patch_path.exists():
                try:
                    with open(patch_path, 'r') as f:
                        patch_content = f.read()
                    
                    # 从patch内容中提取文件路径
                    file_paths = set()
                    for line in patch_content.splitlines():
                        if line.startswith('diff --git'):
                            parts = line.split()
                            if len(parts) >= 4:
                                a_file = parts[2][2:]  # 去掉a/
                                file_paths.add(a_file)
                    
                    # 添加到修改文件列表
                    for file_path in file_paths:
                        path = Path(file_path)
                        if path not in modified_files:
                            modified_files.append(path)
                except Exception as e:
                    logger.warning(f"从patch文件获取修改列表失败: {str(e)}")
        
        return modified_files
    
    def _compile_file(self, context: ModuleContext, file_path: Path) -> Dict[str, Any]:
        """编译单个文件"""
        result = {
            'file': str(file_path),
            'success': False,
            'command': '',
            'output': '',
            'error': None
        }
        
        # 确定编译命令
        build_command = self._determine_build_command(context, file_path)
        if not build_command:
            result['error'] = f"无法确定文件的编译命令: {file_path}"
            return result
        
        # 确定编译目录
        compile_dir = context.commit.base_dir
        
        # 执行编译
        logger.info(f"编译文件: {file_path}, 命令: {build_command}")
        result['command'] = build_command
        
        try:
            process = subprocess.run(
                build_command,
                cwd=compile_dir,
                capture_output=True,
                encoding='utf-8',
                shell=True
            )
            
            # 记录输出
            output = process.stdout + "\n" + process.stderr
            result['output'] = output
            
            # 判断是否成功
            if process.returncode == 0:
                result['success'] = True
                logger.info(f"编译成功: {file_path}")
            else:
                result['success'] = False
                result['error'] = f"编译失败，返回码: {process.returncode}"
                logger.warning(f"编译失败: {file_path}, 错误: {process.stderr}")
            
            # 保存编译输出
            self._save_compilation_output(context, file_path, output, result['success'])
            
            return result
            
        except Exception as e:
            logger.error(f"执行编译命令时出错: {str(e)}")
            result['error'] = str(e)
            return result
    
    def _determine_build_command(self, context: ModuleContext, file_path: Path) -> Optional[str]:
        """确定文件的编译命令"""
        # 获取文件类型
        file_ext = file_path.suffix
        
        # 从config获取编译命令
        base_build_command = context.config.build_command or "make"
        
        # 根据文件类型和路径确定具体编译命令
        if file_ext == '.c' or file_ext == '.h':
            # 对于C文件，可以尝试找到相关的Makefile目标
            # 这需要根据具体项目结构来确定
            file_dir = file_path.parent
            file_name = file_path.stem
            
            # 1. 尝试直接使用文件名作为目标
            return f"{base_build_command} {file_dir}/{file_name}.o"
            
        elif file_ext == '.cpp' or file_ext == '.hpp' or file_ext == '.cc':
            # C++文件类似处理
            file_dir = file_path.parent
            file_name = file_path.stem
            return f"{base_build_command} {file_dir}/{file_name}.o"
            
        else:
            # 其他类型文件，可以尝试使用目录作为目标
            return f"{base_build_command} {file_path.parent}"
    
    def _save_compilation_output(self, context: ModuleContext, file_path: Path, output: str, success: bool) -> None:
        """保存编译输出结果"""
        compile_output_dir = context.commit.base_dir / "compilation" / "outputs"
        compile_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用文件路径创建唯一文件名
        status = "success" if success else "failed"
        filename = f"{file_path.stem}_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # 将路径分隔符替换为下划线
        safe_filename = filename.replace('/', '_').replace('\\', '_')
        output_file = compile_output_dir / safe_filename
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"编译文件: {file_path}\n")
            f.write(f"状态: {'成功' if success else '失败'}\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("-" * 50 + "\n")
            f.write(output)
        
        logger.info(f"编译输出已保存到: {output_file}")
    
    def _retry_with_feedback(self, context: ModuleContext, failed_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """使用编译错误反馈重试"""
        file_path = failed_result.get('file')
        error_output = failed_result.get('output', '')
        
        if not file_path or not error_output:
            logger.warning("无法重试，缺少文件路径或错误输出")
            return None
        
        logger.info(f"尝试使用编译错误反馈重试: {file_path}")
        self.metrics['retries'] += 1
        
        # 准备反馈信息
        feedback = {
            'file': file_path,
            'compilation_error': error_output,
            'retry_count': context.retry_count + 1 if hasattr(context, 'retry_count') else 1
        }
        
        # 更新上下文
        context.retry_count = feedback['retry_count']
        context.feedback_data = feedback
        
        try:
            # 重新执行LLM和补丁适配模块
            # 注意：这里假设AdaptationPipeline会在外部处理这部分逻辑
            # 我们这里只返回一个标记了需要重试的结果
            
            return {
                'file': file_path,
                'success': False,
                'retried': True,
                'retry_feedback': feedback,
                'output': error_output,
                'error': "需要重试"
            }
            
        except Exception as e:
            logger.error(f"重试准备过程中出错: {str(e)}")
            return None
    
    def _update_metrics(self, success: bool, error_type: str = None, compiled_success: bool = False,
                       compilation_results: List[Dict] = None, execution_time: float = 0) -> None:
        """更新指标"""
        self.metrics['execution_time'] = execution_time
        
        if success:
            self.metrics['successful_executions'] += 1
            
            if compiled_success:
                self.metrics['compilation_success'] += 1
            else:
                self.metrics['compilation_failures'] += 1
                
            if compilation_results:
                successful_files = [r['file'] for r in compilation_results if r['success']]
                self.metrics['compiled_files'].extend(successful_files)
        else:
            self.metrics['failed_executions'] += 1
            if error_type:
                self.metrics['error_types'][error_type] = self.metrics['error_types'].get(error_type, 0) + 1
    
    def _save_metrics(self, context: ModuleContext):
        """保存指标"""
        metrics_dir = context.commit.base_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        
        metrics_file = metrics_dir / "compiler_metrics.json"
        with open(metrics_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"编译指标已保存到: {metrics_file}")