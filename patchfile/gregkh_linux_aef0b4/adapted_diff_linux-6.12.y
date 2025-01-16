modified file: drivers/gpu/drm/xe/xe_devcoredump.c
--- patchfile/gregkh_linux_aef0b4/linux-6.12.y/drivers/gpu/drm/xe/xe_devcoredump.c
+++ patchfile/gregkh_linux_aef0b4/adapted_linux-6.12.y/drivers/gpu/drm/xe/xe_devcoredump.c
@@ -21,6 +21,7 @@
  #include "xe_guc_submit.h"
  #include "xe_hw_engine.h"
  #include "xe_sched_job.h"
 +#include "xe_pm.h"
  #include "xe_vm.h"
  
  	fw_ref = xe_force_wake_get(gt_to_fw(ss->gt), XE_FORCEWAKE_ALL);
@@ -156,6 +160,8 @@
  	xe_vm_snapshot_capture_delayed(ss->vm);
  	xe_guc_exec_queue_snapshot_capture_delayed(ss->ge);
  	xe_force_wake_put(gt_to_fw(ss->gt), fw_ref);
 +
 +	xe_pm_runtime_put(xe);
  
  	ss->read.size = __xe_devcoredump_read(NULL, INT_MAX, coredump);

""""""
