import subprocess
from pathlib import Path
import tempfile
import shutil
from loguru import logger
import difflib
import json
from datetime import datetime
from patch_utils import download_patch
from config_manager import ProjectConfig
from adaptation_pipeline_bak import AdaptationPipeline

class PatchEvaluator:
    def __init__(self, config: ProjectConfig):
        """
        初始化评估器
        
        :param config: 项目配置对象
        """
        self.config = config
        self.repo_path = config.repo_path
        if not self.repo_path or not self.repo_path.exists():
            raise ValueError(f"Git仓库路径不存在: {self.repo_path}")
        
        # 创建临时工作目录
        self.work_dir = Path(tempfile.mkdtemp())
        logger.info(f"创建临时工作目录: {self.work_dir}")

        # 设置patch文件存储路径
        self.patch_dir = Path(config.patch_dir)
        self.patch_dir.mkdir(parents=True, exist_ok=True)
        
        # 评估结果存储路径
        self.evaluation_dir = Path(config.evaluation_dir)
        self.evaluation_dir.mkdir(parents=True, exist_ok=True)
        
        # # 缓存设置
        self.use_cached_patches = config.use_cached_patches
        self.last_apply_success = False
        self.error_count = 0

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
        url_hash = patch_url.split('/')[-1][:6]  # 使用commit hash的前6位
        cache_name = f"{patch_type}_{url_hash}.patch"
        cache_path = self.patch_dir / cache_name
        
        return download_patch(patch_url, cache_path, self.use_cached_patches)

    def cleanup_test_branch(self, branch_name):
        """
        清理测试分支
        
        :param branch_name: 要清理的分支名称
        """
        if not branch_name:
            return
        
        try:
            # 首先切换回目标版本分支
            subprocess.run(
                ['git', 'checkout', self.config['target_version']],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            # 删除测试分支
            subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"清理测试分支: {branch_name}")
        except subprocess.CalledProcessError as e:
            logger.warning(f"清理分支时发生错误: {e.stderr}")
        except Exception as e:
            logger.warning(f"清理分支时发生错误: {str(e)}")

    def prepare_repo_branch(self):
        """
        准备一个干净的分支用于测试
        
        :return: 创建的分支名称，如果失败则返回None
        """
        branch_name = f"test_patch_{self.config['target_version']}"
        try:
            # 确保在目标版本的基础上创建新分支
            subprocess.run(
                ['git', 'checkout', self.config['target_version']],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            # 如果分支已存在，先删除它
            try:
                subprocess.run(
                    ['git', 'branch', '-D', branch_name],
                    cwd=self.repo_path,
                    check=True,
                    capture_output=True,
                    text=True
                )
                logger.info(f"删除已存在的测试分支: {branch_name}")
            except subprocess.CalledProcessError:
                # 如果分支不存在，忽略错误
                pass
            
            # 创建新的测试分支
            subprocess.run(
                ['git', 'checkout', '-b', branch_name],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"创建测试分支: {branch_name}")
            
            # 确保工作区干净
            subprocess.run(
                ['git', 'reset', '--hard', 'HEAD'],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ['git', 'clean', '-fd'],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True
            )
            
            return branch_name
        except subprocess.CalledProcessError as e:
            logger.error(f"准备测试分支失败: {e.stderr}")
            # 发生错误时，尝试清理
            self.cleanup_test_branch(branch_name)
            return None
        except Exception as e:
            logger.error(f"准备测试分支时发生错误: {str(e)}")
            # 发生错误时，尝试清理
            self.cleanup_test_branch(branch_name)
            return None

    def apply_upstream_patch(self, patch_path):
        """尝试应用上游patch"""
        try:
            # 将patch_path转换为绝对路径
            absolute_patch_path = Path(patch_path).resolve()
            if not absolute_patch_path.exists():
                logger.error(f"Patch文件不存在: {absolute_patch_path}")
                return {'success': False, 'error': f"Patch文件不存在: {absolute_patch_path}"}
            
            result = subprocess.run(
                ['git', 'am', str(absolute_patch_path)],
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
            files_copied = False
            for file_path in adapted_dir.rglob('*'):
                if file_path.is_file():
                    relative_path = file_path.relative_to(adapted_dir)
                    target_path = self.repo_path / relative_path
                    if target_path.exists():
                        shutil.copy2(file_path, target_path)
                        files_copied = True
                        logger.info(f"复制文件: {file_path}")
            
            if not files_copied:
                logger.warning("没有找到需要复制的文件")
                return False
                    
            # 检查是否有改动
            status = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            
            if not status.stdout.strip():
                logger.warning("没有检测到文件改动")
                return False
            
            # 创建commit
            subprocess.run(['git', 'add', '.'], cwd=self.repo_path, check=True)
            commit_msg = f"Adapted patch for {self.config['target_version']}"
            result = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Commit失败: {result.stderr}")
                return False
            
            logger.info("成功应用适配后的更改并创建commit")
            return True
            
        except Exception as e:
            logger.error(f"应用适配更改失败: {str(e)}")
            return False

    def generate_adapted_patch(self):
        """生成适配后的patch文件"""
        patch_path = self.work_dir / "adapted.patch"
        logger.debug(f"adapted_patch_path:{patch_path.absolute}")
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
            patch_dir = Path(self.config['basedir']) / 'patches'
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
            'target_version': self.config['target_version'],
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
        
        # 添加安全检查
        upstream_apply = results.get('upstream_apply', {})
        if upstream_apply:
            if upstream_apply.get('success'):
                summary['notes'].append("上游patch可以直接应用")
                summary['status'] = 'direct_apply_success'
            else:
                summary['notes'].append("上游patch无法直接应用")
                summary['status'] = 'needs_adaptation'
        
        adapted_apply = results.get('adapted_apply', {})
        if adapted_apply:
            if adapted_apply.get('success'):
                summary['notes'].append("适配patch应用成功")
                if summary['status'] == 'needs_adaptation':
                    summary['status'] = 'adaptation_success'
            else:
                summary['notes'].append("适配patch应用失败")
                summary['status'] = 'adaptation_failed'
        
        patch_comparison = results.get('patch_comparison', {})
        if patch_comparison:
            similarity = patch_comparison.get('similarity', 0)
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
        保存批量评估结果，包括成功率统计和适配效果分析
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        repo_url = self.config['patch_url']
        owner = repo_url.split('/')[3]
        repo = repo_url.split('/')[4]
        save_dir = Path('patchfile') / f"{owner}_{repo}_evaluation"
        save_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = save_dir / f"batch_evaluation_{timestamp}.json"
        adaptation_report_file = save_dir / f"adaptation_analysis_{timestamp}.json"
        
        # 获取基础统计（添加安全检查）
        total_patches = len(batch_results)
        direct_apply_success = sum(1 for r in batch_results 
            if r.get('evaluation') and 
            r['evaluation'].get('upstream_apply') and 
            r['evaluation']['upstream_apply'].get('success'))
        adapted_apply_success = sum(1 for r in batch_results 
            if r.get('evaluation') and
            r['evaluation'].get('adapted_apply') and 
            r['evaluation']['adapted_apply'].get('success'))
        
        # 生成基础评估报告
        evaluation_report = {
            'timestamp': timestamp,
            'target_version': self.config['target_version'],
            'statistics': {
                'total_patches': total_patches,
                'direct_apply_success': direct_apply_success,
                'direct_apply_success_rate': direct_apply_success / total_patches if total_patches > 0 else 0,
                'adapted_apply_success': adapted_apply_success,
                'adapted_apply_success_rate': adapted_apply_success / total_patches if total_patches > 0 else 0
            },
            'detailed_results': [
                {
                    'commit_info': result.get('commit_info', {}),
                    'results': {
                        'upstream_patch_apply': {
                            'success': (result.get('evaluation', {}).get('upstream_apply', {}) or {}).get('success', False),
                            'error': (result.get('evaluation', {}).get('upstream_apply', {}) or {}).get('error')
                        },
                        'adapted_patch_apply': {
                            'success': (result.get('evaluation', {}).get('adapted_apply', {}) or {}).get('success', False),
                            'error': (result.get('evaluation', {}).get('adapted_apply', {}) or {}).get('error')
                        },
                        'patch_comparison': result.get('evaluation', {}).get('patch_comparison')
                    },
                    'summary': self._generate_summary(result.get('evaluation', {}))
                }
                for result in batch_results
            ]
        }
        
        # 生成适配效果分析报告
        adaptation_analysis = self.analyze_adaptation_effectiveness(batch_results)
        
        # 保存报告
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation_report, f, indent=2, ensure_ascii=False)
        
        with open(adaptation_report_file, 'w', encoding='utf-8') as f:
            json.dump(adaptation_analysis, f, indent=2, ensure_ascii=False)
        
        # 输出统计信息
        logger.info(f"评估报告已保存到: {report_file}")
        logger.info(f"适配分析报告已保存到: {adaptation_report_file}")
        logger.info("\n=== 基础统计 ===")
        logger.info(f"总补丁数: {total_patches}")
        logger.info(f"直接应用成功率: {direct_apply_success}/{total_patches} ({evaluation_report['statistics']['direct_apply_success_rate']:.2%})")
        logger.info(f"适配后应用成功率: {adapted_apply_success}/{total_patches} ({evaluation_report['statistics']['adapted_apply_success_rate']:.2%})")
        logger.info("\n=== 适配效果分析 ===")
        logger.info(f"直接应用失败数量: {adaptation_analysis['direct_failed']}")
        logger.info(f"其中经过适配后成功数量: {adaptation_analysis['adapted_success']}")
        logger.info(f"适配有效率: {adaptation_analysis['adaptation_effectiveness']:.2%}")
        
        return report_file, adaptation_report_file

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

    def analyze_adaptation_effectiveness(self, batch_results):
        """分析适配的有效性"""
        analysis = {
            'total_patches': len(batch_results),
            'direct_failed': 0,
            'adapted_success': 0,
            'compilation_success': 0,  # 新增编译成功数
            'adaptation_effectiveness': 0.0,
            'compilation_effectiveness': 0.0,  # 新增编译成功率
            'successful_adaptations': [],
            'failed_adaptations': [],
            'compilation_failures': []  # 新增编译失败记录
        }

        for result in batch_results:
            commit_info = result.get('commit_info', {})
            eval_results = result.get('evaluation', {})
            
            # 检查是否直接应用失败
            upstream_apply = eval_results.get('upstream_apply', {})
            direct_apply_failed = not upstream_apply or not upstream_apply.get('success')
            
            if direct_apply_failed:
                analysis['direct_failed'] += 1
                
                # 检查适配后是否成功
                adapted_apply = eval_results.get('adapted_apply', {})
                adapted_success = adapted_apply and adapted_apply.get('success')
                
                if adapted_success:
                    analysis['adapted_success'] += 1
                    
                    # 检查编译是否成功
                    compilation = eval_results.get('compilation', {})
                    if compilation and compilation.get('success'):
                        analysis['compilation_success'] += 1
                        analysis['successful_adaptations'].append({
                            'commit_sha': commit_info.get('upstream_sha'),
                            'patch_url': commit_info.get('patch_url'),
                            'similarity': (eval_results.get('patch_comparison', {}) or {}).get('similarity', 0),
                            'modified_files': compilation.get('modified_files', [])
                        })
                    else:
                        analysis['compilation_failures'].append({
                            'commit_sha': commit_info.get('upstream_sha'),
                            'patch_url': commit_info.get('patch_url'),
                            'error': compilation.get('error'),
                            'modified_files': compilation.get('modified_files', [])
                        })
                else:
                    analysis['failed_adaptations'].append({
                        'commit_sha': commit_info.get('upstream_sha'),
                        'patch_url': commit_info.get('patch_url'),
                        'error': (eval_results.get('adapted_apply', {}) or {}).get('error')
                    })
        
        if analysis['direct_failed'] > 0:
            analysis['adaptation_effectiveness'] = analysis['adapted_success'] / analysis['direct_failed']
            if analysis['adapted_success'] > 0:
                analysis['compilation_effectiveness'] = analysis['compilation_success'] / analysis['adapted_success']

        return analysis

    
    # def evaluate_patch(self, upstream_patch_url, downstream_patch_url, adapted_dir, commit_info=None):
    #     """评估patch处理过程"""
    #     results = {
    #         'upstream_apply': None,
    #         'adapted_apply': None,
    #         'patch_comparison': None
    #     }
        
    #     try:
    #         # 1. 准备测试分支
    #         branch_name = self.prepare_repo_branch()
    #         if not branch_name:
    #             return results

    #         # 2. 下载上下游patch，并尝试应用上游patch
    #         upstream_patch = self.download_patch_by_type(upstream_patch_url, 'upstream')
    #         logger.info("starting downloading downstream patch:")
    #         downstream_patch = self.download_patch_by_type(downstream_patch_url, 'downstream')
    #         if upstream_patch:
    #             results['upstream_apply'] = self.apply_upstream_patch(upstream_patch)

    #         # 3. 应用适配后的更改并生成patch
    #         if adapted_dir:
    #             adapted_result = self.apply_adapted_changes(adapted_dir)
    #             if adapted_result:
    #                 adapted_patch = self.generate_adapted_patch()
    #                 if adapted_patch:
    #                     # 4. 重置工作区，以便测试patch应用
    #                     subprocess.run(['git', 'reset', '--hard', 'HEAD^'], 
    #                         cwd=self.repo_path, capture_output=True)
    #                     # 5. 尝试应用适配后的patch
    #                     results['adapted_apply'] = self.apply_adapted_patch(adapted_patch)
                        
    #                     # 6. 开始比较
    #                     if downstream_patch:
    #                         results['patch_comparison'] = self.compare_patches(downstream_patch)
    #                     else:
    #                         logger.error("the downstreaming patch raises error.")
    #                         raise Exception("the downstreaming patch raises error.")

    #         # 6. 保存评估结果
    #         if commit_info:
    #             self.save_evaluation_results(commit_info, results)

    #     except Exception as e:
    #         logger.error(f"评估过程发生错误: {str(e)}")
    #     finally:
    #         # 清理：切回原分支并删除测试分支
    #         subprocess.run(['git', 'checkout', self.config['target_version']], 
    #                      cwd=self.repo_path)
    #         subprocess.run(['git', 'branch', '-D', branch_name], 
    #                      cwd=self.repo_path)

    #     return results
    def try_direct_apply(self, patch_file, commit_info=None):
        """
        尝试直接应用上游补丁
        
        :param upstream_patch_url: 上游补丁URL
        :param commit_info: 提交信息
        :return: 评估结果字典
        """
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
            # upstream_patch = self.download_patch_by_type(upstream_patch_url, 'upstream')
            # if upstream_patch:
            results['upstream_apply'] = self.apply_upstream_patch(patch_file)

        except Exception as e:
            logger.error(f"直接应用过程中出错: {str(e)}")
            results['upstream_apply'] = {'success': False, 'error': str(e)}
        finally:
            # 清理工作
            self.cleanup_test_branch(branch_name)
        
        return results

    

    # def apply_single_file_patch(self, patch_file):
    #     """
    #     应用单个文件的patch
        
    #     :param patch_file: patch文件路径
    #     :return: 应用结果
    #     """
    #     try:
    #         result = subprocess.run(
    #             ['git', 'apply', '--check', str(patch_file)],
    #             cwd=self.repo_path,
    #             capture_output=True,
    #             text=True
    #         )
            
    #         if result.returncode == 0:
    #             # 如果检查通过，实际应用patch
    #             apply_result = subprocess.run(
    #                 ['git', 'apply', str(patch_file)],
    #                 cwd=self.repo_path,
    #                 capture_output=True,
    #                 text=True
    #             )
    #             success = apply_result.returncode == 0
    #             return {
    #                 'success': success,
    #                 'output': apply_result.stdout,
    #                 'error': apply_result.stderr if not success else None
    #             }
    #         else:
    #             return {
    #                 'success': False,
    #                 'error': result.stderr
    #             }
    #     except Exception as e:
    #         return {
    #             'success': False,
    #             'error': str(e)
    #         }

    def try_compile(self, adapted_dir=None):
        """
        尝试编译修改后的代码
        
        :param adapted_dir: 适配后的代码目录，如果为None则编译当前工作区
        :return: 编译结果字典
        """
        result = {
            'success': False,
            'error': None,
            'modified_files': [],
            'compilation_output': None
        }
        
        try:
            # 如果提供了适配目录，先复制文件
            if adapted_dir:
                logger.info(f"开始复制适配后的文件从 {adapted_dir}")
                for file_path in adapted_dir.rglob('*.c'):
                    if file_path.is_file():
                        relative_path = file_path.relative_to(adapted_dir)
                        target_path = self.repo_path / relative_path
                        if target_path.exists():
                            shutil.copy2(file_path, target_path)
                            result['modified_files'].append(str(relative_path))
                            logger.debug(f"复制文件: {relative_path}")
                logger.info(f"共复制了 {len(result['modified_files'])} 个文件")
            
            # 对每个修改的.c文件进行单独编译
            compilation_results = []
            for c_file in result['modified_files']:
                logger.info(f"开始编译文件: {c_file}")
                try:
                    # 获取完整的源文件路径和输出路径
                    source_path = self.repo_path / c_file
                    output_dir = self.repo_path / Path(c_file).parent
                    o_file = output_dir / Path(c_file).with_suffix('.o').name
                    
                    # 确保输出目录存在
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    # 获取所有可能的头文件目录
                    include_dirs = [
                        self.repo_path,  # 仓库根目录
                        self.repo_path / 'include',  # 标准include目录
                        self.repo_path / 'arch/x86/include',  # 架构相关头文件
                        output_dir,  # 源文件所在目录
                    ]
                    
                    # 构建编译命令
                    compile_cmd = ['gcc', '-c']
                    
                    # 添加所有包含路径
                    for inc_dir in include_dirs:
                        if inc_dir.exists():
                            compile_cmd.extend(['-I', str(inc_dir)])
                    
                    # 添加常用的内核编译选项
                    compile_cmd.extend([
                        '-Wall',  # 启用所有警告
                        '-Werror',  # 将警告视为错误
                        '-D__KERNEL__',  # 定义内核编译宏
                        '-DMODULE',  # 定义模块编译宏
                        '-fno-pic',  # 禁用位置无关代码
                        '-fno-pie',  # 禁用位置无关可执行文件
                    ])
                    
                    # 添加源文件和输出文件
                    compile_cmd.extend([
                        str(source_path),  # 源文件
                        '-o', str(o_file)  # 输出文件
                    ])
                    
                    logger.debug(f"编译命令: {' '.join(compile_cmd)}")
                    
                    compile_result = subprocess.run(
                        compile_cmd,
                        cwd=self.repo_path,
                        capture_output=True,
                        text=True
                    )
                    
                    file_result = {
                        'file': c_file,
                        'success': compile_result.returncode == 0,
                        'output': compile_result.stdout,
                        'error': compile_result.stderr if compile_result.returncode != 0 else None,
                        'command': ' '.join(compile_cmd)  # 记录使用的命令，方便调试
                    }
                    
                    compilation_results.append(file_result)
                    
                    if file_result['success']:
                        logger.info(f"文件 {c_file} 编译成功")
                    else:
                        logger.error(f"文件 {c_file} 编译失败")
                        logger.debug(f"编译错误信息: {file_result['error']}")
                        logger.debug(f"使用的命令: {file_result['command']}")
                    
                    # 清理生成的.o文件
                    if o_file.exists():
                        o_file.unlink()
                        logger.debug(f"清理编译产物: {o_file}")
                
                except Exception as e:
                    logger.error(f"编译文件 {c_file} 时发生错误: {e}")
                    compilation_results.append({
                        'file': c_file,
                        'success': False,
                        'error': str(e)
                    })
            
            # 汇总编译结果
            result['success'] = all(r['success'] for r in compilation_results)
            result['compilation_output'] = '\n'.join(
                f"{r['file']}:\n{r['output']}{r['error'] or ''}"
                for r in compilation_results
            )
            if not result['success']:
                result['error'] = '\n'.join(
                    f"{r['file']}: {r['error']}"
                    for r in compilation_results
                    if not r['success']
                )
        
        except Exception as e:
            result['success'] = False
            result['error'] = f"编译过程发生错误: {str(e)}"
            logger.error(f"编译过程发生错误: {e}")
        
        return result

    def evaluate_adapted_patch(self, adapted_dir, downstream_patch_url=None):
        """评估适配后的补丁"""
        results = {
            'adapted_apply': None,
            'patch_comparison': None,
            'compilation': None
        }
        
    #     try:
    #     # 1. 准备测试分支
    #     branch_name = self.prepare_repo_branch()
    #     if not branch_name:
    #         return results

    #     # 2. 应用适配后的更改并生成patch
    #     if adapted_dir:
    #         adapted_result = self.apply_adapted_changes(adapted_dir)
    #         if adapted_result:
    #             adapted_patch = self.generate_adapted_patch()
    #             if adapted_patch:
    #                 # 3. 重置工作区，测试patch应用
    #                 subprocess.run(['git', 'reset', '--hard', 'HEAD^'], 
    #                     cwd=self.repo_path, capture_output=True)
    #                 # 4. 尝试应用适配后的patch
    #                 results['adapted_apply'] = self.apply_adapted_patch(adapted_patch)
                    
    #                 # 5. 如果patch应用成功，进行编译测试
    #                 if results['adapted_apply']['success']:
    #                     results['compilation'] = self.try_compile(adapted_dir)
                    
    #                 # 6. 如果提供了下游patch，进行比较
    #                 if downstream_patch_url:
    #                     downstream_patch = self.download_patch_by_type(
    #                         downstream_patch_url, 'downstream')
    #                     if downstream_patch:
    #                         results['patch_comparison'] = self.compare_patches(downstream_patch)

    # except Exception as e:
    #     logger.error(f"评估适配patch过程中出错: {str(e)}")
    #     results['adapted_apply'] = {'success': False, 'error': str(e)}
    # finally:
    #     # 清理：切回原分支并删除测试分支
    #     subprocess.run(['git', 'checkout', self.config['target_version']], 
    #                     cwd=self.repo_path)
    #     subprocess.run(['git', 'branch', '-D', branch_name], 
    #                     cwd=self.repo_path)
        # 使用pipeline处理
        pipeline_config = {
            "enabled_modules": ["patch_adapter", "compiler"],
            "results_dir": self.config.base_dir / "results",
            "patch_adapter_config": self.config.dict(),
            "compiler_config": self.config.dict()
        }
        
        pipeline = AdaptationPipeline(pipeline_config)
        result = pipeline.process_patch({
            "adapted_dir": adapted_dir,
            "downstream_patch_url": downstream_patch_url
        })
        
        # 转换结果格式以保持兼容性
        results.update(self._convert_pipeline_result(result))
        return results

    def _convert_pipeline_result(self, result):
        """将pipeline结果转换为评估结果"""
        # 实现转换逻辑
        # 这里需要根据pipeline的输出格式进行转换
        # 这里只是一个示例，实际转换逻辑需要根据pipeline的输出格式进行调整
        return {
            'adapted_apply': result.get('adapted_apply'),
            'patch_comparison': result.get('patch_comparison'),
            'compilation': result.get('compilation')
        }

