
""""""

""""""
modified file: arch/x86/kernel/vmlinux.lds.S
--- patchfile/torvalds_linux_7fa0da/linux-6.12.y/arch/x86/kernel/vmlinux.lds.S
+++ patchfile/torvalds_linux_7fa0da/adapted_linux-6.12.y/arch/x86/kernel/vmlinux.lds.S
@@ -216,6 +216,29 @@
  
  	. = ALIGN(__vvar_page + PAGE_SIZE, PAGE_SIZE);
  
 +	. = ALIGN(PAGE_SIZE);
 +	__vvar_page = .;
 +
 +	.vvar : AT(ADDR(.vvar) - LOAD_OFFSET) {
 +		/* work around gold bug 13023 */
 +		__vvar_beginning_hack = .;
 +
 +		/* Place all vvars at the offsets in asm/vvar.h. */
 +#define EMIT_VVAR(name, offset)				\
 +		. = __vvar_beginning_hack + offset;	\
 +		*(.vvar_ ## name)
 +#include <asm/vvar.h>
 +#undef EMIT_VVAR
 +
 +		/*
 +		 * Pad the rest of the page with zeros.  Otherwise the loader
 +		 * can leave garbage here.
 +		 */
 +		. = __vvar_beginning_hack + PAGE_SIZE;
 +	} :data
 +
 +	. = ALIGN(__vvar_page + PAGE_SIZE, PAGE_SIZE);
 +
  	. = ALIGN(PAGE_SIZE);
  	.init.begin : AT(ADDR(.init.begin) - LOAD_OFFSET) {

""""""

""""""

""""""

""""""

""""""
