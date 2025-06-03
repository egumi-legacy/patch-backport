import requests
import re
import dotenv
import pprint
import os
import subprocess
import base64
import traceback
import shutil
from pathlib import Path
from llm_assistant import LLMAssistant
from loguru import logger
import difflib
from difflib import SequenceMatcher
from patch_adapter_utils import PatchAdapterUtils
from git_operations import GitOperations
from patch_utils import download_patch
import html
from core.parameter_manager import ModuleContext
from patch_utils import parse_github_url

class PatchProcessor:
    def __init__(self, context: ModuleContext):
        """
        初始化补丁处理器
        
        Args:
            context: 模块上下文对象
        """
        self.context = context
        self.config = context.config  # 向后兼容
        self.url = context.commit.patch_url
        self.target_version = context.config.target_version
        self.base_dir = context.commit.base_dir
        self.model = context.config.model
        
        # 初始化Git操作，传递上下文
        self.git_operations = GitOperations(context)
        
        # 设置patch相关路径
        self.patch_dir = context.commit.patch_dir
        
        # 设置其他参数
        dotenv.load_dotenv()
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.headers = {
            'User-Agent': 'Apifox/1.0.0 (https://apifox.com)',
            'Accept': 'application/json, application/vnd.github+json',
            'Authorization': f'Bearer {self.github_token}',
            'Host': 'api.github.com',
            'Connection': 'keep-alive'
        }
        
        # 从url解析仓库信息
        self.commit_info = parse_github_url(self.url)
        self.owner = self.commit_info['owner']
        self.repo = self.commit_info['name']
        if self.commit_info['commit_sha']:
            self.patch_commit_sha = self.commit_info['commit_sha']
        
        # 缓存设置
        self.use_cached_patches = getattr(context.config, 'use_cached_patches', False)

    def download_patch_by_type(self, url, patch_type):
        """
        根据类型下载补丁
        
        Args:
            url: 补丁URL
            patch_type: 补丁类型 ('upstream' 或 'downstream')
        
        Returns:
            Path: 补丁文件路径
        """
        # 确保补丁目录存在
        patch_dir = self.base_dir / 'patch'
        patch_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成输出路径
        output_file = patch_dir / f"{patch_type}_patch.txt"
        
        # 调用download_patch函数，只传入两个参数
        return download_patch(url, output_file)
        

    def parse_patch(self, patch_content):
        # 解析patch内容
        pass

    def adapt_patch(self, patch_content, target_version):
        # 调整patch以适应目标版本
        pass

    def get_patch_files(self, commit_content):
        patch_files = commit_content['files']
        # patch_message = commit_info['commit']['message']
        patch_contents = []

        for patch_file in patch_files:
            patch_content = {}
            patch_content['filename'] = patch_file['filename']
            patch_content['patch'] = patch_file['patch']
            patch_content['sha'] = patch_file['sha']
            patch_contents.append(patch_content)
        return patch_contents

    def generate_folder_diff(self, folder1, folder2, output_file, context_lines=3):
        # 生成两个文件夹之间的差异，类似git diff的输出。
        # folder1: 新版本文件夹
        # folder2: 目标版本文件夹，通常为旧版本
        with open(output_file, 'w', encoding='utf-8') as out_file:
            files1 = set(f.relative_to(folder1) for f in folder1.rglob('*') if f.is_file())
            files2 = set(f.relative_to(folder2) for f in folder2.rglob('*') if f.is_file())
            all_files = files1.union(files2)
            for file in sorted(all_files):
                path1 = folder1 / file
                path2 = folder2 / file
                if not path1.exists():
                    out_file.write(f"The file does not exist in the new version: {file}\n")
                    # with open(path2, 'r', encoding='utf-8') as f:
                    #     out_file.write(f.read())
                elif not path2.exists():
                    out_file.write(f"The file does not exist in the older (target) version: {file}\n")
                    # with open(path1, 'r', encoding='utf-8') as f:
                    #     out_file.write(f.read())
                else:
                    with open(path1, 'r', encoding='utf-8') as f1, open(path2, 'r', encoding='utf-8') as f2:
                        lines1 = f1.readlines()
                        lines2 = f2.readlines()
                        diff = list(difflib.unified_diff(
                            lines1, lines2,
                            fromfile=str(path1),
                            tofile=str(path2),
                            n=context_lines,
                            lineterm=''
                        ))
                        if diff:
                            out_file.write(f"modified file: {file}\n")
                            in_comment = False
                            for line in diff:
                                if line.strip().startswith('/*'):
                                    in_comment = True
                                if in_comment and '*/' in line:
                                    in_comment = False
                                    continue
                                if not in_comment:
                                    if line.startswith('@@'):
                                        out_file.write(line + '\n')
                                    elif line.startswith(('---', '+++')):
                                        out_file.write(line + '\n')
                                    else:
                                        out_file.write(' ' + line)
                out_file.write('\n' + '"' * 6 + '\n')  # 添加分隔线
        print(f"差异已保存到 {output_file}")

    def write_file_contents(self, file_contents, folder_name):
        # 使用context中的base_dir，而不是硬编码路径
        base_dir = self.base_dir

        for file_content in file_contents:
            file_path = base_dir / folder_name / file_content['filename']
            if not file_path.exists():
                if not file_path.parent.exists():
                    file_path.parent.mkdir(parents=True)
            file_path.write_text(file_content['content'])

    def get_response_path(self):
        """获取响应文件的路径"""
        output_file_name = f"output_{self.target_version}_{self.model}"
        return self.base_dir / output_file_name

    def save_response_to_project(self, response):
        # 将response写入到project文件夹中
        if response is None:
            return None
        output_path = self.get_response_path()
        # if not output_path.exists():
        #     output_path.parent.mkdir(parents=True)
            
        output_path.write_text(response)
        return output_path

   
    def apply_llm_patch(self, llm_response_path):
        base_dir = self.base_dir
        source_dir = base_dir / f'{self.target_version}'
        output_dir = base_dir / f"adapted_{self.target_version}"

        adapter = PatchAdapterUtils()
        adapter.generate_adapted_file(llm_response_path, source_dir, output_dir)
        

    # def _apply_patch_to_file(self, diff_content, source_file, target_file):
        

    def run(self):
        # 1. 使用已有的commit_info，不需要重新解析URL
        # commit_info已经在初始化时通过parse_github_url设置了
        try:
            commit_content = self.git_operations.get_commit_content(self.commit_info)
            
            # 检查commit_content是否有效
            if not commit_content or 'files' not in commit_content:
                logger.warning("获取提交内容失败或内容不完整，尝试使用本地仓库")
                # 确保有一个有效的文件列表，即使是空的
                file_list = []
            else:
                file_list = self.git_operations.get_commit_file_list(commit_content)
        except Exception as e:
            logger.error(f"获取提交内容失败: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            file_list = []
            commit_content = {"files": []}

        # 使用context.commit.base_dir而不是硬编码路径
        base_dir = self.base_dir
        
        # 2. 解析commit信息
        if not (base_dir / 'newer').exists() or not list((base_dir / 'newer').iterdir()):
            try:
                # 获取commit前的文件内容
                newer_file_contents = self.git_operations.get_file_before_commit(self.commit_info)
                if newer_file_contents:
                    self.write_file_contents(newer_file_contents, 'newer')
                else:
                    logger.warning("无法获取提交前的文件内容")
            except Exception as e:
                logger.error(f"获取提交前的文件内容失败: {e}")
                logger.error(f"错误堆栈: {traceback.format_exc()}")

        if not (base_dir / self.target_version).exists() or not list((base_dir / self.target_version).iterdir()):
            # 创建target_info字典，适应新的参数系统
            target_info = {
                'owner': self.owner,
                'name': self.repo,
                'branch': self.target_version
            }
            
            # 直接从context获取repo_path，不再使用字典访问
            repo_path = self.context.config.repo_path
            
            # 获取目标版本的文件内容
            try:
                target_file_contents = self.git_operations.get_file_contents_from_ref(
                    file_list, 
                    target_info,
                    True,  # 优先使用本地仓库
                    repo_path
                )
                if target_file_contents:
                    self.write_file_contents(target_file_contents, self.target_version)
                else:
                    logger.warning(f"无法获取目标版本 {self.target_version} 的文件内容")
            except Exception as e:
                logger.error(f"获取目标版本文件内容失败: {e}")
                logger.error(f"错误堆栈: {traceback.format_exc()}")

        # 3. 生成差异文件
        try:
            # 检查文件夹是否存在并且不为空
            newer_exists = (base_dir / 'newer').exists() and list((base_dir / 'newer').iterdir())
            target_exists = (base_dir / self.target_version).exists() and list((base_dir / self.target_version).iterdir())
            
            if newer_exists and target_exists:
                self.generate_folder_diff(base_dir / 'newer', base_dir / self.target_version, base_dir / 'diff')
            else:
                logger.warning(f"无法生成差异文件: newer文件夹存在={newer_exists}, {self.target_version}文件夹存在={target_exists}")
                # 创建一个空的diff文件，防止后续处理错误
                with open(base_dir / 'diff', 'w', encoding='utf-8') as f:
                    f.write("# 无法生成差异文件\n")
        except Exception as e:
            logger.error(f"生成差异文件失败: {e}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            # 创建一个包含错误信息的diff文件
            with open(base_dir / 'diff', 'w', encoding='utf-8') as f:
                f.write(f"# 生成差异文件失败: {str(e)}\n")

        # 4. 使用patch文件
        patch_path = self.context.commit.patch_path
        
        # 确保patch文件存在
        if not os.path.exists(patch_path):
            logger.warning(f"补丁文件不存在: {patch_path}")
            # 尝试使用git format-patch命令生成补丁
            try:
                if self.context.config.repo_path:
                    patch_dir = os.path.dirname(patch_path)
                    os.makedirs(patch_dir, exist_ok=True)
                    subprocess.run(
                        ['git', 'format-patch', '-1', self.commit_info['commit_sha'], '-o', patch_dir],
                        cwd=self.context.config.repo_path,
                        check=True
                    )
                    # 查找生成的补丁文件
                    patch_files = [f for f in os.listdir(patch_dir) if f.endswith('.patch')]
                    if patch_files:
                        # 使用第一个找到的补丁文件
                        new_patch_path = os.path.join(patch_dir, patch_files[0])
                        # 复制到预期的路径
                        shutil.copy(new_patch_path, patch_path)
                        logger.info(f"已使用git format-patch生成补丁文件: {patch_path}")
                    else:
                        logger.error("git format-patch未生成任何补丁文件")
            except Exception as e:
                logger.error(f"生成补丁文件失败: {e}")
        
        # 创建返回值
        patch_content = ""
        diff_content = ""
        
        try:
            if os.path.exists(patch_path):
                with open(patch_path, 'r', encoding='utf-8', errors='replace') as f:
                    patch_content = html.unescape(f.read())
        except Exception as e:
            logger.error(f"读取补丁文件失败: {e}")
        
        try:
            if os.path.exists(base_dir / 'diff'):
                with open(base_dir / 'diff', 'r', encoding='utf-8', errors='replace') as f:
                    diff_content = html.unescape(f.read())
        except Exception as e:
            logger.error(f"读取差异文件失败: {e}")
        
        patch_values = [{"patchCode": patch_content, "diffCode": diff_content}]
        
        # 返回结果
        return {
            "status": "success" if patch_content or diff_content else "error",
            "prompt_values": patch_values
        }
        
        

    def process_single_commit(self):
        """
        处理单个提交的补丁
        """
        # 运行基本处理流程
        patch_processor_outputs = self.run()
        self.config.update(**patch_processor_outputs)

        # 处理LLM响应
        use_cache = self.config.use_cache
        if use_cache:
            # 确保在使用缓存前设置缓存路径
            cache_path = self.get_response_path()
            self.config.extra_config.update({
                "cache_path": cache_path
            })
            logger.info(f"使用缓存路径: {cache_path}")

        # 调用LLM处理
        llm_assistant = LLMAssistant(self.config)
        llm_output = llm_assistant.run()
        self.config.update(**llm_output)

        # 处理LLM输出
        for response in llm_output["openai_responses"]:
            if not use_cache:
                output_path = self.save_response_to_project(response)
            else:
                output_path = self.config.extra_config["cache_path"]

            # 应用补丁并生成差异
            self.apply_llm_patch(output_path)
            self.generate_folder_diff(
                self.config.base_dir / self.config.target_version,
                self.config.base_dir / f'adapted_{self.config.target_version}',
                self.config.base_dir / f'adapted_diff_{self.config.target_version}'
            )
        
        

