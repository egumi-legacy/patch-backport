modified file: drivers/virt/coco/tdx-guest/tdx-guest.c
--- patchfile/gregkh_linux_278349/linux-6.12.y/drivers/virt/coco/tdx-guest/tdx-guest.c
+++ patchfile/gregkh_linux_278349/adapted_linux-6.12.y/drivers/virt/coco/tdx-guest/tdx-guest.c
@@ -124,10 +124,8 @@
  	if (!addr)
  		return NULL;
  
 -	if (set_memory_decrypted((unsigned long)addr, count)) {
 -		free_pages_exact(addr, len);
 +	if (set_memory_decrypted((unsigned long)addr, count))
  		return NULL;
 -	}
  
  	return addr;
  }

""""""
