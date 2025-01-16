modified file: include/linux/sched.h
--- patchfile/gregkh_linux_f718fa/linux-6.12.y/include/linux/sched.h
+++ patchfile/gregkh_linux_f718fa/adapted_linux-6.12.y/include/linux/sched.h
@@ -1626,8 +1626,9 @@
  	 * We're lying here, but rather than expose a completely new task state
  	 * to userspace, we can make this appear as if the task has gone through
  	 * a regular rt_mutex_lock() call.
 -	 */
 -	if (tsk_state & TASK_RTLOCK_WAIT)
 +	 * Report frozen tasks as uninterruptible.
 +	 */
 +	if ((tsk_state & TASK_RTLOCK_WAIT) || (tsk_state & TASK_FROZEN))
  		state = TASK_UNINTERRUPTIBLE;
  
  	return fls(state);

""""""
