from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import sys
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
from .kernel_compiler import KernelCompiler

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
        """
        执行编译验证
        
        :param context: 模块上下文
        :return: 更新后的上下文（始终返回上下文对象，不返回布尔值）
        """
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
            
            # 应用适配后的补丁
            if not self._apply_adapted_patch(context):
                logger.error("应用补丁失败，无法进行编译测试")
                context.compilation_result = {
                    'success': False,
                    'error': '应用补丁失败'
                }
                self._update_metrics(False, error_type="PatchApplyFailed")
                self._save_metrics(context)
                return context
            
            try:
                # 调用内核编译模块
                kernel_compiler = KernelCompiler(
                    repo_path=context.config.repo_path,
                    output_dir=context.commit.compilation_dir,
                    use_docker=context.config.module_configs.get('kernel_compiler', {}).get('use_docker', False),
                    docker_image=context.config.module_configs.get('kernel_compiler', {}).get('docker_image', 'kernel-builder:arm64'),
                    ccache_dir=Path(os.path.expanduser(context.config.module_configs.get('kernel_compiler', {}).get('ccache_dir', '~/.ccache')))
                )
                
                # 首次运行时构建Docker镜像
                if context.config.module_configs.get('kernel_compiler', {}).get('use_docker', False) and not context.docker_image_built:
                    logger.info("开始构建Docker镜像")
                    if not kernel_compiler.build_docker_image():
                        logger.error("Docker镜像构建失败，无法继续编译验证")
                        context.compilation_result = {
                            'success': False,
                            'error': 'Docker镜像构建失败'
                        }
                        # 重要：返回上下文，不返回布尔值
                        return context
                    logger.info("Docker镜像构建完成")
                    context.docker_image_built = True
                
                # 修改的文件路径列表
                modified_files = self._get_modified_files(context)
                if not modified_files:
                    logger.warning("未找到修改的文件，跳过编译验证")
                    context.compilation_result = {
                        'success': True,
                        'warning': '未找到修改的文件'
                    }
                    # 重要：返回上下文，不返回布尔值
                    return context
                
                # 执行编译验证
                logger.info(f"开始编译文件: {modified_files}")
                compilation_ok = kernel_compiler.compile_files(modified_files)
                # kernel_compiler.compile_files(modified_files)
                # logger.info(f"编译函数返回结果: {compilation_ok}")
                # compilation_ok = kernel_compiler.compile_files(modified_files)
                # logger.info(f"编译函数返回结果2222: {compilation_ok}")
                # 更新编译结果
                if not compilation_ok:
                    logger.error("补丁导致编译错误")
                    context.compilation_result = {
                        'success': False,
                        'error': '编译失败，请查看日志了解详情'
                    }
                    self.metrics['compilation_failures'] += 1
                    self._update_metrics(False)
                else:
                    logger.info("补丁编译验证通过")
                    context.compilation_result = {
                        'success': True,
                        'files': [str(f) for f in modified_files]
                    }
                    self.metrics['compilation_success'] += 1
                    self._update_metrics(True)
                
                return context
                
            except Exception as e:
                logger.error(f"编译过程发生错误: {str(e)}")
                context.compilation_result = {
                    'success': False,
                    'error': str(e)
                }
                self._update_metrics(False)
                return context
            
        except Exception as e:
            logger.error(f"编译测试过程发生错误: {str(e)}")
            context.compilation_result = {
                'success': False,
                'error': str(e)
            }
            self._update_metrics(False)
            return context
        
        finally:
            # 无论成功失败，都清理临时分支
            if hasattr(context, 'compiler_branch'):
                logger.info("清理编译测试分支")
                self._cleanup_branch(context, context.compiler_branch)
                delattr(context, 'compiler_branch')  # 清理上下文中的分支记录
    
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
        
        logger.info(f"已修改的文件列表: {modified_files}")
        return modified_files
        # # 也可以从patch文件中获取修改的文件列表
        # if context.patch_adapter_result.get('adapted_patch_path'):
        #     patch_path = Path(context.patch_adapter_result['adapted_patch_path'])
        #     if patch_path.exists():
        #         try:
        #             # 从context获取修改的文件
        #             if hasattr(context, 'modified_files') and context.modified_files:
        #                 return [context.repo_path / f for f in context.modified_files]
                    
        #             # 或者从git获取
        #             result = subprocess.run(
        #                 ["git", "diff", "--name-only", "HEAD^"],
        #                 cwd=context.config.repo_path,
        #                 capture_output=True,
        #                 text=True
        #             )
            
        #             if result.returncode != 0:
        #                 logger.warning(f"获取修改文件失败: {result.stderr}")
        #                 return []
        #             logger.info(f"获取修改文件成功: {result.stdout}")
        #             return [
        #                 context.config.repo_path / f.strip()
        #                 for f in result.stdout.splitlines()
        #                 if f.strip()
        #             ]
        #         except Exception as e:
        #             logger.error(f"获取修改文件列表时出错: {str(e)}")
        #             return []
    
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
        compile_dir = context.commit.compilation_dir
        
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
    
    def _update_metrics(self, success: bool) -> None:
        """更新模块指标"""
        if success:
            self.metrics['successful_executions'] += 1
        else:
            self.metrics['failed_executions'] += 1
    
    def _save_metrics(self, context: ModuleContext):
        """保存指标"""
        metrics_dir = context.commit.base_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        
        metrics_file = metrics_dir / "compiler_metrics.json"
        with open(metrics_file, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"编译指标已保存到: {metrics_file}")

    def _apply_adapted_patch(self, context: ModuleContext) -> bool:
        """
        应用适配后的补丁到仓库
        
        :param context: 模块上下文
        :return: 是否成功应用补丁
        """
        try:
            # 获取适配后的补丁路径
            if not hasattr(context, 'patch_adapter_result') or not context.patch_adapter_result:
                logger.warning("缺少补丁适配结果")
                return False
            
            adapted_patch_path = context.patch_adapter_result.get('adapted_patch_path')
            if not adapted_patch_path or not Path(adapted_patch_path).exists():
                logger.warning(f"适配后的补丁文件不存在: {adapted_patch_path}")
                return False
            
            repo_path = context.config.repo_path
            
            # 创建并切换到临时分支
            branch_name = f"compile_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 执行git命令
            commands = [
                ["git", "checkout", "-b", branch_name],  # 创建并切换到新分支
                ["git", "am", str(adapted_patch_path)]   # 应用补丁
            ]
            
            for cmd in commands:
                logger.info(f"执行命令: {' '.join(cmd)}")
                process = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
                
                if process.returncode != 0:
                    logger.error(f"命令执行失败: {' '.join(cmd)}")
                    logger.error(f"错误输出: {process.stderr}")
                    # 清理：删除临时分支
                    self._cleanup_branch(context, branch_name)
                    return False
                else:
                    logger.info(f"命令执行成功: {' '.join(cmd)}")
                    logger.debug(f"命令输出: {process.stdout}")
            
            # 记录分支名到上下文，以便后续清理
            context.compiler_branch = branch_name
            return True
            
        except Exception as e:
            logger.error(f"应用补丁时发生错误: {str(e)}")
            if hasattr(context, 'compiler_branch'):
                self._cleanup_branch(context, context.compiler_branch)
            return False

    def _cleanup_branch(self, context: ModuleContext, branch_name: str) -> None:
        """
        清理临时分支
        
        :param context: 模块上下文
        :param branch_name: 要清理的分支名
        """
        try:
            repo_path = context.config.repo_path
            
            # 切换回主分支
            subprocess.run(
                ["git", "checkout", context.config.target_version],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            # 删除临时分支
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            logger.info(f"已清理临时分支: {branch_name}")
            
        except Exception as e:
            logger.error(f"清理分支时发生错误: {str(e)}")