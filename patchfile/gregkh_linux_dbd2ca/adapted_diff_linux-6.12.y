modified file: io_uring/io_uring.c
--- patchfile/gregkh_linux_dbd2ca/linux-6.12.y/io_uring/io_uring.c
+++ patchfile/gregkh_linux_dbd2ca/adapted_linux-6.12.y/io_uring/io_uring.c
@@ -515,7 +515,11 @@
  	struct io_uring_task *tctx = req->task->io_uring;
  
  	BUG_ON(!tctx);
 -	BUG_ON(!tctx->io_wq);
 +
 +	if ((current->flags & PF_KTHREAD) || !tctx->io_wq) {
 +		io_req_task_queue_fail(req, -ECANCELED);
 +		return;
 +	}
  
  	io_prep_async_link(req);

""""""
