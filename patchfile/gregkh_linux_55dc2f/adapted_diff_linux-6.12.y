modified file: arch/loongarch/kernel/efi.c
--- patchfile/gregkh_linux_55dc2f/linux-6.12.y/arch/loongarch/kernel/efi.c
+++ patchfile/gregkh_linux_55dc2f/adapted_linux-6.12.y/arch/loongarch/kernel/efi.c
@@ -95,7 +95,7 @@
  	memset(si, 0, sizeof(*si));
  	early_memunmap(si, sizeof(*si));
  
 -	memblock_reserve(screen_info.lfb_base, screen_info.lfb_size);
 +	memblock_reserve(__screen_info_lfb_base(&screen_info), screen_info.lfb_size);
  }
  
  void __init efi_init(void)

""""""
