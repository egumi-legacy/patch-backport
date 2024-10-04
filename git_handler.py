import git
import os
import pprint

class GitHandler:
    def __init__(self, repo_path=""):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(current_dir)
        repo_path = os.path.join("..", "..", "github_projects", "git_practice_repo")
        if not os.path.exists(repo_path):
            print(f"仓库路径不存在: {repo_path}")
            return 
        self.repo_path = repo_path
        self.repo = git.Repo(repo_path)

    def _execute_git_command(self, command, *args, **kwargs):
        try:
            return getattr(self.repo.git, command)(*args, **kwargs), True
        except git.GitCommandError as e:
            print(f"{command}失败: {str(e)}")
            return None, False

    def get_commit_info(self, commit_hash):
        commit = self.repo.commit(commit_hash)
        return {
            "hash": commit.hexsha,
            "author": commit.author.name,
            "date": commit.authored_datetime,
            "message": commit.message
        }

    def apply_patch(self, patch_file):
        return self._execute_git_command('apply', patch_file)[1]

    def checkout_version(self, version):
        return self._execute_git_command('checkout', version)[1]

    def create_branch(self, branch_name):
        return self._execute_git_command('checkout', '-b', branch_name)[1]

    def commit_changes(self, message):
        success = self._execute_git_command('add', '.')[1]
        if success:
            return self._execute_git_command('commit', '-m', message)[1]
        return False

    def get_diff(self, commit_hash):
        return self.repo.git.show(commit_hash)

    def get_file_content(self, file_path, commit_hash='HEAD'):
        return self.repo.git.show(f'{commit_hash}:{file_path}')

    def get_branch_name(self):
        return self.repo.active_branch.name

    def get_all_branches(self):
        return [branch.name for branch in self.repo.branches]

    def get_remote_branches(self):
        return [remote.name for remote in self.repo.remotes]

    def push_branch(self, branch_name):
        return self._execute_git_command('push', 'origin', branch_name)[1]

    def pull_branch(self, branch_name):
        return self._execute_git_command('pull', 'origin', branch_name)[1]

    def merge_branch(self, branch_name):
        return self._execute_git_command('merge', branch_name)[1]

    def print_commit_history(self, length=-1):
        commits = list(self.repo.iter_commits())
        if length == -1:
            length = len(commits)
        for commit in commits[:length]:
            print(f"提交: {commit.hexsha}")
            print(f"作者: {commit.author}")
            print(f"日期: {commit.authored_datetime}")
            print(f"消息: {commit.message}")
            print("-" * 40)

    def get_current_branch_info(self):
        branch = self.repo.active_branch
        print("当前分支信息:")
        print("name: ", branch.name)
        print("最近三次提交:")
        self.print_commit_history(3)
        return True

    def get_commit_history(self, file_path):
        commits = self.repo.git.log('--pretty=format:%H %ad | %s', file_path)
        return [commit.split(' | ') for commit in commits.split('\n')]

    def get_file_history(self, file_path):
        return self.repo.git.log('--pretty=format:%H %ad | %s', file_path)

    def get_file_diff(self, file_path, commit_hash='HEAD'):
        return self.repo.git.diff(commit_hash, file_path)

    def get_file_status(self, file_path):
        return self.repo.git.status(file_path)

    def get_commit_count(self, file_path):
        return len(self.repo.git.log('--pretty=format:%H', file_path).split('\n'))

    def get_commit_stats(self, commit_hash):
        commit = self.repo.commit(commit_hash)
        return {
            "additions": commit.stats.total['insertions'],
            "deletions": commit.stats.total['deletions']
        }

    def get_file_changes(self, file_path, commit_hash='HEAD'):
        return self.repo.git.diff(commit_hash, file_path).split('\n')



git_handler = GitHandler()
# git_handler.get_file_changes("git_handler.py")
git_handler.get_current_branch_info()
git_handler.check