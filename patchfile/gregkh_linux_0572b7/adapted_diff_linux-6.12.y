
""""""
modified file: drivers/net/wireless/intel/iwlwifi/iwl-trans.h
--- patchfile/gregkh_linux_0572b7/linux-6.12.y/drivers/net/wireless/intel/iwlwifi/iwl-trans.h
+++ patchfile/gregkh_linux_0572b7/adapted_linux-6.12.y/drivers/net/wireless/intel/iwlwifi/iwl-trans.h
@@ -1074,12 +1074,13 @@
  void iwl_trans_debugfs_cleanup(struct iwl_trans *trans);
  #endif
  
 -#define iwl_trans_read_mem_bytes(trans, addr, buf, bufsize)		      \
 -	do {								      \
 -		if (__builtin_constant_p(bufsize))			      \
 -			BUILD_BUG_ON((bufsize) % sizeof(u32));		      \
 -		iwl_trans_read_mem(trans, addr, buf, (bufsize) / sizeof(u32));\
 -	} while (0)
 +#define iwl_trans_read_mem_bytes(trans, addr, buf, bufsize)	\
 +	({							\
 +		if (__builtin_constant_p(bufsize))		\
 +			BUILD_BUG_ON((bufsize) % sizeof(u32));	\
 +		iwl_trans_read_mem(trans, addr, buf,		\
 +				   (bufsize) / sizeof(u32));	\
 +	})
  
  int iwl_trans_write_imr_mem(struct iwl_trans *trans, u32 dst_addr,
  			    u64 src_addr, u32 byte_cnt);

""""""
modified file: drivers/net/wireless/intel/iwlwifi/mvm/d3.c
--- patchfile/gregkh_linux_0572b7/linux-6.12.y/drivers/net/wireless/intel/iwlwifi/mvm/d3.c
+++ patchfile/gregkh_linux_0572b7/adapted_linux-6.12.y/drivers/net/wireless/intel/iwlwifi/mvm/d3.c
@@ -3635,21 +3635,30 @@
  	iwl_fw_dbg_read_d3_debug_data(&mvm->fwrt);
  
  	if (iwl_mvm_check_rt_status(mvm, NULL)) {
 +		IWL_ERR(mvm,
 +			"iwl_mvm_check_rt_status failed, device is gone during suspend\n");
  		set_bit(STATUS_FW_ERROR, &mvm->trans->status);
  		iwl_mvm_dump_nic_error_log(mvm);
  		iwl_dbg_tlv_time_point(&mvm->fwrt,
  				       IWL_FW_INI_TIME_POINT_FW_ASSERT, NULL);
  		iwl_fw_dbg_collect_desc(&mvm->fwrt, &iwl_dump_desc_assert,
  					false, 0);
 -		return -ENODEV;
 +		mvm->trans->state = IWL_TRANS_NO_FW;
 +		ret = -ENODEV;
 +
 +		goto out;
  	}
  	ret = iwl_mvm_d3_notif_wait(mvm, &d3_data);
 +
 +	if (ret) {
 +		IWL_ERR(mvm, "Couldn't get the d3 notif %d\n", ret);
 +		mvm->trans->state = IWL_TRANS_NO_FW;
 +	}
 +
 +out:
  	clear_bit(IWL_MVM_STATUS_IN_D3, &mvm->status);
  	mvm->trans->system_pm_mode = IWL_PLAT_PM_MODE_DISABLED;
  	mvm->fast_resume = false;
 -
 -	if (ret)
 -		IWL_ERR(mvm, "Couldn't get the d3 notif %d\n", ret);
  
  	return ret;
  }

""""""
modified file: drivers/net/wireless/intel/iwlwifi/pcie/trans.c
--- patchfile/gregkh_linux_0572b7/linux-6.12.y/drivers/net/wireless/intel/iwlwifi/pcie/trans.c
+++ patchfile/gregkh_linux_0572b7/adapted_linux-6.12.y/drivers/net/wireless/intel/iwlwifi/pcie/trans.c
@@ -1643,6 +1643,8 @@
  out:
  	if (*status == IWL_D3_STATUS_ALIVE)
  		ret = iwl_pcie_d3_handshake(trans, false);
 +	else
 +		trans->state = IWL_TRANS_NO_FW;
  
  	return ret;
  }

""""""
