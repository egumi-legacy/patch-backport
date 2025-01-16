modified file: drivers/scsi/mpi3mr/mpi3mr_fw.c
--- patchfile/gregkh_linux_fb6eb9/linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr_fw.c
+++ patchfile/gregkh_linux_fb6eb9/adapted_linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr_fw.c
@@ -1036,6 +1036,36 @@
  }
  
 +static inline bool mpi3mr_is_fault_recoverable(struct mpi3mr_ioc *mrioc)
 +{
 +	u32 fault;
 +
 +	fault = (readl(&mrioc->sysif_regs->fault) &
 +		      MPI3_SYSIF_FAULT_CODE_MASK);
 +
 +	switch (fault) {
 +	case MPI3_SYSIF_FAULT_CODE_COMPLETE_RESET_NEEDED:
 +	case MPI3_SYSIF_FAULT_CODE_POWER_CYCLE_REQUIRED:
 +		ioc_warn(mrioc,
 +		    "controller requires system power cycle, marking controller as unrecoverable\n");
 +		return false;
 +	case MPI3_SYSIF_FAULT_CODE_INSUFFICIENT_PCI_SLOT_POWER:
 +		ioc_warn(mrioc,
 +		    "controller faulted due to insufficient power,\n"
 +		    " try by connecting it to a different slot\n");
 +		return false;
 +	default:
 +		break;
 +	}
 +	return true;
 +}
 +
 +/**
   * mpi3mr_print_fault_info - Display fault information
   * @mrioc: Adapter instance reference
   *
@@ -1372,6 +1402,11 @@
  	base_info = lo_hi_readq(&mrioc->sysif_regs->ioc_information);
  	ioc_info(mrioc, "ioc_status(0x%08x), ioc_config(0x%08x), ioc_info(0x%016llx) at the bringup\n",
  	    ioc_status, ioc_config, base_info);
 +
 +	if (!mpi3mr_is_fault_recoverable(mrioc)) {
 +		mrioc->unrecoverable = 1;
 +		goto out_device_not_present;
 +	}
  
  	mrioc->ready_timeout =
@@ -2733,6 +2768,11 @@
  
  	mpi3mr_print_fault_info(mrioc);
  	mrioc->diagsave_timeout = 0;
 +
 +	if (!mpi3mr_is_fault_recoverable(mrioc)) {
 +		mrioc->unrecoverable = 1;
 +		goto schedule_work;
 +	}
  
  	switch (trigger_data.fault) {
  	case MPI3_SYSIF_FAULT_CODE_COMPLETE_RESET_NEEDED:

""""""
