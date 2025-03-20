import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import subprocess
import os
import sys
import tempfile
import shutil
from datetime import datetime

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.backtrack_apply import BacktrackApplyModule
from core.parameter_manager import ModuleContext, Mode1Config, CommitContext

class TestBacktrackApplyModule(unittest.TestCase):
    """测试回溯应用模块"""
    
    def setUp(self):
        """测试前准备"""
        # 创建临时目录作为测试仓库路径
        self.temp_dir = tempfile.mkdtemp()
        
        # 模拟配置
        self.config = MagicMock()
        self.config.repo_path = self.temp_dir
        self.config.module_configs = {
            'backtrack_apply': {
                'stop_at': 'v1.0',
                'max_attempts': 10
            }
        }
        
        # 创建模块实例
        self.module = BacktrackApplyModule(self.config)
        
        # 模拟上下文
        self.context = MagicMock(spec=ModuleContext)
        self.context.config = self.config
        self.context.commit = MagicMock(spec=CommitContext)
        self.context.commit.commit_sha = '1234567890abcdef'
        self.context.commit.patch_url = 'https://github.com/example/repo/commit/1234567890abcdef.patch'
        self.context.patch_dir = Path(self.temp_dir) / 'patches'
        os.makedirs(self.context.patch_dir, exist_ok=True)
    
    def tearDown(self):
        """测试后清理"""
        # 删除临时目录
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('modules.backtrack_apply.download_patch')
    def test_download_patch(self, mock_download):
        """测试下载补丁"""
        # 模拟下载成功
        mock_path = Path(self.temp_dir) / 'patches' / 'upstream_123456.patch'
        mock_download.return_value = mock_path
        mock_path.exists = MagicMock(return_value=True)
        
        # 执行测试
        result = self.module._download_patch(self.context)
        
        # 验证结果
        self.assertEqual(result, mock_path.absolute())
        mock_download.assert_called_once()
    
    def test_find_modified_files(self):
        """测试查找修改的文件"""
        # 创建模拟补丁文件
        patch_content = """
        diff --git a/file1.txt b/file1.txt
        index 1234567..abcdef 100644
        --- a/file1.txt
        +++ b/file1.txt
        @@ -1,3 +1,4 @@
        line1
        line2
        +line3
        line4
        diff --git a/dir/file2.py b/dir/file2.py
        index 9876543..fedcba 100644
        --- a/dir/file2.py
        +++ b/dir/file2.py
        @@ -10,5 +10,5 @@
        def function():
            return 1
        -# old comment
        +# new comment
        """
        
        patch_path = Path(self.temp_dir) / 'test.patch'
        with open(patch_path, 'w') as f:
            f.write(patch_content)
        
        # 执行测试
        result = self.module._find_modified_files(self.context, patch_path)
        
        # 验证结果
        self.assertEqual(len(result), 2)
        self.assertIn('file1.txt', result)
        self.assertIn('dir/file2.py', result)
    
    @patch('subprocess.run')
    def test_get_current_branch(self, mock_run):
        """测试获取当前分支"""
        # 模拟成功
        mock_process = MagicMock()
        mock_process.stdout = 'main\n'
        mock_process.returncode = 0
        mock_run.return_value = mock_process
        
        # 执行测试
        result = self.module._get_current_branch(self.temp_dir)
        
        # 验证结果
        self.assertEqual(result, 'main')
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_resolve_ref(self, mock_run):
        """测试解析引用"""
        # 模拟成功
        mock_process = MagicMock()
        mock_process.stdout = 'abcdef1234567890\n'
        mock_process.returncode = 0
        mock_run.return_value = mock_process
        
        # 执行测试
        result = self.module._resolve_ref(self.temp_dir, 'v1.0')
        
        # 验证结果
        self.assertEqual(result, 'abcdef1234567890')
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_get_file_history(self, mock_run):
        """测试获取文件历史"""
        # 模拟成功
        mock_process = MagicMock()
        mock_process.stdout = 'commit1\ncommit2\ncommit3\n'
        mock_process.returncode = 0
        mock_run.return_value = mock_process
        
        # 执行测试
        result = self.module._get_file_history(self.temp_dir, 'file.txt')
        
        # 验证结果
        self.assertEqual(len(result), 3)
        self.assertEqual(result, ['commit1', 'commit2', 'commit3'])
        mock_run.assert_called_once()
    
    @patch('modules.backtrack_apply.BacktrackApplyModule._get_current_branch')
    @patch('modules.backtrack_apply.BacktrackApplyModule._resolve_ref')
    @patch('modules.backtrack_apply.BacktrackApplyModule._get_file_history')
    @patch('modules.backtrack_apply.BacktrackApplyModule._create_temp_branch')
    @patch('modules.backtrack_apply.BacktrackApplyModule._apply_patch')
    @patch('modules.backtrack_apply.BacktrackApplyModule._cleanup_temp_branch')
    def test_backtrack_apply_success(self, mock_cleanup, mock_apply, mock_create, 
                                    mock_history, mock_resolve, mock_current):
        """测试回溯应用成功的情况"""
        # 模拟当前分支
        mock_current.return_value = 'main'
        
        # 模拟解析引用
        mock_resolve.return_value = 'v1.0_commit'
        
        # 模拟文件历史
        mock_history.return_value = ['commit1', 'commit2', 'commit3']
        
        # 模拟创建临时分支
        mock_create.return_value = True
        
        # 模拟应用补丁
        mock_apply.side_effect = [
            {'success': False, 'error': 'patch does not apply'},
            {'success': False, 'error': 'conflicts'},
            {'success': True, 'output': 'Applied patch successfully'}
        ]
        
        # 执行测试
        result = self.module._backtrack_apply(
            self.context, 
            Path(self.temp_dir) / 'test.patch',
            ['file1.txt', 'file2.py']
        )
        
        # 验证结果
        self.assertTrue(result['success'])
        self.assertEqual(result['applicable_version'], 'commit3')
        self.assertEqual(mock_apply.call_count, 3)
        self.assertEqual(mock_cleanup.call_count, 3)
    
    @patch('modules.backtrack_apply.BacktrackApplyModule._get_current_branch')
    @patch('modules.backtrack_apply.BacktrackApplyModule._get_file_history')
    @patch('modules.backtrack_apply.BacktrackApplyModule._create_temp_branch')
    @patch('modules.backtrack_apply.BacktrackApplyModule._apply_patch')
    @patch('modules.backtrack_apply.BacktrackApplyModule._cleanup_temp_branch')
    def test_backtrack_apply_failure(self, mock_cleanup, mock_apply, mock_create, 
                                    mock_history, mock_current):
        """测试回溯应用失败的情况"""
        # 模拟当前分支
        mock_current.return_value = 'main'
        
        # 模拟文件历史
        mock_history.return_value = ['commit1', 'commit2']
        
        # 模拟创建临时分支
        mock_create.return_value = True
        
        # 模拟应用补丁 - 都失败
        mock_apply.return_value = {'success': False, 'error': 'patch does not apply'}
        
        # 执行测试
        result = self.module._backtrack_apply(
            self.context, 
            Path(self.temp_dir) / 'test.patch',
            ['file1.txt']
        )
        
        # 验证结果
        self.assertFalse(result['success'])
        self.assertEqual(result['error_type'], 'no_compatible_version')
        self.assertEqual(mock_apply.call_count, 2)
        self.assertEqual(mock_cleanup.call_count, 2)
    
    @patch('modules.backtrack_apply.BacktrackApplyModule._download_patch')
    @patch('modules.backtrack_apply.BacktrackApplyModule._find_modified_files')
    @patch('modules.backtrack_apply.BacktrackApplyModule._backtrack_apply')
    def test_execute(self, mock_backtrack, mock_find_files, mock_download):
        """测试执行方法"""
        # 模拟下载补丁
        patch_path = Path(self.temp_dir) / 'patches' / 'upstream_123456.patch'
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        with open(patch_path, 'w') as f:
            f.write('test patch')
        mock_download.return_value = patch_path
        
        # 模拟找到修改的文件
        mock_find_files.return_value = ['file1.txt', 'file2.py']
        
        # 模拟回溯应用结果
        mock_backtrack.return_value = {
            'success': True,
            'message': '补丁可以应用于 abc1234',
            'applicable_version': 'abc1234',
            'last_compatible_commit': 'abc1234',
            'attempt_count': 3
        }
        
        # 设置模块状态
        self.module._should_run = MagicMock(return_value=True)
        self.module._update_metrics = MagicMock()
        self.module._save_metrics = MagicMock()
        
        # 执行测试
        result = self.module.execute(self.context)
        
        # 验证结果
        self.assertEqual(result, self.context)
        self.assertTrue(hasattr(self.context, 'backtrack_result'))
        self.assertTrue(self.context.backtrack_result['success'])
        mock_download.assert_called_once()
        mock_find_files.assert_called_once()
        mock_backtrack.assert_called_once()
        self.module._update_metrics.assert_called_once()
        self.module._save_metrics.assert_called_once()

if __name__ == '__main__':
    unittest.main() 