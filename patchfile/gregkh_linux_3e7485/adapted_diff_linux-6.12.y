modified file: fs/btrfs/relocation.c
--- patchfile/gregkh_linux_3e7485/linux-6.12.y/fs/btrfs/relocation.c
+++ patchfile/gregkh_linux_3e7485/adapted_linux-6.12.y/fs/btrfs/relocation.c
@@ -2902,6 +2902,7 @@
  	const bool use_rst = btrfs_need_stripe_tree_update(fs_info, rc->block_group->flags);
  
  	ASSERT(index <= last_index);
 +again:
  	folio = filemap_lock_folio(inode->i_mapping, index);
  	if (IS_ERR(folio)) {
  
@@ -2936,6 +2937,11 @@
  		if (!folio_test_uptodate(folio)) {
  			ret = -EIO;
  			goto release_folio;
 +		}
 +		if (folio->mapping != inode->i_mapping) {
 +			folio_unlock(folio);
 +			folio_put(folio);
 +			goto again;
  		}
  	}
  

""""""
