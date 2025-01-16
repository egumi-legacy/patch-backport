modified file: fs/btrfs/sysfs.c
--- patchfile/gregkh_linux_fca432/linux-6.12.y/fs/btrfs/sysfs.c
+++ patchfile/gregkh_linux_fca432/adapted_linux-6.12.y/fs/btrfs/sysfs.c
@@ -1118,7 +1118,7 @@
  {
  	struct btrfs_fs_info *fs_info = to_fs_info(kobj);
  
 -	return sysfs_emit(buf, "%u\n", fs_info->super_copy->nodesize);
 +	return sysfs_emit(buf, "%u\n", fs_info->nodesize);
  }
  
  BTRFS_ATTR(, nodesize, btrfs_nodesize_show);
@@ -1128,7 +1128,7 @@
  {
  	struct btrfs_fs_info *fs_info = to_fs_info(kobj);
  
 -	return sysfs_emit(buf, "%u\n", fs_info->super_copy->sectorsize);
 +	return sysfs_emit(buf, "%u\n", fs_info->sectorsize);
  }
  
  BTRFS_ATTR(, sectorsize, btrfs_sectorsize_show);
@@ -1180,7 +1180,7 @@
  {
  	struct btrfs_fs_info *fs_info = to_fs_info(kobj);
  
 -	return sysfs_emit(buf, "%u\n", fs_info->super_copy->sectorsize);
 +	return sysfs_emit(buf, "%u\n", fs_info->sectorsize);
  }
  
  BTRFS_ATTR(, clone_alignment, btrfs_clone_alignment_show);

""""""
