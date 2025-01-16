modified file: drivers/block/ublk_drv.c
--- patchfile/gregkh_linux_75cd40/linux-6.12.y/drivers/block/ublk_drv.c
+++ patchfile/gregkh_linux_75cd40/adapted_linux-6.12.y/drivers/block/ublk_drv.c
@@ -1599,6 +1599,21 @@
  	blk_mq_kick_requeue_list(ub->ub_disk->queue);
  }
  
 +static struct gendisk *ublk_detach_disk(struct ublk_device *ub)
 +{
 +	struct gendisk *disk;
 +
 +	/* Sync with ublk_abort_queue() by holding the lock */
 +	spin_lock(&ub->lock);
 +	disk = ub->ub_disk;
 +	ub->dev_info.state = UBLK_S_DEV_DEAD;
 +	ub->dev_info.ublksrv_pid = -1;
 +	ub->ub_disk = NULL;
 +	spin_unlock(&ub->lock);
 +
 +	return disk;
 +}
 +
  static void ublk_stop_dev(struct ublk_device *ub)
  {
  	struct gendisk *disk;
@@ -1612,14 +1627,7 @@
  		ublk_unquiesce_dev(ub);
  	}
  	del_gendisk(ub->ub_disk);
 -
 -	/* Sync with ublk_abort_queue() by holding the lock */
 -	spin_lock(&ub->lock);
 -	disk = ub->ub_disk;
 -	ub->dev_info.state = UBLK_S_DEV_DEAD;
 -	ub->dev_info.ublksrv_pid = -1;
 -	ub->ub_disk = NULL;
 -	spin_unlock(&ub->lock);
 +	disk = ublk_detach_disk(ub);
  	put_disk(disk);
   unlock:
  	mutex_unlock(&ub->mutex);
@@ -2295,7 +2303,7 @@
  
  out_put_cdev:
  	if (ret) {
 -		ub->dev_info.state = UBLK_S_DEV_DEAD;
 +		ublk_detach_disk(ub);
  		ublk_put_device(ub);
  	}
  	if (ret)

""""""
