modified file: kernel/trace/trace.c
--- patchfile/gregkh_linux_98fecc/linux-6.12.y/kernel/trace/trace.c
+++ patchfile/gregkh_linux_98fecc/adapted_linux-6.12.y/kernel/trace/trace.c
@@ -5248,6 +5248,9 @@
  	struct trace_array *tr = file_inode(filp)->i_private;
  	cpumask_var_t tracing_cpumask_new;
  	int err;
 +
 +	if (count == 0 || count > KMALLOC_MAX_SIZE)
 +		return -EINVAL;
  
  	if (!zalloc_cpumask_var(&tracing_cpumask_new, GFP_KERNEL))
  		return -ENOMEM;

""""""
