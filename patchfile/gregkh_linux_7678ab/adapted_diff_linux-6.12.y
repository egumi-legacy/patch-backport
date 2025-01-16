modified file: drivers/block/virtio_blk.c
--- patchfile/gregkh_linux_7678ab/linux-6.12.y/drivers/block/virtio_blk.c
+++ patchfile/gregkh_linux_7678ab/adapted_linux-6.12.y/drivers/block/virtio_blk.c
@@ -1587,9 +1587,12 @@
  static int virtblk_freeze(struct virtio_device *vdev)
  {
  	struct virtio_blk *vblk = vdev->priv;
 +	struct request_queue *q = vblk->disk->queue;
  
 -	blk_mq_freeze_queue(vblk->disk->queue);
 +	blk_mq_freeze_queue(q);
 +	blk_mq_quiesce_queue_nowait(q);
 +	blk_mq_unfreeze_queue(q);
  
  	virtio_reset_device(vdev);
@@ -1613,8 +1616,8 @@
  		return ret;
  
  	virtio_device_ready(vdev);
 -
 -	blk_mq_unfreeze_queue(vblk->disk->queue);
 +	blk_mq_unquiesce_queue(vblk->disk->queue);
 +
  	return 0;
  }
  #endif

""""""
