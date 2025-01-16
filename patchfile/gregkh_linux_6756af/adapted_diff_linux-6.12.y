modified file: fs/udf/namei.c
--- patchfile/gregkh_linux_6756af/linux-6.12.y/fs/udf/namei.c
+++ patchfile/gregkh_linux_6756af/adapted_linux-6.12.y/fs/udf/namei.c
@@ -787,8 +787,18 @@
  			retval = -ENOTEMPTY;
  			if (!empty_dir(new_inode))
  				goto out_oiter;
 -		}
 +			retval = -EFSCORRUPTED;
 +			if (new_inode->i_nlink != 2)
 +				goto out_oiter;
 +		}
 +		retval = -EFSCORRUPTED;
 +		if (old_dir->i_nlink < 3)
 +			goto out_oiter;
  		is_dir = true;
 +	} else if (new_inode) {
 +		retval = -EFSCORRUPTED;
 +		if (new_inode->i_nlink < 1)
 +			goto out_oiter;
  	}
  	if (is_dir && old_dir != new_dir) {
  		retval = udf_fiiter_find_entry(old_inode, &dotdot_name,

""""""
