modified file: arch/x86/events/intel/uncore.c
--- patchfile/gregkh_linux_b6ccdd/linux-6.12.y/arch/x86/events/intel/uncore.c
+++ patchfile/gregkh_linux_b6ccdd/adapted_linux-6.12.y/arch/x86/events/intel/uncore.c
@@ -1910,6 +1910,7 @@
  	X86_MATCH_VFM(INTEL_ATOM_GRACEMONT,	&adl_uncore_init),
  	X86_MATCH_VFM(INTEL_ATOM_CRESTMONT_X,	&gnr_uncore_init),
  	X86_MATCH_VFM(INTEL_ATOM_CRESTMONT,	&gnr_uncore_init),
 +	X86_MATCH_VFM(INTEL_ATOM_DARKMONT_X,	&gnr_uncore_init),
  	{},
  };
  MODULE_DEVICE_TABLE(x86cpu, intel_uncore_match);

""""""
