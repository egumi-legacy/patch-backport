modified file: drivers/scsi/storvsc_drv.c
--- patchfile/gregkh_linux_b1aee7/linux-6.12.y/drivers/scsi/storvsc_drv.c
+++ patchfile/gregkh_linux_b1aee7/adapted_linux-6.12.y/drivers/scsi/storvsc_drv.c
@@ -148,6 +148,8 @@
   * storage functionality is available in the host.
  */
  static int vmstor_proto_version;
 +
 +static bool hv_dev_is_fc(struct hv_device *hv_dev);
  
  #define STORVSC_LOGGING_NONE	0
  #define STORVSC_LOGGING_ERROR	1
@@ -1138,6 +1140,7 @@
  	 * not correctly handle:
  	 * INQUIRY command with page code parameter set to 0x80
  	 * MODE_SENSE command with cmd[2] == 0x1c
 +	 * MAINTENANCE_IN is not supported by HyperV FC passthrough
  	 *
  	 * Setup srb and scsi status so this won't be fatal.
  	 * We do this so we can distinguish truly fatal failues
@@ -1145,7 +1148,9 @@
  	 */
  
  	if ((stor_pkt->vm_srb.cdb[0] == INQUIRY) ||
 -	   (stor_pkt->vm_srb.cdb[0] == MODE_SENSE)) {
 +	   (stor_pkt->vm_srb.cdb[0] == MODE_SENSE) ||
 +	   (stor_pkt->vm_srb.cdb[0] == MAINTENANCE_IN &&
 +	   hv_dev_is_fc(device))) {
  		vstor_packet->vm_srb.scsi_status = 0;
  		vstor_packet->vm_srb.srb_status = SRB_STATUS_SUCCESS;
  	}

""""""
