modified file: tools/objtool/noreturns.h
--- patchfile/gregkh_linux_31ad36/linux-6.12.y/tools/objtool/noreturns.h
+++ patchfile/gregkh_linux_31ad36/adapted_linux-6.12.y/tools/objtool/noreturns.h
@@ -20,6 +20,7 @@
  NORETURN(arch_cpu_idle_dead)
  NORETURN(bch2_trans_in_restart_error)
  NORETURN(bch2_trans_restart_error)
 +NORETURN(bch2_trans_unlocked_error)
  NORETURN(cpu_bringup_and_idle)
  NORETURN(cpu_startup_entry)
  NORETURN(do_exit)

""""""
