modified file: tools/tracing/rtla/src/timerlat_hist.c
--- patchfile/gregkh_linux_6cc45f/linux-6.12.y/tools/tracing/rtla/src/timerlat_hist.c
+++ patchfile/gregkh_linux_6cc45f/adapted_linux-6.12.y/tools/tracing/rtla/src/timerlat_hist.c
@@ -281,6 +281,21 @@
  }
  
 +static void format_summary_value(struct trace_seq *seq,
 +				 int count,
 +				 unsigned long long val,
 +				 bool avg)
 +{
 +	if (count)
 +		trace_seq_printf(seq, "%9llu ", avg ? val / count : val);
 +	else
 +		trace_seq_printf(seq, "%9c ", '-');
 +}
 +
 +/*
   * timerlat_print_summary - print the summary of the hist data to the output
   */
  static void
@@ -327,29 +342,23 @@
  		if (!data->hist[cpu].irq_count && !data->hist[cpu].thread_count)
  			continue;
  
 -		if (!params->no_irq) {
 -			if (data->hist[cpu].irq_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						data->hist[cpu].min_irq);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 -
 -		if (!params->no_thread) {
 -			if (data->hist[cpu].thread_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						data->hist[cpu].min_thread);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 -
 -		if (params->user_hist) {
 -			if (data->hist[cpu].user_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						data->hist[cpu].min_user);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 +		if (!params->no_irq)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].irq_count,
 +					     data->hist[cpu].min_irq,
 +					     false);
 +
 +		if (!params->no_thread)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].thread_count,
 +					     data->hist[cpu].min_thread,
 +					     false);
 +
 +		if (params->user_hist)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].user_count,
 +					     data->hist[cpu].min_user,
 +					     false);
  	}
  	trace_seq_printf(trace->seq, "\n");
  
@@ -363,29 +372,23 @@
  		if (!data->hist[cpu].irq_count && !data->hist[cpu].thread_count)
  			continue;
  
 -		if (!params->no_irq) {
 -			if (data->hist[cpu].irq_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						 data->hist[cpu].sum_irq / data->hist[cpu].irq_count);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 -
 -		if (!params->no_thread) {
 -			if (data->hist[cpu].thread_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						 data->hist[cpu].sum_thread / data->hist[cpu].thread_count);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 -
 -		if (params->user_hist) {
 -			if (data->hist[cpu].user_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						 data->hist[cpu].sum_user / data->hist[cpu].user_count);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 +		if (!params->no_irq)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].irq_count,
 +					     data->hist[cpu].sum_irq,
 +					     true);
 +
 +		if (!params->no_thread)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].thread_count,
 +					     data->hist[cpu].sum_thread,
 +					     true);
 +
 +		if (params->user_hist)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].user_count,
 +					     data->hist[cpu].sum_user,
 +					     true);
  	}
  	trace_seq_printf(trace->seq, "\n");
  
@@ -399,29 +402,23 @@
  		if (!data->hist[cpu].irq_count && !data->hist[cpu].thread_count)
  			continue;
  
 -		if (!params->no_irq) {
 -			if (data->hist[cpu].irq_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						 data->hist[cpu].max_irq);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 -
 -		if (!params->no_thread) {
 -			if (data->hist[cpu].thread_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						data->hist[cpu].max_thread);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 -
 -		if (params->user_hist) {
 -			if (data->hist[cpu].user_count)
 -				trace_seq_printf(trace->seq, "%9llu ",
 -						data->hist[cpu].max_user);
 -			else
 -				trace_seq_printf(trace->seq, "        - ");
 -		}
 +		if (!params->no_irq)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].irq_count,
 +					     data->hist[cpu].max_irq,
 +					     false);
 +
 +		if (!params->no_thread)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].thread_count,
 +					     data->hist[cpu].max_thread,
 +					     false);
 +
 +		if (params->user_hist)
 +			format_summary_value(trace->seq,
 +					     data->hist[cpu].user_count,
 +					     data->hist[cpu].max_user,
 +					     false);
  	}
  	trace_seq_printf(trace->seq, "\n");
  	trace_seq_do_printf(trace->seq);
@@ -505,16 +502,22 @@
  		trace_seq_printf(trace->seq, "min:  ");
  
  	if (!params->no_irq)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.min_irq);
 +		format_summary_value(trace->seq,
 +				     sum.irq_count,
 +				     sum.min_irq,
 +				     false);
  
  	if (!params->no_thread)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.min_thread);
 +		format_summary_value(trace->seq,
 +				     sum.thread_count,
 +				     sum.min_thread,
 +				     false);
  
  	if (params->user_hist)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.min_user);
 +		format_summary_value(trace->seq,
 +				     sum.user_count,
 +				     sum.min_user,
 +				     false);
  
  	trace_seq_printf(trace->seq, "\n");
  
@@ -522,16 +525,22 @@
  		trace_seq_printf(trace->seq, "avg:  ");
  
  	if (!params->no_irq)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.sum_irq / sum.irq_count);
 +		format_summary_value(trace->seq,
 +				     sum.irq_count,
 +				     sum.sum_irq,
 +				     true);
  
  	if (!params->no_thread)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.sum_thread / sum.thread_count);
 +		format_summary_value(trace->seq,
 +				     sum.thread_count,
 +				     sum.sum_thread,
 +				     true);
  
  	if (params->user_hist)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.sum_user / sum.user_count);
 +		format_summary_value(trace->seq,
 +				     sum.user_count,
 +				     sum.sum_user,
 +				     true);
  
  	trace_seq_printf(trace->seq, "\n");
  
@@ -539,16 +548,22 @@
  		trace_seq_printf(trace->seq, "max:  ");
  
  	if (!params->no_irq)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.max_irq);
 +		format_summary_value(trace->seq,
 +				     sum.irq_count,
 +				     sum.max_irq,
 +				     false);
  
  	if (!params->no_thread)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.max_thread);
 +		format_summary_value(trace->seq,
 +				     sum.thread_count,
 +				     sum.max_thread,
 +				     false);
  
  	if (params->user_hist)
 -		trace_seq_printf(trace->seq, "%9llu ",
 -				 sum.max_user);
 +		format_summary_value(trace->seq,
 +				     sum.user_count,
 +				     sum.max_user,
 +				     false);
  
  	trace_seq_printf(trace->seq, "\n");
  	trace_seq_do_printf(trace->seq);

""""""
