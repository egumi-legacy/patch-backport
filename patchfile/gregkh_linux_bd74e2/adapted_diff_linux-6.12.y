modified file: kernel/bpf/verifier.c
--- patchfile/gregkh_linux_bd74e2/linux-6.12.y/kernel/bpf/verifier.c
+++ patchfile/gregkh_linux_bd74e2/adapted_linux-6.12.y/kernel/bpf/verifier.c
@@ -7868,7 +7868,7 @@
  	if (reg->type != PTR_TO_STACK && reg->type != CONST_PTR_TO_DYNPTR) {
  		verbose(env,
  			"arg#%d expected pointer to stack or const struct bpf_dynptr\n",
 -			regno);
 +			regno - 1);
  		return -EINVAL;
  	}
  
@@ -7922,7 +7922,7 @@
  		if (!is_dynptr_reg_valid_init(env, reg)) {
  			verbose(env,
  				"Expected an initialized dynptr as arg #%d\n",
 -				regno);
 +				regno - 1);
  			return -EINVAL;
  		}
  
@@ -7930,7 +7930,7 @@
  		if (!is_dynptr_type_expected(env, reg, arg_type & ~MEM_RDONLY)) {
  			verbose(env,
  				"Expected a dynptr of type %s as arg #%d\n",
 -				dynptr_type_str(arg_to_dynptr_type(arg_type)), regno);
 +				dynptr_type_str(arg_to_dynptr_type(arg_type)), regno - 1);
  			return -EINVAL;
  		}
  
@@ -7999,7 +7999,7 @@
  	 */
  	btf_id = btf_check_iter_arg(meta->btf, meta->func_proto, regno - 1);
  	if (btf_id < 0) {
 -		verbose(env, "expected valid iter pointer as arg #%d\n", regno);
 +		verbose(env, "expected valid iter pointer as arg #%d\n", regno - 1);
  		return -EINVAL;
  	}
  	t = btf_type_by_id(meta->btf, btf_id);
@@ -8009,7 +8009,7 @@
  		if (!is_iter_reg_valid_uninit(env, reg, nr_slots)) {
  			verbose(env, "expected uninitialized iter_%s as arg #%d\n",
 -				iter_type_str(meta->btf, btf_id), regno);
 +				iter_type_str(meta->btf, btf_id), regno - 1);
  			return -EINVAL;
  		}
  
@@ -8033,7 +8033,7 @@
  			break;
  		case -EINVAL:
  			verbose(env, "expected an initialized iter_%s as arg #%d\n",
 -				iter_type_str(meta->btf, btf_id), regno);
 +				iter_type_str(meta->btf, btf_id), regno - 1);
  			return err;
  		case -EPROTO:
  			verbose(env, "expected an RCU CS when using %s\n", meta->func_name);

""""""
modified file: tools/testing/selftests/bpf/progs/dynptr_fail.c
--- patchfile/gregkh_linux_bd74e2/linux-6.12.y/tools/testing/selftests/bpf/progs/dynptr_fail.c
+++ patchfile/gregkh_linux_bd74e2/adapted_linux-6.12.y/tools/testing/selftests/bpf/progs/dynptr_fail.c
@@ -149,7 +149,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #3")
 +__failure __msg("Expected an initialized dynptr as arg #2")
  int use_after_invalid(void *ctx)
  {
  	struct bpf_dynptr ptr;
@@ -428,7 +428,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #1")
 +__failure __msg("Expected an initialized dynptr as arg #0")
  int invalid_write1(void *ctx)
  {
  	struct bpf_dynptr ptr;
@@ -1407,7 +1407,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #1")
 +__failure __msg("Expected an initialized dynptr as arg #0")
  int dynptr_adjust_invalid(void *ctx)
  {
  	struct bpf_dynptr ptr = {};
@@ -1420,7 +1420,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #1")
 +__failure __msg("Expected an initialized dynptr as arg #0")
  int dynptr_is_null_invalid(void *ctx)
  {
  	struct bpf_dynptr ptr = {};
@@ -1433,7 +1433,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #1")
 +__failure __msg("Expected an initialized dynptr as arg #0")
  int dynptr_is_rdonly_invalid(void *ctx)
  {
  	struct bpf_dynptr ptr = {};
@@ -1446,7 +1446,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #1")
 +__failure __msg("Expected an initialized dynptr as arg #0")
  int dynptr_size_invalid(void *ctx)
  {
  	struct bpf_dynptr ptr = {};
@@ -1459,7 +1459,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #1")
 +__failure __msg("Expected an initialized dynptr as arg #0")
  int clone_invalid1(void *ctx)
  {
  	struct bpf_dynptr ptr1 = {};
@@ -1493,7 +1493,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #3")
 +__failure __msg("Expected an initialized dynptr as arg #2")
  int clone_invalidate1(void *ctx)
  {
  	struct bpf_dynptr clone;
@@ -1514,7 +1514,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #3")
 +__failure __msg("Expected an initialized dynptr as arg #2")
  int clone_invalidate2(void *ctx)
  {
  	struct bpf_dynptr ptr;
@@ -1535,7 +1535,7 @@
  
  SEC("?raw_tp")
 -__failure __msg("Expected an initialized dynptr as arg #3")
 +__failure __msg("Expected an initialized dynptr as arg #2")
  int clone_invalidate3(void *ctx)
  {
  	struct bpf_dynptr ptr;
@@ -1723,7 +1723,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("arg#1 expected pointer to stack or const struct bpf_dynptr")
 +__failure __msg("arg#0 expected pointer to stack or const struct bpf_dynptr")
  int test_dynptr_reg_type(void *ctx)
  {
  	struct task_struct *current = NULL;

""""""
modified file: tools/testing/selftests/bpf/progs/iters_state_safety.c
--- patchfile/gregkh_linux_bd74e2/linux-6.12.y/tools/testing/selftests/bpf/progs/iters_state_safety.c
+++ patchfile/gregkh_linux_bd74e2/adapted_linux-6.12.y/tools/testing/selftests/bpf/progs/iters_state_safety.c
@@ -73,7 +73,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("expected an initialized iter_num as arg #1")
 +__failure __msg("expected an initialized iter_num as arg #0")
  int destroy_without_creating_fail(void *ctx)
  {
@@ -91,7 +91,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("expected an initialized iter_num as arg #1")
 +__failure __msg("expected an initialized iter_num as arg #0")
  int compromise_iter_w_direct_write_fail(void *ctx)
  {
  	struct bpf_iter_num iter;
@@ -143,7 +143,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("expected an initialized iter_num as arg #1")
 +__failure __msg("expected an initialized iter_num as arg #0")
  int compromise_iter_w_helper_write_fail(void *ctx)
  {
  	struct bpf_iter_num iter;
@@ -230,7 +230,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("expected uninitialized iter_num as arg #1")
 +__failure __msg("expected uninitialized iter_num as arg #0")
  int double_create_fail(void *ctx)
  {
  	struct bpf_iter_num iter;
@@ -258,7 +258,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("expected an initialized iter_num as arg #1")
 +__failure __msg("expected an initialized iter_num as arg #0")
  int double_destroy_fail(void *ctx)
  {
  	struct bpf_iter_num iter;
@@ -284,7 +284,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("expected an initialized iter_num as arg #1")
 +__failure __msg("expected an initialized iter_num as arg #0")
  int next_without_new_fail(void *ctx)
  {
  	struct bpf_iter_num iter;
@@ -305,7 +305,7 @@
  }
  
  SEC("?raw_tp")
 -__failure __msg("expected an initialized iter_num as arg #1")
 +__failure __msg("expected an initialized iter_num as arg #0")
  int next_after_destroy_fail(void *ctx)
  {
  	struct bpf_iter_num iter;

""""""
modified file: tools/testing/selftests/bpf/progs/iters_testmod_seq.c
--- patchfile/gregkh_linux_bd74e2/linux-6.12.y/tools/testing/selftests/bpf/progs/iters_testmod_seq.c
+++ patchfile/gregkh_linux_bd74e2/adapted_linux-6.12.y/tools/testing/selftests/bpf/progs/iters_testmod_seq.c
@@ -79,7 +79,7 @@
  
  SEC("?raw_tp")
  __failure
 -__msg("expected an initialized iter_testmod_seq as arg #2")
 +__msg("expected an initialized iter_testmod_seq as arg #1")
  int testmod_seq_getter_before_bad(const void *ctx)
  {
  	struct bpf_iter_testmod_seq it;
@@ -89,7 +89,7 @@
  
  SEC("?raw_tp")
  __failure
 -__msg("expected an initialized iter_testmod_seq as arg #2")
 +__msg("expected an initialized iter_testmod_seq as arg #1")
  int testmod_seq_getter_after_bad(const void *ctx)
  {
  	struct bpf_iter_testmod_seq it;

""""""
modified file: tools/testing/selftests/bpf/progs/test_kfunc_dynptr_param.c
--- patchfile/gregkh_linux_bd74e2/linux-6.12.y/tools/testing/selftests/bpf/progs/test_kfunc_dynptr_param.c
+++ patchfile/gregkh_linux_bd74e2/adapted_linux-6.12.y/tools/testing/selftests/bpf/progs/test_kfunc_dynptr_param.c
@@ -45,7 +45,7 @@
  }
  
  SEC("?lsm.s/bpf")
 -__failure __msg("arg#1 expected pointer to stack or const struct bpf_dynptr")
 +__failure __msg("arg#0 expected pointer to stack or const struct bpf_dynptr")
  int BPF_PROG(not_ptr_to_stack, int cmd, union bpf_attr *attr, unsigned int size)
  {
  	unsigned long val = 0;

""""""
modified file: tools/testing/selftests/bpf/progs/verifier_bits_iter.c
--- patchfile/gregkh_linux_bd74e2/linux-6.12.y/tools/testing/selftests/bpf/progs/verifier_bits_iter.c
+++ patchfile/gregkh_linux_bd74e2/adapted_linux-6.12.y/tools/testing/selftests/bpf/progs/verifier_bits_iter.c
@@ -32,7 +32,7 @@
  
  SEC("iter/cgroup")
  __description("uninitialized iter in ->next()")
 -__failure __msg("expected an initialized iter_bits as arg #1")
 +__failure __msg("expected an initialized iter_bits as arg #0")
  int BPF_PROG(next_uninit, struct bpf_iter_meta *meta, struct cgroup *cgrp)
  {
  	struct bpf_iter_bits it = {};
@@ -43,7 +43,7 @@
  
  SEC("iter/cgroup")
  __description("uninitialized iter in ->destroy()")
 -__failure __msg("expected an initialized iter_bits as arg #1")
 +__failure __msg("expected an initialized iter_bits as arg #0")
  int BPF_PROG(destroy_uninit, struct bpf_iter_meta *meta, struct cgroup *cgrp)
  {
  	struct bpf_iter_bits it = {};

""""""
