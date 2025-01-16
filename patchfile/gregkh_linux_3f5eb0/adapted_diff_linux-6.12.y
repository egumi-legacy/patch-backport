modified file: drivers/scsi/mpt3sas/mpt3sas_base.c
--- patchfile/gregkh_linux_3f5eb0/linux-6.12.y/drivers/scsi/mpt3sas/mpt3sas_base.c
+++ patchfile/gregkh_linux_3f5eb0/adapted_linux-6.12.y/drivers/scsi/mpt3sas/mpt3sas_base.c
@@ -7041,11 +7041,12 @@
  	int i;
  	u8 failed;
  	__le32 *mfp;
 +	int ret_val;
  
  	if ((ioc->base_readl_ext_retry(&ioc->chip->Doorbell) & MPI2_DOORBELL_USED)) {
  		ioc_err(ioc, "doorbell is in use (line=%d)\n", __LINE__);
 -		return -EFAULT;
 +		goto doorbell_diag_reset;
  	}
  
@@ -7135,6 +7136,10 @@
  			    le32_to_cpu(mfp[i]));
  	}
  	return 0;
 +
 +doorbell_diag_reset:
 +	ret_val = _base_diag_reset(ioc);
 +	return ret_val;
  }
  

""""""
