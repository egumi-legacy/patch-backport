import subprocess
import os
import shutil
# import logging

import re
import tempfile
import docker
from pathlib import Path
from typing import List, Dict, Optional, Union, Tuple

# logger = logging.getLogger(__name__)
from loguru import logger

class KernelCompiler:
    def __init__(self, 
                 repo_path: Path,
                 output_dir: Optional[Path] = None,
                 config_path: Optional[Path] = None,
                 use_docker: bool = True,
                 docker_image: str = "kernel-compiler:arm64",
                 ccache_dir: Optional[Path] = None):
        """
        Linux内核编译验证器
        
        :param repo_path: 内核源码目录路径
        :param output_dir: 构建输出目录，默认为repo_path/build
        :param config_path: 内核配置文件路径，默认自动生成
        :param use_docker: 是否使用Docker容器进行编译
        :param docker_image: Docker镜像名称
        :param ccache_dir: ccache缓存目录
        """
        self.repo_path = Path(repo_path).resolve()
        self.output_dir = Path(output_dir) if output_dir else self.repo_path / "build"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_path = config_path
        self.use_docker = use_docker
        self.docker_image = docker_image
        self.ccache_dir = Path(ccache_dir) if ccache_dir else Path.home() / ".ccache"
        self.ccache_dir.mkdir(parents=True, exist_ok=True)
        
        # 自动检测CPU核心数
        self.jobs = self._detect_cpu_cores()
        
        # Docker客户端
        self.docker_client = docker.from_env() if use_docker else None
        
        # 创建默认配置
        if not self.config_path and not (self.repo_path / ".config").exists():
            self._create_default_config()

    def _detect_cpu_cores(self) -> int:
        """自动检测CPU核心数"""
        try:
            cores = os.cpu_count() or 2
            return max(2, min(cores, 8))  # 使用2-8个核心
        except Exception:
            return 2

    # def _create_default_config(self) -> None:
    #     """创建默认的内核配置文件"""
    #     try:
    #         # # 先检查Docker镜像是否存在
    #         # logger.info(f"是否使用Docker镜像: {self.use_docker}")
    #         # if self.use_docker:
    #         #     check_image = subprocess.run(
    #         #         ["docker", "image", "inspect", self.docker_image],
    #         #         capture_output=True
    #         #     )
                
    #         #     if check_image.returncode != 0:
    #         #         logger.error(f"Docker镜像 {self.docker_image} 不存在，无法创建配置")
    #         logger.info("开始创建默认配置...")
            
    #         # 确保在正确的目录
    #         os.chdir(self.repo_path)
            
    #         # 首先清理
    #         clean_cmd = self._prepare_command("mrproper")
    #         returncode, stdout, stderr = self._run_command(clean_cmd)
    #         if returncode != 0:
    #             logger.warning(f"清理命令返回非零值: {stderr}")
            
    #         # 检查架构特定的默认配置是否存在
    #         arch_defconfig = self.repo_path / "arch" / self.arch / "configs" / "defconfig"
    #         if arch_defconfig.exists():
    #             # 复制架构默认配置
    #             shutil.copy(arch_defconfig, self.repo_path / ".config")
    #             logger.info(f"已复制架构默认配置: {arch_defconfig}")
                
    #             # if check_image.returncode != 0:
    #             #     logger.error(f"Docker镜像 {self.docker_image} 不存在，无法创建配置")
    #             # 更新配置
    #             update_cmd = self._prepare_command("olddefconfig")
    #             returncode, stdout, stderr = self._run_command(update_cmd)
    #             if returncode != 0:
    #                 logger.error(f"更新配置失败: {stderr}")
    #                 return
            
    #         # # 准备创建配置命令
    #         # config_cmd = self._prepare_command("defconfig")
    #         # returncode, stdout, stderr = self._run_command(config_cmd)
            
    #         # if returncode != 0:
    #         #     logger.error(f"创建配置失败: {stderr}")
    #         else:
    #             # 使用defconfig
    #             config_cmd = self._prepare_command("defconfig")
    #             returncode, stdout, stderr = self._run_command(config_cmd)
    #             if returncode != 0:
    #                 logger.error(f"创建默认配置失败: {stderr}")
    #                 return
            
    #         # 验证配置文件是否创建
    #         config_file = self.repo_path / ".config"
    #         if config_file.exists():
    #             logger.info(f"配置文件创建成功: {config_file}")
    #         else:
    #             logger.error("配置文件未能创建")
                
    #     except Exception as e:
    #         import traceback
    #         logger.error(f"创建配置时发生错误: {str(e)}")
    #         logger.debug(traceback.format_exc())
    
    def _create_default_config(self) -> None:
        """创建默认的内核配置文件"""
        try:
            # 先检查Docker镜像是否存在
            logger.info(f"是否使用Docker镜像: {self.use_docker}")
            if self.use_docker:
                check_image = subprocess.run(
                    ["docker", "image", "inspect", self.docker_image],
                    capture_output=True
                )
                
                if check_image.returncode != 0:
                    logger.error(f"Docker镜像 {self.docker_image} 不存在，无法创建配置")
                    return
            
            # 准备创建配置命令
            config_cmd = self._prepare_command("defconfig")
            returncode, stdout, stderr = self._run_command(config_cmd)
            
            if returncode != 0:
                logger.error(f"创建配置失败: {stderr}")
            else:
                logger.info(f"已创建默认内核配置: {self.output_dir / '.config'}")
        except Exception as e:
            import traceback
            logger.info(traceback.format_exc())
            logger.error(f"创建配置失败: {str(e)}")

    def _prepare_command(self, target: str = "") -> List[str]:
        """准备命令行参数"""
        cmd = ["make", f"-j{self.jobs}", f"O={self.output_dir}"]
        if target:
            cmd.append(target)
        return cmd

    def _run_command(self, 
                    cmd: List[str], 
                    cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """
        执行命令（本地或Docker中）
        
        :param cmd: 要执行的命令
        :param cwd: 工作目录
        :return: (返回码, 标准输出, 标准错误)
        """
        cwd = cwd or self.repo_path
        
        if not self.use_docker:
            # 本地执行
            process = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                env=dict(os.environ, CCACHE_DIR=str(self.ccache_dir))
            )
            return process.returncode, process.stdout, process.stderr
        else:
            # Docker中执行
            return self._run_in_docker(cmd, cwd)

    def _run_in_docker(self, 
                      cmd: List[str], 
                      cwd: Path) -> Tuple[int, str, str]:
        """在Docker容器中执行命令"""
        try:
            # 相对于挂载点的工作目录
            rel_path = cwd.relative_to(self.repo_path)
            work_dir = f"/kernel/{rel_path}"
            
            # 创建临时文件用于捕获输出
            with tempfile.NamedTemporaryFile(mode='w+') as stdout_file, \
                 tempfile.NamedTemporaryFile(mode='w+') as stderr_file:
                
                # 确保Docker镜像存在
                try:
                    self.docker_client.images.get(self.docker_image)
                except docker.errors.ImageNotFound:
                    return -1, "", f"Docker镜像 {self.docker_image} 不存在"
                
                # 运行容器
                try:
                    logger.info(f"运行容器: {self.docker_image}")
                    logger.info(f"work_dir: {work_dir}")
                    logger.info(f"cmd: {' '.join(cmd)}")
                    logger.info(f"command=f'bash -c 'cd {work_dir} && {' '.join(cmd)} > {stdout_file.name} 2> {stderr_file.name}; echo $? > /tmp/exit_code''")
                    container = self.docker_client.containers.run(
                        self.docker_image,
                        command=f"bash -c 'cd {work_dir} && {' '.join(cmd)} > {stdout_file.name} 2> {stderr_file.name}; echo $? > /tmp/exit_code'",
                        volumes={
                            str(self.repo_path): {'bind': '/kernel', 'mode': 'rw'},
                            str(self.ccache_dir): {'bind': '/ccache', 'mode': 'rw'},
                            stdout_file.name: {'bind': stdout_file.name, 'mode': 'rw'},
                            stderr_file.name: {'bind': stderr_file.name, 'mode': 'rw'}
                        },
                        working_dir="/kernel",
                        detach=True,
                        remove=True
                    )
                    
                    # 等待容器完成
                    result = container.wait()
                    exit_code = result['StatusCode']
                    
                    # 读取输出
                    stdout_file.seek(0)
                    stderr_file.seek(0)
                    stdout = stdout_file.read()
                    stderr = stderr_file.read()
                    
                    return exit_code, stdout, stderr
                except Exception as e:
                    return -1, "", f"Docker容器执行错误: {str(e)}"
                
        except Exception as e:
            logger.error(f"Docker执行失败: {str(e)}")
            return -1, "", str(e)

    def compile_files(self, files: List[Path]) -> bool:
        """编译指定的文件列表"""
        try:
            logger.info(f"开始编译文件1111: {[str(f) for f in files]}")
            
            # 准备编译环境
            if not self._prepare_build_env():
                logger.error("准备编译环境失败")
                return False
                
            # 将文件路径转换为相对于repo_path的路径
            relative_files = []
            for file in files:
                if isinstance(file, str):
                    file = Path(file)
                try:
                    # 确保是相对路径
                    rel_path = file.relative_to(self.repo_path) if file.is_absolute() else file
                    relative_files.append(str(rel_path))
                except ValueError:
                    logger.warning(f"跳过不在仓库中的文件: {file}")
            
            if not relative_files:
                logger.warning("没有找到有效的文件进行编译")
                return True  # 没有文件需要编译，返回成功
                
            # 构建编译命令
            build_targets = self._get_build_targets(relative_files)
            logger.info(f"编译目标: {build_targets}")
            
            # 执行编译
            for target in build_targets:
                compile_cmd = self._prepare_command(target)
                logger.info(f"执行编译命令: {' '.join(compile_cmd)}")
                
                returncode, stdout, stderr = self._run_command(compile_cmd)
                
                if returncode != 0:
                    logger.error(f"编译目标 {target} 失败: {stderr}")
                    return False
                
                logger.info(f"目标 {target} 编译成功")
            
            logger.info("所有文件编译成功")
            return True
            
        except Exception as e:
            logger.error(f"编译过程出错: {str(e)}")
            return False
            
    def _prepare_build_env(self) -> bool:
        """准备编译环境"""
        try:
            # 检查配置文件是否存在
            config_file = self.repo_path / ".config"
            logger.info(f"检查配置文件: {config_file.resolve()}")
            if not config_file.exists():
                logger.info("未找到配置文件，创建默认配置")
                self._create_default_config()
                
                # 再次检查
                if not config_file.exists():
                    logger.error("无法创建配置文件")
                    return False
            
            logger.info("编译环境已准备")
            return True
        except Exception as e:
            logger.error(f"准备环境出错: {str(e)}")
            return False

    def _get_build_targets(self, files: List[str]) -> List[str]:
        """
        将文件路径转换为内核构建目标
        
        :param files: 源文件路径列表
        :return: 构建目标列表
        """
        targets = set()
        
        for file_path in files:
            file_path = Path(file_path)
            
            if file_path.suffix == '.c':
                # C文件转换为.o目标
                obj_target = str(file_path.with_suffix('.o'))
                targets.add(obj_target)
            elif file_path.suffix == '.h':
                # 头文件 - 尝试找到包含该头文件的模块
                module_path = self._find_module_for_header(file_path)
                if module_path:
                    targets.add(module_path)
            elif file_path.name in ('Makefile', 'Kconfig', 'Kbuild'):
                # 构建整个目录
                targets.add(f"M={file_path.parent}")
        
        # 如果没有特定目标，尝试构建全部
        if not targets:
            targets.add("all")
            
        return list(targets)

    def _find_module_for_header(self, header_path: Path) -> Optional[str]:
        """
        查找包含指定头文件的模块路径
        简化版 - 返回头文件所在目录
        
        :param header_path: 头文件路径
        :return: 模块构建路径
        """
        # 简化实现 - 构建头文件所在目录
        return f"M={header_path.parent}"

    def build_docker_image(self) -> bool:
        """构建Docker镜像或使用现有镜像"""
        if not self.use_docker:
            return True
            
        try:
            # 首先检查镜像是否已存在
            image_check = subprocess.run(
                ["docker", "image", "inspect", self.docker_image],
                capture_output=True
            )
            
            if image_check.returncode == 0:
                logger.info(f"使用已存在的Docker镜像: {self.docker_image}")
                return True
            
            # 检查基础镜像
            alpine_check = subprocess.run(
                ["docker", "image", "inspect", "alpine/git:latest"],
                capture_output=True
            )
            
            if alpine_check.returncode == 0:
                # 使用本地已有的alpine/git镜像创建编译镜像
                logger.info("使用alpine/git创建内核编译镜像")
                
                # 创建临时容器安装编译工具
                container_id = subprocess.run(
                    ["docker", "run", "-d", "alpine/git:latest", "tail", "-f", "/dev/null"],
                    capture_output=True, text=True
                ).stdout.strip()
                
                try:
                    # 在容器内安装构建工具
                    install_result = subprocess.run(
                        ["docker", "exec", container_id, "sh", "-c", 
                         "apk add --no-cache build-base gcc g++ make flex bison elfutils-dev "
                         "openssl-dev perl bash ncurses-dev python3 bc kmod"],
                        capture_output=True, text=True
                    )
                    
                    if install_result.returncode != 0:
                        logger.error(f"安装编译工具失败: {install_result.stderr}")
                        return False
                    
                    # 提交为新镜像
                    commit_result = subprocess.run(
                        ["docker", "commit", container_id, self.docker_image],
                        capture_output=True, text=True
                    )
                    
                    if commit_result.returncode != 0:
                        logger.error(f"创建镜像失败: {commit_result.stderr}")
                        return False
                    
                    logger.info(f"成功创建编译镜像: {self.docker_image}")
                    return True
                    
                finally:
                    # 清理临时容器
                    subprocess.run(["docker", "rm", "-f", container_id], 
                                  capture_output=True)
            
            # 如果没有合适的基础镜像，尝试从Dockerfile构建
            logger.warning("未找到可用基础镜像，尝试从Dockerfile构建")
            
            # 创建构建目录
            docker_dir = self.output_dir / "docker"
            docker_dir.mkdir(exist_ok=True)
            
            # 创建适用本地环境的Dockerfile
            dockerfile_content = """FROM alpine/git:latest

RUN apk add --no-cache \\
    build-base \\
    gcc \\
    g++ \\
    make \\
    flex \\
    bison \\
    elfutils-dev \\
    openssl-dev \\
    perl \\
    bash \\
    ncurses-dev \\
    python3 \\
    bc \\
    kmod

WORKDIR /kernel
"""
            
            # 写入Dockerfile
            dockerfile_path = docker_dir / "Dockerfile"
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
                
            # 构建镜像
            logger.info(f"开始构建Docker镜像: {self.docker_image}")
            build_result = subprocess.run(
                ["docker", "build", "-t", self.docker_image, "."],
                cwd=docker_dir,
                capture_output=True,
                text=True
            )
            
            if build_result.returncode != 0:
                logger.error(f"Docker镜像构建失败: {build_result.stderr}")
                return False
                
            logger.info(f"Docker镜像 {self.docker_image} 构建成功")
            return True
            
        except Exception as e:
            logger.error(f"Docker镜像构建过程发生错误: {str(e)}")
            return False

    def clean(self, all: bool = False) -> bool:
        """
        清理构建目录
        
        :param all: 是否执行完全清理(mrproper)
        :return: 清理是否成功
        """
        target = "mrproper" if all else "clean"
        cmd = self._prepare_command(target)
        returncode, stdout, stderr = self._run_command(cmd)
        
        if returncode != 0:
            logger.error(f"清理失败: {stderr}")
            return False
            
        logger.info(f"成功完成{target}清理")
        return True

    def verify_patch(self, patch_path: Path) -> bool:
        """
        验证补丁的编译能力
        
        :param patch_path: 补丁文件路径
        :return: 验证是否成功
        """
        try:
            # 创建临时分支
            branch_name = f"verify_patch_{os.urandom(4).hex()}"
            
            # 创建新分支
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.repo_path,
                capture_output=True
            )
            
            try:
                # 应用补丁
                apply_result = subprocess.run(
                    ["git", "am", str(patch_path)],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True
                )
                
                if apply_result.returncode != 0:
                    logger.error(f"补丁应用失败: {apply_result.stderr}")
                    return False
                
                # 获取修改的文件列表
                files_result = subprocess.run(
                    ["git", "diff", "--name-only", "HEAD^"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True
                )
                
                modified_files = [
                    self.repo_path / f.strip()
                    for f in files_result.stdout.splitlines()
                    if f.strip()
                ]
                
                # 编译修改的文件
                return self.compile_files(modified_files)
                
            finally:
                # 恢复原始分支
                subprocess.run(
                    ["git", "checkout", "-"],
                    cwd=self.repo_path,
                    capture_output=True
                )
                
                # 删除临时分支
                subprocess.run(
                    ["git", "branch", "-D", branch_name],
                    cwd=self.repo_path,
                    capture_output=True
                )
                
        except Exception as e:
            logger.error(f"补丁验证过程发生错误: {str(e)}")
            return False

    def _prepare_kernel_config(self) -> bool:
        """准备内核配置文件"""
        try:
            if self.use_docker:
                # 在Docker中准备配置
                cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{self.repo_path}:/kernel",
                    "-v", f"{self.output_dir}:/output",
                    self.docker_image,
                    "-c", "cd /kernel && make O=/output defconfig"
                ]
            else:
                # 本地准备配置
                cmd = [
                    "make", 
                    f"O={self.output_dir}", 
                    "defconfig"
                ]
                
            process = subprocess.run(
                cmd,
                cwd=self.repo_path if not self.use_docker else None,
                capture_output=True,
                text=True
            )
            
            if process.returncode != 0:
                logger.error(f"创建内核配置失败: {process.stderr}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"创建配置失败: {str(e)}")
            import traceback
            logger.info(traceback.format_exc())
            return False