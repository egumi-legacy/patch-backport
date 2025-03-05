import subprocess
from pathlib import Path
from typing import List, Dict, Optional
import logging
import re
import shutil
import os

logger = logging.getLogger(__name__)

class KernelCompiler:
    def __init__(self, 
                 repo_path: Path,
                 output_dir: Path = Path("build"),
                 config_path: Path = Path("configs/kernel.config"),
                 ccache_path: Path = Path("/usr/lib/ccache")):
        """
        Linux内核编译验证器
        
        :param repo_path: 内核源码目录路径
        :param output_dir: 构建输出目录
        :param config_path: 内核配置文件路径
        :param ccache_path: ccache可执行文件路径
        """
        self.repo_path = repo_path.resolve()
        self.output_dir = output_dir.resolve()
        self.config_path = config_path.resolve()
        self.ccache_path = ccache_path
        
        # 自动检测CPU核心数
        self.jobs = self._detect_cpu_cores()
        
        # 编译环境配置
        self.env = self._prepare_env()
        
    def _detect_cpu_cores(self) -> int:
        """自动检测CPU核心数"""
        try:
            import os
            return len(os.sched_getaffinity(0)) or 1
        except AttributeError:
            return os.cpu_count() or 1

    def _prepare_env(self) -> Dict[str, str]:
        """准备编译环境变量"""
        env = dict(os.environ)
        
        # 设置ccache路径
        ccache_bin = self.ccache_path / "bin"
        if ccache_bin.exists():
            env["PATH"] = f"{ccache_bin}:{env['PATH']}"
            env["CCACHE_DIR"] = str(self.ccache_path / "cache")
            
        # 内核编译专用环境变量
        env["ARCH"] = "x86_64"  # 根据实际情况调整
        env["CROSS_COMPILE"] = ""  # 本地编译
        
        return env

    def _run_make(self, 
                 target: str = "",
                 capture_output: bool = True) -> subprocess.CompletedProcess:
        """执行make命令的通用方法"""
        cmd = [
            "make",
            f"-j{self.jobs}",
            f"O={self.output_dir}",
            target
        ]
        
        return subprocess.run(
            cmd,
            cwd=self.repo_path,
            env=self.env,
            capture_output=capture_output,
            text=True
        )

    def prepare_kernel_config(self) -> bool:
        """准备内核编译配置"""
        try:
            # 创建输出目录
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制配置文件
            if self.config_path.exists():
                shutil.copy2(self.config_path, self.output_dir / ".config")
                
            # 更新配置
            result = self._run_make("olddefconfig")
            return result.returncode == 0
        except Exception as e:
            logger.error(f"准备内核配置失败: {str(e)}")
            return False

    def incremental_build(self, 
                         modified_files: List[Path]) -> bool:
        """
        执行增量编译验证
        
        :param modified_files: 修改过的文件路径列表
        :return: 编译是否成功
        """
        if not self.prepare_kernel_config():
            return False
            
        # 解析修改文件对应的编译目标
        build_targets = self._analyze_modified_files(modified_files)
        
        if not build_targets:
            logger.info("没有需要编译的目标文件")
            return True
            
        # 执行增量编译
        logger.info(f"开始增量编译目标: {', '.join(build_targets)}")
        result = self._run_make(" ".join(build_targets), capture_output=False)
        
        if result.returncode != 0:
            logger.error("增量编译失败")
            return False
            
        return True

    def _analyze_modified_files(self, 
                               modified_files: List[Path]) -> List[str]:
        """分析修改文件对应的编译目标"""
        targets = set()
        
        for file_path in modified_files:
            # 转换为相对于内核源码目录的路径
            relative_path = file_path.relative_to(self.repo_path)
            
            # 根据文件类型确定编译目标
            if relative_path.suffix == ".c":
                # C文件编译为对应的.o文件
                obj_path = relative_path.with_suffix(".o")
                targets.add(str(obj_path))
            elif relative_path.name == "Kbuild":
                # 处理整个目录的编译
                dir_path = relative_path.parent
                targets.add(f"M={dir_path}")
            elif relative_path.suffix == ".h":
                # 头文件需要编译依赖它的所有目标
                dependent_objs = self._find_header_dependencies(relative_path)
                targets.update(dependent_objs)
                
        return list(targets)

    def _find_header_dependencies(self, 
                                 header_path: Path) -> List[str]:
        """查找依赖指定头文件的目标文件（简化版）"""
        try:
            # 使用make的依赖追踪功能
            result = self._run_make(f"deps {header_path}")
            if result.returncode != 0:
                return []
                
            # 解析依赖关系
            deps = re.findall(r"\S+\.o", result.stdout)
            return list(set(deps))
        except Exception as e:
            logger.warning(f"无法获取头文件依赖: {str(e)}")
            return []

    def clean_build(self) -> bool:
        """执行完整清理"""
        logger.info("执行完整清理...")
        result = self._run_make("distclean")
        return result.returncode == 0
