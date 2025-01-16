modified file: io_uring/sqpoll.c
--- patchfile/gregkh_linux_e33ac6/linux-6.12.y/io_uring/sqpoll.c
+++ patchfile/gregkh_linux_e33ac6/adapted_linux-6.12.y/io_uring/sqpoll.c
@@ -412,6 +412,7 @@
  __cold int io_sq_offload_create(struct io_ring_ctx *ctx,
  				struct io_uring_params *p)
  {
 +	struct task_struct *task_to_put = NULL;
  	int ret;
  
@@ -492,6 +493,7 @@
  		}
  
  		sqd->thread = tsk;
 +		task_to_put = get_task_struct(tsk);
  		ret = io_uring_alloc_task_context(tsk, ctx);
  		wake_up_new_task(tsk);
  		if (ret)
@@ -502,11 +504,15 @@
  		goto err;
  	}
  
 +	if (task_to_put)
 +		put_task_struct(task_to_put);
  	return 0;
  err_sqpoll:
  	complete(&ctx->sq_data->exited);
  err:
  	io_sq_thread_finish(ctx);
 +	if (task_to_put)
 +		put_task_struct(task_to_put);
  	return ret;
  }
  

""""""
