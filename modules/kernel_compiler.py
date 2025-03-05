import subprocess
import os
import shutil
import logging
import re
import tempfile
import docker
from pathlib import Path
from typing import List, Dict, Optional, Union, Tuple

logger = logging.getLogger(__name__)

class KernelCompiler:
    def __init__(self, 
                 repo_path: Path,
                 output_dir: Optional[Path] = None,
                 config_path: Optional[Path] = None,
                 use_docker: bool = True,
                 docker_image: str = "kernel-compiler:latest",
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
        if not self.config_path and not (self.output_dir / ".config").exists():
            self._create_default_config()

    def _detect_cpu_cores(self) -> int:
        """自动检测CPU核心数"""
        try:
            cores = os.cpu_count() or 2
            return max(2, min(cores, 8))  # 使用2-8个核心
        except Exception:
            return 2

    def _create_default_config(self) -> None:
        """创建默认的内核配置文件"""
        config_cmd = self._prepare_command("defconfig")
        self._run_command(config_cmd)
        logger.info(f"已创建默认内核配置: {self.output_dir / '.config'}")

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
                
                # 运行容器
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
            logger.error(f"Docker执行失败: {str(e)}")
            return -1, "", str(e)

    def compile_files(self, files: List[Path]) -> bool:
        """编译指定的文件列表"""
        try:
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
            compile_cmd = self._build_compile_command(build_targets)
            logger.info(f"编译命令: {' '.join(compile_cmd) if isinstance(compile_cmd, list) else compile_cmd}")
            
            # 执行编译命令
            process = subprocess.run(
                compile_cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            
            # 检查编译结果
            if process.returncode != 0:
                logger.error(f"编译失败: {process.stderr}")
                return False
                
            logger.info("编译成功完成")
            return True
            
        except Exception as e:
            logger.error(f"编译过程出错: {str(e)}")
            return False

    def _get_build_targets(self, files: List[Path]) -> List[str]:
        """
        将文件路径转换为内核构建目标
        
        :param files: 源文件路径列表
        :return: 构建目标列表
        """
        targets = set()
        
        for file_path in files:
            # 获取相对路径
            try:
                rel_path = file_path.relative_to(self.repo_path)
            except ValueError:
                logger.warning(f"文件不在仓库目录内: {file_path}")
                continue
                
            if rel_path.suffix == '.c':
                # C文件转换为.o目标
                obj_target = str(rel_path.with_suffix('.o'))
                targets.add(obj_target)
            elif rel_path.suffix == '.h':
                # 头文件 - 尝试找到包含该头文件的模块
                module_path = self._find_module_for_header(rel_path)
                if module_path:
                    targets.add(module_path)
            elif rel_path.name in ('Makefile', 'Kconfig', 'Kbuild'):
                # 构建整个目录
                targets.add(f"M={rel_path.parent}")
        
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

    def build_docker_image(self) -> bool:
        """
        构建Docker镜像
        
        :return: 构建是否成功
        """
        if not self.use_docker:
            return True
            
        try:
            # 创建Dockerfile
#             dockerfile_content = """FROM ubuntu:22.04

# # ENV DEBIAN_FRONTEND=noninteractive

# RUN apt-get update && apt-get install -y \\
#     build-essential \\
#     flex \\
#     bison \\
#     libssl-dev \\
#     libelf-dev \\
#     bc \\
#     ccache \\
#     git \\
#     kmod \\
#     python3 \\
#     ncurses-dev \\
#     rsync \\
#     --no-install-recommends \\
#     && apt-get clean \\
#     && rm -rf /var/lib/apt/lists/*

# RUN mkdir -p /ccache && chmod 777 /ccache
# WORKDIR /kernel
# ENV PATH="/usr/lib/ccache:${PATH}" CCACHE_DIR=/ccache CCACHE_MAXSIZE=10G
# ENTRYPOINT ["/bin/bash"]
# """
            dockerfile_content = """FROM alpine/git:latest


RUN apk add --no-cache \
    build-base \
    gcc \
    g++ \
    make \
    flex \
    bison \
    elfutils-dev \
    openssl-dev \
    perl \
    bash \
    ncurses-dev \
    python3 \
    bc \
    git \
    kmod


WORKDIR /kernel
"""
            # 创建构建目录
            docker_dir = self.output_dir / "docker"
            docker_dir.mkdir(exist_ok=True)
            logger.info(f"构建目录: {docker_dir.resolve()}")
            
            # 写入Dockerfile
            dockerfile_path = docker_dir / "Dockerfile"
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
                
            # 构建镜像
            logger.info(f"开始构建Docker镜像: {self.docker_image}")
            process = subprocess.run(
                ["docker", "build", "-t", self.docker_image, "."],
                cwd=docker_dir,
                capture_output=True,
                text=True
            )
            
            if process.returncode != 0:
                logger.error(f"Docker镜像构建失败: {process.stderr}")
                return False
                
            logger.info(f"Docker镜像 {self.docker_image} 构建成功")
            return True
            
        except Exception as e:
            logger.error(f"Docker镜像构建过程发生错误: {str(e)}")
            return False

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
            return False