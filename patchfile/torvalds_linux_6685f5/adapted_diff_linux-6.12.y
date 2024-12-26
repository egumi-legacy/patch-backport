modified file: arch/arm64/kvm/sys_regs.c
--- patchfile/torvalds_linux_6685f5/linux-6.12.y/arch/arm64/kvm/sys_regs.c
+++ patchfile/torvalds_linux_6685f5/adapted_linux-6.12.y/arch/arm64/kvm/sys_regs.c
@@ -1811,6 +1811,13 @@
  		val |= SYS_FIELD_PREP(ID_DFR0_EL1, PerfMon, perfmon);
  
  	val = ID_REG_LIMIT_FIELD_ENUM(val, ID_DFR0_EL1, CopDbg, Debugv8p8);
 +
 +	/*
 +	 * MPAM is disabled by default as KVM also needs a set of PARTID to
 +	 * program the MPAMVPMx_EL2 PARTID remapping registers with. But some
 +	 * older kernels let the guest see the ID bit.
 +	 */
 +	val &= ~ID_AA64PFR0_EL1_MPAM_MASK;
  
  	return val;
  }

""""""
