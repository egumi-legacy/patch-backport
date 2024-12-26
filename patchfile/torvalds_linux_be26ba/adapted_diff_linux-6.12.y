
""""""
modified file: block/blk-mq.c
--- patchfile/torvalds_linux_be26ba/linux-6.12.y/block/blk-mq.c
+++ patchfile/torvalds_linux_be26ba/adapted_linux-6.12.y/block/blk-mq.c
@@ -3292,6 +3292,7 @@
  			rq->bio = rq->biotail = bio;
  		}
  		bio = NULL;
 +		bio = NULL;
  	}
  

""""""
modified file: block/blk-sysfs.c
--- patchfile/torvalds_linux_be26ba/linux-6.12.y/block/blk-sysfs.c
+++ patchfile/torvalds_linux_be26ba/adapted_linux-6.12.y/block/blk-sysfs.c
@@ -131,7 +131,6 @@
  QUEUE_SYSFS_LIMIT_SHOW_SECTORS_TO_BYTES(max_write_zeroes_sectors)
  QUEUE_SYSFS_LIMIT_SHOW_SECTORS_TO_BYTES(atomic_write_max_sectors)
  QUEUE_SYSFS_LIMIT_SHOW_SECTORS_TO_BYTES(atomic_write_boundary_sectors)
 -
  #define QUEUE_SYSFS_LIMIT_SHOW_SECTORS_TO_KB(_field)			\
  static ssize_t queue_##_field##_show(struct gendisk *disk, char *page)	\
  {									\
@@ -176,6 +175,18 @@
  	if (err)
  		return err;
  	return ret;
 +}
 +
 +/*
 + * For zone append queue_max_zone_append_sectors does not just return the
 + * underlying queue limits, but actually contains a calculation.  Because of
 + * that we can't simply use QUEUE_SYSFS_LIMIT_SHOW_SECTORS_TO_BYTES here.
 + */
 +static ssize_t queue_zone_append_max_show(struct gendisk *disk, char *page)
 +{
 +	return sprintf(page, "%llu\n",
 +		(u64)queue_max_zone_append_sectors(disk->queue) <<
 +			SECTOR_SHIFT);
  }
  

""""""
