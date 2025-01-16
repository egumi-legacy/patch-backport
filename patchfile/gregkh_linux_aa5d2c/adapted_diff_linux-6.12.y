modified file: arch/x86/events/intel/core.c
--- patchfile/gregkh_linux_aa5d2c/linux-6.12.y/arch/x86/events/intel/core.c
+++ patchfile/gregkh_linux_aa5d2c/adapted_linux-6.12.y/arch/x86/events/intel/core.c
@@ -429,6 +429,16 @@
  	EVENT_CONSTRAINT_END
  };
  
 +static struct extra_reg intel_lnc_extra_regs[] __read_mostly = {
 +	INTEL_UEVENT_EXTRA_REG(0x012a, MSR_OFFCORE_RSP_0, 0xfffffffffffull, RSP_0),
 +	INTEL_UEVENT_EXTRA_REG(0x012b, MSR_OFFCORE_RSP_1, 0xfffffffffffull, RSP_1),
 +	INTEL_UEVENT_PEBS_LDLAT_EXTRA_REG(0x01cd),
 +	INTEL_UEVENT_EXTRA_REG(0x02c6, MSR_PEBS_FRONTEND, 0x9, FE),
 +	INTEL_UEVENT_EXTRA_REG(0x03c6, MSR_PEBS_FRONTEND, 0x7fff1f, FE),
 +	INTEL_UEVENT_EXTRA_REG(0x40ad, MSR_PEBS_FRONTEND, 0xf, FE),
 +	INTEL_UEVENT_EXTRA_REG(0x04c2, MSR_PEBS_FRONTEND, 0x8, FE),
 +	EVENT_EXTRA_END
 +};
  
  EVENT_ATTR_STR(mem-loads,	mem_ld_nhm,	"event=0x0b,umask=0x10,ldlat=3");
  EVENT_ATTR_STR(mem-loads,	mem_ld_snb,	"event=0xcd,umask=0x1,ldlat=3");
@@ -6344,7 +6354,7 @@
  	intel_pmu_init_glc(pmu);
  	hybrid(pmu, event_constraints) = intel_lnc_event_constraints;
  	hybrid(pmu, pebs_constraints) = intel_lnc_pebs_event_constraints;
 -	hybrid(pmu, extra_regs) = intel_rwc_extra_regs;
 +	hybrid(pmu, extra_regs) = intel_lnc_extra_regs;
  }
  
  static __always_inline void intel_pmu_init_skt(struct pmu *pmu)

""""""
