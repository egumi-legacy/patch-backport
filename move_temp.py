import os
import shutil
from pathlib import Path
from loguru import logger
def move_dirs_with_only_evaluations(source_dir, target_dir):
    """
    移动只包含一个evaluations子文件夹的目录到目标目录
    
    参数:
    source_dir (str): 源目录路径
    target_dir (str): 目标目录路径
    
    返回:
    int: 成功移动的目录数量
    """
    # 转换为Path对象以便更好地处理路径
    source_path = Path(source_dir)
    target_path = Path(target_dir)
    
    # 确保目标目录存在
    target_path.mkdir(parents=True, exist_ok=True)
    
    # 跟踪移动的目录数
    moved_count = 0
    
    logger.info(f"len of source directories: {len([d for d in source_path.iterdir() if d.is_dir()])}")
    logger.info(f"len of target directories: {len([d for d in target_path.iterdir() if d.is_dir()])}")
    # 遍历源目录中的所有子目录
    for subdir in [d for d in source_path.iterdir() if d.is_dir()]:
        # 获取子目录中的所有子目录
        sub_directories = [d for d in subdir.iterdir() if d.is_dir()]

        
        
        # 检查是否只有两个以下的子目录，且其中有名称为"evaluations"
        if len(sub_directories) <= 2 and ("evaluations" in [d.name for d in sub_directories]):
            # all(not f.is_file() for f in subdir.iterdir())):  # 确保没有文件，只有evaluations文件夹
            shutil.rmtree(subdir)
            moved_count += 1
            logger.warning(f"成功移除了 {subdir}")
            # # 构建目标路径
            # dest_path = target_path / subdir.name
            
            # # 如果目标已存在，添加后缀避免冲突
            # if dest_path.exists():
            #     logger.warning(f"目标路径 {dest_path} 已存在，删除源路径 {subdir}")
            #     shutil.rmtree(subdir)
            #     continue
            #     # i = 1
            #     # while (target_path / f"{subdir.name}_{i}").exists():
            #     #     i += 1
            #     # dest_path = target_path / f"{subdir.name}_{i}"
            
            # # 移动目录
            # try:
            #     print(f"移动 {subdir} 到 {dest_path}")
            #     shutil.move(str(subdir), str(dest_path))
            #     moved_count += 1
            # except Exception as e:
            #     print(f"移动 {subdir} 时出错: {e}")
    
    print(f"成功移除了 {moved_count} 个目录")
    return moved_count

# def remove_dirs_with_only_evaluations(source_dir):
#     """
#     删除只包含一个evaluations子文件夹的目录
    
#     参数:
#     source_dir (str): 源目录路径
#     """


# 使用示例
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 3:
        print("用法: python move_temp.py <源目录> <目标目录>")
        sys.exit(1)
    
    source_directory = sys.argv[1]
    target_directory = sys.argv[2]
    
    print(f"从 {source_directory} 移动文件夹到 {target_directory}")
    move_dirs_with_only_evaluations(source_directory, target_directory)
