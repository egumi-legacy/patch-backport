modified file: fs/btrfs/ctree.c
--- patchfile/gregkh_linux_44f52b/linux-6.12.y/fs/btrfs/ctree.c
+++ patchfile/gregkh_linux_44f52b/adapted_linux-6.12.y/fs/btrfs/ctree.c
@@ -654,6 +654,8 @@
  			goto error_unlock_cow;
  		}
  	}
 +
 +	trace_btrfs_cow_block(root, buf, cow);
  	if (unlock_orig)
  		btrfs_tree_unlock(buf);
  	free_extent_buffer_stale(buf);
@@ -710,7 +712,6 @@
  {
  	struct btrfs_fs_info *fs_info = root->fs_info;
  	u64 search_start;
 -	int ret;
  
  	if (unlikely(test_bit(BTRFS_ROOT_DELETING, &root->state))) {
  		btrfs_abort_transaction(trans, -EUCLEAN);
@@ -751,12 +752,8 @@
  	 * Also We don't care about the error, as it's handled internally.
  	 */
  	btrfs_qgroup_trace_subtree_after_cow(trans, root, buf);
 -	ret = btrfs_force_cow_block(trans, root, buf, parent, parent_slot,
 -				    cow_ret, search_start, 0, nest);
 -
 -	trace_btrfs_cow_block(root, buf, *cow_ret);
 -
 -	return ret;
 +	return btrfs_force_cow_block(trans, root, buf, parent, parent_slot,
 +				     cow_ret, search_start, 0, nest);
  }
  ALLOW_ERROR_INJECTION(btrfs_cow_block, ERRNO);
  

""""""
