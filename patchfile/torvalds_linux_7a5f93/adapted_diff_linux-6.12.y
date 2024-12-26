modified file: rust/Makefile
--- patchfile/torvalds_linux_7a5f93/linux-6.12.y/rust/Makefile
+++ patchfile/torvalds_linux_7a5f93/adapted_linux-6.12.y/rust/Makefile
@@ -52,6 +52,11 @@
  
  core-cfgs = \
      --cfg no_fp_fmt_parse
 +
 +alloc-cfgs = \
 +    --cfg no_global_oom_handling \
 +    --cfg no_rc \
 +    --cfg no_sync
  
  alloc-cfgs = \
      --cfg no_global_oom_handling \
@@ -327,6 +332,9 @@
  $(obj)/exports_alloc_generated.h: $(obj)/alloc.o FORCE
  	$(call if_changed,exports)
  
 +$(obj)/exports_alloc_generated.h: $(obj)/alloc.o FORCE
 +	$(call if_changed,exports)
 +
  # Even though Rust kernel modules should never use the bindings directly,
  # symbols from the `bindings` crate and the C helpers need to be exported
  # because Rust generics and inlined functions may not get their code generated

""""""
