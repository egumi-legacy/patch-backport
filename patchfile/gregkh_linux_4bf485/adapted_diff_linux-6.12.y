modified file: block/blk-mq.c
--- patchfile/gregkh_linux_4bf485/linux-6.12.y/block/blk-mq.c
+++ patchfile/gregkh_linux_4bf485/adapted_linux-6.12.y/block/blk-mq.c
@@ -3903,23 +3903,23 @@
  {
  	hctx->queue_num = hctx_idx;
  
 +	hctx->tags = set->tags[hctx_idx];
 +
 +	if (set->ops->init_hctx &&
 +	    set->ops->init_hctx(hctx, set->driver_data, hctx_idx))
 +		goto fail;
 +
 +	if (blk_mq_init_request(set, hctx->fq->flush_rq, hctx_idx,
 +				hctx->numa_node))
 +		goto exit_hctx;
 +
 +	if (xa_insert(&q->hctx_table, hctx_idx, hctx, GFP_KERNEL))
 +		goto exit_flush_rq;
 +
  	if (!(hctx->flags & BLK_MQ_F_STACKING))
  		cpuhp_state_add_instance_nocalls(CPUHP_AP_BLK_MQ_ONLINE,
  				&hctx->cpuhp_online);
  	cpuhp_state_add_instance_nocalls(CPUHP_BLK_MQ_DEAD, &hctx->cpuhp_dead);
 -
 -	hctx->tags = set->tags[hctx_idx];
 -
 -	if (set->ops->init_hctx &&
 -	    set->ops->init_hctx(hctx, set->driver_data, hctx_idx))
 -		goto unregister_cpu_notifier;
 -
 -	if (blk_mq_init_request(set, hctx->fq->flush_rq, hctx_idx,
 -				hctx->numa_node))
 -		goto exit_hctx;
 -
 -	if (xa_insert(&q->hctx_table, hctx_idx, hctx, GFP_KERNEL))
 -		goto exit_flush_rq;
  
  	return 0;
  
@@ -3929,8 +3929,7 @@
   exit_hctx:
  	if (set->ops->exit_hctx)
  		set->ops->exit_hctx(hctx, hctx_idx);
 - unregister_cpu_notifier:
 -	blk_mq_remove_cpuhp(hctx);
 + fail:
  	return -1;
  }
  

""""""
