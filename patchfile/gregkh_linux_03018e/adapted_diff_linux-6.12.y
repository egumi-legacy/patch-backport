modified file: fs/btrfs/inode.c
--- patchfile/gregkh_linux_03018e/linux-6.12.y/fs/btrfs/inode.c
+++ patchfile/gregkh_linux_03018e/adapted_linux-6.12.y/fs/btrfs/inode.c
@@ -9780,15 +9780,16 @@
  	struct btrfs_fs_info *fs_info = root->fs_info;
  	struct extent_io_tree *io_tree = &BTRFS_I(inode)->io_tree;
  	struct extent_state *cached_state = NULL;
 -	struct extent_map *em = NULL;
  	struct btrfs_chunk_map *map = NULL;
  	struct btrfs_device *device = NULL;
  	struct btrfs_swap_info bsi = {
  		.lowest_ppage = (sector_t)-1ULL,
  	};
 +	struct btrfs_backref_share_check_ctx *backref_ctx = NULL;
 +	struct btrfs_path *path = NULL;
  	int ret = 0;
  	u64 isize;
 -	u64 start;
 +	u64 prev_extent_end = 0;
  
 +		if (ret > 0) {
  			btrfs_warn(fs_info, "swapfile must not have holes");
  			ret = -EINVAL;
  			goto out;
  		}
 -		if (em->disk_bytenr == EXTENT_MAP_INLINE) {
 +
 +		leaf = path->nodes[0];
 +		ei = btrfs_item_ptr(leaf, path->slots[0], struct btrfs_file_extent_item);
 +
 +		if (btrfs_file_extent_type(leaf, ei) == BTRFS_FILE_EXTENT_INLINE) {
 +		btrfs_release_path(path);
 +
 +		ret = btrfs_is_data_extent_shared(BTRFS_I(inode), disk_bytenr,
 +						  extent_gen, backref_ctx);
  		if (ret < 0) {
  			goto out;
 -		} else if (ret) {
 -			ret = 0;
 -		} else {
 +		} else if (ret > 0) {
  			btrfs_warn(fs_info,
  				   "swapfile must not be copy-on-write");
  			ret = -EINVAL;
@@ -9950,7 +9995,6 @@
  
  		physical_block_start = (map->stripes[0].physical +
  					(logical_block_start - map->start));
 -		len = min(len, map->chunk_len - (logical_block_start - map->start));
  		btrfs_free_chunk_map(map);
  		map = NULL;
  
@@ -9991,20 +10035,16 @@
  				if (ret)
  					goto out;
  			}
 -			bsi.start = start;
 +			bsi.start = key.offset;
  			bsi.block_start = physical_block_start;
  			bsi.block_len = len;
  		}
 -
 -		start += len;
  	}
  
  	if (bsi.block_len)
  		ret = btrfs_add_swap_extent(sis, &bsi);
  
  out:
 -	if (!IS_ERR_OR_NULL(em))
 -		free_extent_map(em);
  	if (!IS_ERR_OR_NULL(map))
  		btrfs_free_chunk_map(map);
  

""""""
