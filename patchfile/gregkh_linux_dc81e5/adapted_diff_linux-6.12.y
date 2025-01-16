modified file: arch/x86/kernel/cet.c
--- patchfile/gregkh_linux_dc81e5/linux-6.12.y/arch/x86/kernel/cet.c
+++ patchfile/gregkh_linux_dc81e5/adapted_linux-6.12.y/arch/x86/kernel/cet.c
@@ -81,6 +81,34 @@
  
  static __ro_after_init bool ibt_fatal = true;
  
 +/*
 + * By definition, all missing-ENDBRANCH #CPs are a result of WFE && !ENDBR.
 + *
 + * For the kernel IBT no ENDBR selftest where #CPs are deliberately triggered,
 + * the WFE state of the interrupted context needs to be cleared to let execution
 + * continue.  Otherwise when the CPU resumes from the instruction that just
 + * caused the previous #CP, another missing-ENDBRANCH #CP is raised and the CPU
 + * enters a dead loop.
 + *
 + * This is not a problem with IDT because it doesn't preserve WFE and IRET doesn't
 + * set WFE.  But FRED provides space on the entry stack (in an expanded CS area)
 + * to save and restore the WFE state, thus the WFE state is no longer clobbered,
 + * so software must clear it.
 + */
 +static void ibt_clear_fred_wfe(struct pt_regs *regs)
 +{
 +	/*
 +	 * No need to do any FRED checks.
 +	 *
 +	 * For IDT event delivery, the high-order 48 bits of CS are pushed
 +	 * as 0s into the stack, and later IRET ignores these bits.
 +	 *
 +	 * For FRED, a test to check if fred_cs.wfe is set would be dropped
 +	 * by compilers.
 +	 */
 +	regs->fred_cs.wfe = 0;
 +}
 +
  static void do_kernel_cp_fault(struct pt_regs *regs, unsigned long error_code)
  {
  	if ((error_code & CP_EC) != CP_ENDBR) {
@@ -90,6 +118,7 @@
  
  	if (unlikely(regs->ip == (unsigned long)&ibt_selftest_noendbr)) {
  		regs->ax = 0;
 +		ibt_clear_fred_wfe(regs);
  		return;
  	}
  
@@ -97,6 +126,7 @@
  	if (!ibt_fatal) {
  		printk(KERN_DEFAULT CUT_HERE);
  		__warn(__FILE__, __LINE__, (void *)regs->ip, TAINT_WARN, regs, NULL);
 +		ibt_clear_fred_wfe(regs);
  		return;
  	}
  	BUG();

""""""
