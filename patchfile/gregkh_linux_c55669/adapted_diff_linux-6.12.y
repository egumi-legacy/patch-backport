modified file: fs/udf/namei.c
--- patchfile/gregkh_linux_c55669/linux-6.12.y/fs/udf/namei.c
+++ patchfile/gregkh_linux_c55669/adapted_linux-6.12.y/fs/udf/namei.c
@@ -517,7 +517,11 @@
  			 inode->i_nlink);
  	clear_nlink(inode);
  	inode->i_size = 0;
 -	inode_dec_link_count(dir);
 +	if (dir->i_nlink >= 3)
 +		inode_dec_link_count(dir);
 +	else
 +		udf_warn(inode->i_sb, "parent dir link count too low (%u)\n",
 +			 dir->i_nlink);
  	udf_add_fid_counter(dir->i_sb, true, -1);
  	inode_set_mtime_to_ts(dir,
  			      inode_set_ctime_to_ts(dir, inode_set_ctime_current(inode)));

""""""
