modified file: arch/x86/include/asm/static_call.h
--- patchfile/torvalds_linux_0ef804/linux-6.12.y/arch/x86/include/asm/static_call.h
+++ patchfile/torvalds_linux_0ef804/adapted_linux-6.12.y/arch/x86/include/asm/static_call.h
@@ -80,4 +80,19 @@
  	}								\
  })
  
 +extern void __static_call_update_early(void *tramp, void *func);
 +
 +#define static_call_update_early(name, _func)				\
 +({									\
 +	typeof(&STATIC_CALL_TRAMP(name)) __F = (_func);			\
 +	if (static_call_initialized) {					\
 +		__static_call_update(&STATIC_CALL_KEY(name),		\
 +				     STATIC_CALL_TRAMP_ADDR(name), __F);\
 +	} else {							\
 +		WRITE_ONCE(STATIC_CALL_KEY(name).func, _func);		\
 +		__static_call_update_early(STATIC_CALL_TRAMP_ADDR(name),\
 +					   __F);			\
 +	}								\
 +})
 +
  #endif /* _ASM_STATIC_CALL_H */

""""""

""""""
modified file: arch/x86/kernel/static_call.c
--- patchfile/torvalds_linux_0ef804/linux-6.12.y/arch/x86/kernel/static_call.c
+++ patchfile/torvalds_linux_0ef804/adapted_linux-6.12.y/arch/x86/kernel/static_call.c
@@ -171,6 +171,15 @@
  	mutex_unlock(&text_mutex);
  }
  EXPORT_SYMBOL_GPL(arch_static_call_transform);
 +
 +noinstr void __static_call_update_early(void *tramp, void *func)
 +{
 +	BUG_ON(system_state != SYSTEM_BOOTING);
 +	BUG_ON(!early_boot_irqs_disabled);
 +	BUG_ON(static_call_initialized);
 +	__text_gen_insn(tramp, JMP32_INSN_OPCODE, tramp, func, JMP32_INSN_SIZE);
 +	sync_core();
 +}
  
  noinstr void __static_call_update_early(void *tramp, void *func)
  {

""""""

""""""
modified file: include/linux/static_call.h
--- patchfile/torvalds_linux_0ef804/linux-6.12.y/include/linux/static_call.h
+++ patchfile/torvalds_linux_0ef804/adapted_linux-6.12.y/include/linux/static_call.h
@@ -159,6 +159,8 @@
  #define static_call_query(name) (READ_ONCE(STATIC_CALL_KEY(name).func))
  
  #ifdef CONFIG_HAVE_STATIC_CALL_INLINE
 +
 +extern int static_call_initialized;
  
  extern int static_call_initialized;
  
@@ -229,6 +231,8 @@
  
  #define static_call_initialized 0
  
 +#define static_call_initialized 0
 +
  static inline int static_call_init(void) { return 0; }
  
  #define DEFINE_STATIC_CALL(name, _func)					\
@@ -284,6 +288,8 @@
  	EXPORT_SYMBOL_GPL(STATIC_CALL_TRAMP(name))
  
  #else /* Generic implementation */
 +
 +#define static_call_initialized 0
  
  #define static_call_initialized 0
  

""""""

""""""
