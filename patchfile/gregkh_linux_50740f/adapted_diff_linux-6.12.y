modified file: drivers/scsi/megaraid/megaraid_sas_base.c
--- patchfile/gregkh_linux_50740f/linux-6.12.y/drivers/scsi/megaraid/megaraid_sas_base.c
+++ patchfile/gregkh_linux_50740f/adapted_linux-6.12.y/drivers/scsi/megaraid/megaraid_sas_base.c
@@ -8907,8 +8907,11 @@
  						   (ld_target_id / MEGASAS_MAX_DEV_PER_CHANNEL),
  						   (ld_target_id % MEGASAS_MAX_DEV_PER_CHANNEL),
  						   0);
 -			if (sdev1)
 +			if (sdev1) {
 +				mutex_unlock(&instance->reset_mutex);
  				megasas_remove_scsi_device(sdev1);
 +				mutex_lock(&instance->reset_mutex);
 +			}
  
  			event_type = SCAN_VD_CHANNEL;
  			break;

""""""
