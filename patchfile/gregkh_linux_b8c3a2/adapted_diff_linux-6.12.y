modified file: arch/x86/events/intel/ds.c
--- patchfile/gregkh_linux_b8c3a2/linux-6.12.y/arch/x86/events/intel/ds.c
+++ patchfile/gregkh_linux_b8c3a2/adapted_linux-6.12.y/arch/x86/events/intel/ds.c
@@ -2496,6 +2496,7 @@
  			x86_pmu.large_pebs_flags |= PERF_SAMPLE_TIME;
  			break;
  
 +		case 6:
  		case 5:
  			x86_pmu.pebs_ept = 1;
  			fallthrough;

""""""
