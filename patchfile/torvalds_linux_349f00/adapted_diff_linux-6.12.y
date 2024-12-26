modified file: include/linux/static_call.h
--- patchfile/torvalds_linux_349f00/linux-6.12.y/include/linux/static_call.h
+++ patchfile/torvalds_linux_349f00/adapted_linux-6.12.y/include/linux/static_call.h
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
