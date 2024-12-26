import subprocess
from pathlib import Path
import tempfile
import shutil
from loguru import logger
import difflib
import json
from datetime import datetime
from patch_utils import download_patch

class PatchEvaluator:
    def __init__(self, repo_path, inputs):
        """
        初始化评估器
        
        :param repo_path: 本地Git仓库路径
        :param inputs: 配置信息
        """
        self.repo_path = Path(repo_path)
        self.inputs = inputs
        if not self.repo_path.exists():
            raise ValueError(f"Git仓库路径不存在: {repo_path}")
        
        # 创建临时工作目录
        self.work_dir = Path(tempfile.mkdtemp())
        logger.info(f"创建临时工作目录: {self.work_dir}")

        # 设置patch文件存储路径
        self.patch_dir = Path(inputs['basedir']) / 'patches'
        self.patch_dir.mkdir(parents=True, exist_ok=True)
        
        # 评估结果存储路径
        self.evaluation_dir = Path(inputs['basedir']) / 'evaluations'
        self.evaluation_dir.mkdir(parents=True, exist_ok=True)
        
        # # 缓存设置
        self.use_cached_patches = inputs.get('use_cached_patches', False)

    def __del__(self):
        """清理临时目录"""
        if hasattr(self, 'work_dir') and self.work_dir.exists():
            shutil.rmtree(self.work_dir)
            logger.info(f"清理临时工作目录: {self.work_dir}")

    # def download_patch(self, patch_url, patch_type='upstream'):
    #     """
    #     下载patch文件，支持缓存
        
    #     :param patch_url: patch的URL
    #     :param patch_type: patch类型 ('upstream' 或 'downstream')
    #     :return: patch文件路径
    #     """
    #     # 生成缓存文件名
    #     url_hash = patch_url.split('/')[-1][:6]  # 使用commit hash的前6位
    #     cache_name = f"{patch_type}_{url_hash}.patch"
    #     cache_path = self.patch_dir / cache_name

    #     # 如果启用缓存且文件存在，直接返回
    #     if self.use_cached_patches: 
    #         if cache_path.exists():
    #             logger.info(f"使用缓存的patch文件: {cache_path}")
    #             return cache_path
    #         else:
    #             logger.info(f"缓存文件不存在, 下载patch: {cache_path}")

    #     # 下载patch
    #     patch_url = f"{patch_url}.patch"
    #     try:
    #         result = subprocess.run(
    #             ['curl', '-L', patch_url, '-o', str(cache_path)],
    #             check=True,
    #             capture_output=True,
    #             text=True
    #         )
    #         logger.info(f"下载patch文件成功: {cache_path}")
    #         return cache_path
    #     except subprocess.CalledProcessError as e:
    #         logger.error(f"下载patch失败: {e.stderr}")
    #         return None
    def download_patch_by_type(self, patch_url, patch_type='upstream'):
        """
        下载patch文件，支持缓存
        
        :param patch_url: patch的URL
        :param patch_type: patch类型 ('upstream' 或 'downstream')
        :return: patch文件路径
        """
        # 生成缓存文件名
        print(f"patch_url:{patch_url}")
        url_hash = patch_url.split('/')[-1][:6]  # 使用commit hash的前6位
        cache_name = f"{patch_type}_{url_hash}.patch"
        cache_path = self.patch_dir / cache_name
        
        return download_patch(patch_url, cache_path, self.use_cached_patches)

    def prepare_repo_branch(self):
        """准备一个干净的分支用于测试"""
        branch_name = f"test_patch_{self.inputs['target_version']}"
        try:
            # 确保在目标版本的基础上创建新分支
            subprocess.run(
                ['git', 'checkout', self.inputs['target_version']],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            # 创建新的测试分支
            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"创建测试分支: {branch_name}")
            return branch_name
        except subprocess.CalledProcessError as e:
            logger.error(f"准备测试分支失败: {e.stderr}")
            return None

    def apply_upstream_patch(self, patch_path):
        """尝试应用上游patch"""
        try:
            result = subprocess.run(
                ['git', 'am', str(patch_path)],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            success = result.returncode == 0
            logger.info(f"应用上游patch {'成功' if success else '失败'}")
            return {
                'success': success,
                'output': result.stdout,
                'error': result.stderr
            }
        except Exception as e:
            logger.error(f"应用patch时发生错误: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            # 无论成功与否，都清理git am状态
            subprocess.run(['git', 'am', '--abort'], cwd=self.repo_path, 
                         capture_output=True)

    def apply_adapted_changes(self, adapted_dir):
        """应用适配后的更改并创建commit"""
        try:
            # 复制适配后的文件到仓库
            for file_path in adapted_dir.rglob('*'):
                if file_path.is_file():
                    relative_path = file_path.relative_to(adapted_dir)
                    target_path = self.repo_path / relative_path
                    if target_path.exists():
                        shutil.copy2(file_path, target_path)
                        
            # 创建commit
            subprocess.run(['git', 'add', '.'], cwd=self.repo_path, check=True)
            commit_msg = f"Adapted patch  for {self.inputs['target_version']}"
            subprocess.run(['git', 'commit', '-m', commit_msg], 
                         cwd=self.repo_path, check=True)
            
            logger.info("成功应用适配后的更改并创建commit")
            return True
        except Exception as e:
            logger.error(f"应用适配更改失败: {str(e)}")
            return False

    def generate_adapted_patch(self):
        """生成适配后的patch文件"""
        patch_path = self.work_dir / "adapted.patch"
        try:
            subprocess.run(
                ['git', 'format-patch', '-1', '-o', str(self.work_dir)],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            # 重命名生成的patch文件
            generated_patch = next(self.work_dir.glob('*.patch'))
            generated_patch.rename(patch_path)
            logger.info(f"生成适配patch文件: {patch_path}")
            # 将生成的patch文件复制到patch_dir
            patch_dir = Path(self.inputs['basedir']) / 'patches'
            patch_dir.mkdir(exist_ok=True)
            shutil.copy2(patch_path, patch_dir / patch_path.name)
            return patch_path
        except Exception as e:
            logger.error(f"生成patch文件失败: {str(e)}")
            return None

    def compare_patches(self, downstream_patch):
        """比较适配patch和下游patch"""
        # # 下载下游patch
        # downstream_patch = self.work_dir / "downstream.patch"
        # subprocess.run(
        #     ['curl', '-L', f"{downstream_patch_url}.patch", '-o', str(downstream_patch)],
        #     check=True
        # )
        
        # 读取两个patch文件
        adapted_patch = self.work_dir / "adapted.patch"
        with open(adapted_patch) as f1, open(downstream_patch) as f2:
            adapted_lines = f1.readlines()
            downstream_lines = f2.readlines()

        # 计算差异
        diff = difflib.unified_diff(
            adapted_lines, 
            downstream_lines,
            fromfile='adapted_patch',
            tofile='downstream_patch'
        )
        
        # 计算相似度
        similarity = difflib.SequenceMatcher(
            None, 
            ''.join(adapted_lines), 
            ''.join(downstream_lines)
        ).ratio()

        return {
            'similarity': similarity,
            'diff': list(diff)
        }

    def save_evaluation_results(self, commit_info, results):
        """
        保存评估结果
        
        :param commit_info: 提交信息字典
        :param results: 评估结果字典
        """
        # 生成评估报告文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.evaluation_dir / f"evaluation_{timestamp}.json"
        
        # 整理评估结果
        evaluation_report = {
            'timestamp': timestamp,
            'commit_info': {
                'upstream_sha': commit_info.get('upstream_sha'),
                'downstream_sha': commit_info.get('downstream_sha'),
                'upstream_url': commit_info.get('patch_url'),
                'downstream_url': commit_info.get('reference_url'),
            },
            'target_version': self.inputs['target_version'],
            'results': {
                'upstream_patch_apply': {
                    'success': results['upstream_apply']['success'] if results['upstream_apply'] else False,
                    'error': results['upstream_apply']['error'] if results['upstream_apply'] and not results['upstream_apply']['success'] else None
                },
                'adapted_patch_apply': {
                    'success': results['adapted_apply'] if results['adapted_apply'] else False
                },
                'patch_comparison': results['patch_comparison'] if results['patch_comparison'] else None
            },
            'summary': self._generate_summary(results)
        }
        
        # 保存评估报告
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation_report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"评估报告已保存到: {report_file}")
        return report_file

    def _generate_summary(self, results):
        """生成评估结果摘要"""
        summary = {
            'status': 'unknown',
            'similarity_score': None,
            'notes': []
        }
        
        # 检查上游patch直接应用情况
        if results['upstream_apply']:
            if results['upstream_apply']['success']:
                summary['notes'].append("上游patch可以直接应用")
                summary['status'] = 'direct_apply_success'
            else:
                summary['notes'].append("上游patch无法直接应用")
                summary['status'] = 'needs_adaptation'
        
        # 检查适配patch情况
        if results['adapted_apply']:
            summary['notes'].append("适配patch应用成功")
            if summary['status'] == 'needs_adaptation':
                summary['status'] = 'adaptation_success'
        elif results['adapted_apply'] is False:
            summary['notes'].append("适配patch应用失败")
            summary['status'] = 'adaptation_failed'
        
        # 检查patch比较结果
        if results['patch_comparison']:
            similarity = results['patch_comparison']['similarity']
            summary['similarity_score'] = similarity
            if similarity >= 0.8:
                summary['notes'].append("与下游patch高度相似")
            elif similarity >= 0.5:
                summary['notes'].append("与下游patch部分相似")
            else:
                summary['notes'].append("与下游patch差异较大")
        
        return summary

    def save_batch_evaluation_results(self, batch_results):
        """
        保存批量评估结果，包括成功率统计
        
        :param batch_results: 包含多个评估结果的列表
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.evaluation_dir / f"batch_evaluation_{timestamp}.json"
        
        # 统计成功率
        total_patches = len(batch_results)
        direct_apply_success = 0
        adapted_apply_success = 0
        
        # 整理评估报告
        evaluation_report = {
            'timestamp': timestamp,
            'target_version': self.inputs['target_version'],
            'statistics': {
                'total_patches': total_patches,
                'direct_apply_success': 0,
                'direct_apply_success_rate': 0.0,
                'adapted_apply_success': 0,
                'adapted_apply_success_rate': 0.0
            },
            'detailed_results': []
        }
        
        # 处理每个评估结果
        for result in batch_results:
            commit_info = result['commit_info']
            eval_results = result['evaluation']
            
            # 统计成功次数
            if eval_results['upstream_apply'] and eval_results['upstream_apply']['success']:
                direct_apply_success += 1
            if eval_results['adapted_apply'] and eval_results['adapted_apply']['success']:
                adapted_apply_success += 1
            
            # 添加详细结果
            detailed_result = {
                'commit_info': {
                    'upstream_sha': commit_info.get('upstream_sha'),
                    'downstream_sha': commit_info.get('downstream_sha'),
                    'upstream_url': commit_info.get('patch_url'),
                    'downstream_url': commit_info.get('reference_url'),
                },
                'results': {
                    'upstream_patch_apply': {
                        'success': eval_results['upstream_apply']['success'] if eval_results['upstream_apply'] else False,
                        'error': eval_results['upstream_apply']['error'] if eval_results['upstream_apply'] and not eval_results['upstream_apply']['success'] else None
                    },
                    'adapted_patch_apply': {
                        'success': eval_results['adapted_apply']['success'] if eval_results['adapted_apply'] else False,
                        'error': eval_results['adapted_apply']['error'] if eval_results['adapted_apply'] and not eval_results['adapted_apply']['success'] else None
                    },
                    'patch_comparison': eval_results['patch_comparison'] if eval_results['patch_comparison'] else None
                },
                'summary': self._generate_summary(eval_results)
            }
            evaluation_report['detailed_results'].append(detailed_result)
        
        # 更新统计信息
        evaluation_report['statistics'].update({
            'direct_apply_success': direct_apply_success,
            'direct_apply_success_rate': direct_apply_success / total_patches if total_patches > 0 else 0,
            'adapted_apply_success': adapted_apply_success,
            'adapted_apply_success_rate': adapted_apply_success / total_patches if total_patches > 0 else 0
        })
        
        # 保存评估报告
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation_report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"批量评估报告已保存到: {report_file}")
        logger.info(f"统计结果:")
        logger.info(f"总补丁数: {total_patches}")
        logger.info(f"直接应用成功率: {direct_apply_success}/{total_patches} ({evaluation_report['statistics']['direct_apply_success_rate']:.2%})")
        logger.info(f"适配后应用成功率: {adapted_apply_success}/{total_patches} ({evaluation_report['statistics']['adapted_apply_success_rate']:.2%})")
        
        return report_file

    def apply_adapted_patch(self, patch_path):
        """
        应用适配后的patch
        
        :param patch_path: 适配后的patch文件路径
        :return: 应用结果字典
        """
        try:
            result = subprocess.run(
                ['git', 'am', str(patch_path)],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            success = result.returncode == 0
            logger.info(f"应用适配patch {'成功' if success else '失败'}")
            return {
                'success': success,
                'output': result.stdout,
                'error': result.stderr if not success else None
            }
        except Exception as e:
            logger.error(f"应用适配patch时发生错误: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            # 无论成功与否，都清理git am状态
            subprocess.run(['git', 'am', '--abort'], cwd=self.repo_path, 
                         capture_output=True)

    def evaluate_patch(self, upstream_patch_url, downstream_patch_url, adapted_dir, commit_info=None):
        """评估patch处理过程"""
        results = {
            'upstream_apply': None,
            'adapted_apply': None,
            'patch_comparison': None
        }
        
        try:
            # 1. 准备测试分支
            branch_name = self.prepare_repo_branch()
            if not branch_name:
                return results

            # 2. 下载并尝试应用上游patch
            upstream_patch = self.download_patch_by_type(upstream_patch_url, 'upstream')
            if upstream_patch:
                results['upstream_apply'] = self.apply_upstream_patch(upstream_patch)

            # 3. 应用适配后的更改并生成patch
            if adapted_dir:
                adapted_result = self.apply_adapted_changes(adapted_dir)
                if adapted_result:
                    adapted_patch = self.generate_adapted_patch()
                    if adapted_patch:
                        # 4. 尝试应用适配后的patch
                        results['adapted_apply'] = self.apply_adapted_patch(adapted_patch)
                        
                        # 5. 下载下游patch并比较
                        downstream_patch = self.download_patch_by_type(downstream_patch_url, 'downstream')
                        if downstream_patch:
                            results['patch_comparison'] = self.compare_patches(downstream_patch)

            # 6. 保存评估结果
            if commit_info:
                self.save_evaluation_results(commit_info, results)

        except Exception as e:
            logger.error(f"评估过程发生错误: {str(e)}")
        finally:
            # 清理：切回原分支并删除测试分支
            subprocess.run(['git', 'checkout', self.inputs['target_version']], 
                         cwd=self.repo_path)
            subprocess.run(['git', 'branch', '-D', branch_name], 
                         cwd=self.repo_path)

        return results

