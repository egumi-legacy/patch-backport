modified file: fs/btrfs/send.c
--- patchfile/gregkh_linux_0fba7b/linux-6.12.y/fs/btrfs/send.c
+++ patchfile/gregkh_linux_0fba7b/adapted_linux-6.12.y/fs/btrfs/send.c
@@ -5291,6 +5291,7 @@
  		unsigned cur_len = min_t(unsigned, len,
  					 PAGE_SIZE - pg_offset);
  
 +again:
  		folio = filemap_lock_folio(mapping, index);
  		if (IS_ERR(folio)) {
  			page_cache_sync_readahead(mapping,
@@ -5322,6 +5323,11 @@
  				folio_put(folio);
  				ret = -EIO;
  				break;
 +			}
 +			if (folio->mapping != mapping) {
 +				folio_unlock(folio);
 +				folio_put(folio);
 +				goto again;
  			}
  		}
  

""""""
