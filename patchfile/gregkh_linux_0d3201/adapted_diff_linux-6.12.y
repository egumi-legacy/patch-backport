modified file: drivers/scsi/mpi3mr/mpi3mr_os.c
--- patchfile/gregkh_linux_0d3201/linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr_os.c
+++ patchfile/gregkh_linux_0d3201/adapted_linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr_os.c
@@ -5215,7 +5215,7 @@
  	}
  
  	mrioc = shost_priv(shost);
 -	retval = ida_alloc_range(&mrioc_ida, 1, U8_MAX, GFP_KERNEL);
 +	retval = ida_alloc_range(&mrioc_ida, 0, U8_MAX, GFP_KERNEL);
  	if (retval < 0)
  		goto id_alloc_failed;
  	mrioc->id = (u8)retval;

""""""
