modified file: fs/ceph/file.c
--- patchfile/gregkh_linux_9abee4/linux-6.12.y/fs/ceph/file.c
+++ patchfile/gregkh_linux_9abee4/adapted_linux-6.12.y/fs/ceph/file.c
@@ -1066,7 +1066,7 @@
  	if (ceph_inode_is_shutdown(inode))
  		return -EIO;
  
 -	if (!len)
 +	if (!len || !i_size)
  		return 0;

""""""
