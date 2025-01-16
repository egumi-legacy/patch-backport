modified file: include/linux/trace_events.h
--- patchfile/gregkh_linux_452f4b/linux-6.12.y/include/linux/trace_events.h
+++ patchfile/gregkh_linux_452f4b/adapted_linux-6.12.y/include/linux/trace_events.h
@@ -375,7 +375,7 @@
  	struct list_head	list;
  	struct trace_event_class *class;
  	union {
 -		char			*name;
 +		const char		*name;
  		struct tracepoint	*tp;
  	};

""""""
