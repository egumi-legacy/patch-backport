modified file: tools/testing/selftests/arm64/abi/syscall-abi-asm.S
--- patchfile/torvalds_linux_ce0357/linux-6.12.y/tools/testing/selftests/arm64/abi/syscall-abi-asm.S
+++ patchfile/torvalds_linux_ce0357/adapted_linux-6.12.y/tools/testing/selftests/arm64/abi/syscall-abi-asm.S
@@ -124,9 +124,9 @@
  	str	x30, [x2], #8		// LR
  
  	// Load FPRs if we're not doing neither SVE nor streaming SVE
 -	cbnz	x0, check_sve_in
 +cbnz	x0, check_sve_in
  	ldr	x2, =svcr_in
 -	tbnz	x2, #SVCR_SM_SHIFT, check_sve_in
 +tbnz	x2, #SVCR_SM_SHIFT, check_sve_in
  
  	ldr	x2, =fpr_in
  	ldp	q0, q1, [x2]

""""""
