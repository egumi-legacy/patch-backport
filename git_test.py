import os
import git

def create_repo(repo_name):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(current_dir)
    repo_path = os.path.join("..", "..", "github_projects", repo_name)
    os.makedirs(repo_path, exist_ok=True)
    repo = git.Repo.init(repo_path)
    print(f"创建了新仓库: {repo_path}")
    return repo, repo_path

def create_initial_commit(repo, repo_path):
    file_path = os.path.join(repo_path, "example.txt")
    with open(file_path, "w") as f:
        f.write("这是一个示例文件。")
    repo.index.add(["example.txt"])
    repo.index.commit("初始提交")
    print("创建了初始提交")

def print_commit_history(repo):
    for commit in repo.iter_commits():
        print(f"提交: {commit.hexsha}")
        print(f"作者: {commit.author}")
        print(f"日期: {commit.authored_datetime}")
        print(f"消息: {commit.message}")
        print("-" * 40)

def create_and_switch_branch(repo, branch_name):
    new_branch = repo.create_head(branch_name)
    repo.head.reference = new_branch
    repo.head.reset(index=True, working_tree=True)
    print(f"切换到分支: {repo.active_branch}")

def modify_file_and_commit(repo, file_path, new_content, commit_message):
    with open(file_path, "a") as f:
        f.write(new_content)
    repo.index.add([os.path.basename(file_path)])
    repo.index.commit(commit_message)
    print(f"在 {repo.active_branch} 分支创建了新提交")

def merge_branch(repo, branch_name):
    main_branch = repo.heads.master
    repo.head.reference = main_branch
    repo.head.reset(index=True, working_tree=True)
    repo.git.merge(branch_name)
    print(f"将 {branch_name} 分支合并到 master")

def print_diff_between_last_two_commits(repo):
    commits = list(repo.iter_commits(max_count=2))
    diff = repo.git.diff(commits[1], commits[0])
    print("最近两次提交的差异:")
    print(diff)

def main():
    repo, repo_path = create_repo("git_practice_repo")
    # print("当前分支:", repo.active_branch)
    # create_initial_commit(repo, repo_path)
    # print_commit_history(repo)
    # 获取所有分支
    branches = repo.branches

    # 遍历每个分支并打印提交信息
    for branch in branches:
        print(f"Branch: {branch.name}")
        # 切换到该分支
        repo.git.checkout(branch.name)
        # 获取该分支的所有提交
        commits = list(repo.iter_commits())
        for commit in commits:
            print(f"  Commit: {commit.hexsha} - {commit.message.strip()}")
    
    for branch in repo.refs:
        print(branch)
    
    
    # create_and_switch_branch(repo, "new-feature")
    # print("当前分支:", repo.active_branch)
    # print_commit_history(repo)
    
    # file_path = os.path.join(repo_path, "example.txt")
    # modify_file_and_commit(repo, file_path, "\n这是新的一行。", "添加了新行")
    
    # merge_branch(repo, "new-feature")
    
    # print_diff_between_last_two_commits(repo)

if __name__ == "__main__":
    main()

