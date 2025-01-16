modified file: arch/loongarch/include/asm/inst.h
--- patchfile/gregkh_linux_c1474b/linux-6.12.y/arch/loongarch/include/asm/inst.h
+++ patchfile/gregkh_linux_c1474b/adapted_linux-6.12.y/arch/loongarch/include/asm/inst.h
@@ -683,7 +683,17 @@
  DEF_EMIT_REG2I16_FORMAT(bge, bge_op)
  DEF_EMIT_REG2I16_FORMAT(bltu, bltu_op)
  DEF_EMIT_REG2I16_FORMAT(bgeu, bgeu_op)
 -DEF_EMIT_REG2I16_FORMAT(jirl, jirl_op)
 +
 +static inline void emit_jirl(union loongarch_instruction *insn,
 +			     enum loongarch_gpr rd,
 +			     enum loongarch_gpr rj,
 +			     int offset)
 +{
 +	insn->reg2i16_format.opcode = jirl_op;
 +	insn->reg2i16_format.immediate = offset;
 +	insn->reg2i16_format.rd = rd;
 +	insn->reg2i16_format.rj = rj;
 +}
  
  #define DEF_EMIT_REG2BSTRD_FORMAT(NAME, OP)				\
  static inline void emit_##NAME(union loongarch_instruction *insn,	\

""""""
modified file: arch/loongarch/kernel/inst.c
--- patchfile/gregkh_linux_c1474b/linux-6.12.y/arch/loongarch/kernel/inst.c
+++ patchfile/gregkh_linux_c1474b/adapted_linux-6.12.y/arch/loongarch/kernel/inst.c
@@ -332,7 +332,7 @@
  		return INSN_BREAK;
  	}
  
 -	emit_jirl(&insn, rj, rd, imm >> 2);
 -
 -	return insn.word;
 -}
 +	emit_jirl(&insn, rd, rj, imm >> 2);
 +
 +	return insn.word;
 +}

""""""
modified file: arch/loongarch/net/bpf_jit.c
--- patchfile/gregkh_linux_c1474b/linux-6.12.y/arch/loongarch/net/bpf_jit.c
+++ patchfile/gregkh_linux_c1474b/adapted_linux-6.12.y/arch/loongarch/net/bpf_jit.c
@@ -181,13 +181,13 @@
  		emit_insn(ctx, addiw, LOONGARCH_GPR_A0, regmap[BPF_REG_0], 0);
 -		emit_insn(ctx, jirl, LOONGARCH_GPR_RA, LOONGARCH_GPR_ZERO, 0);
 +		emit_insn(ctx, jirl, LOONGARCH_GPR_ZERO, LOONGARCH_GPR_RA, 0);
  	} else {
 -		emit_insn(ctx, jirl, LOONGARCH_GPR_T3, LOONGARCH_GPR_ZERO, 1);
 +		emit_insn(ctx, jirl, LOONGARCH_GPR_ZERO, LOONGARCH_GPR_T3, 1);
  	}
  }
  
@@ -904,7 +904,7 @@
  			return ret;
  
  		move_addr(ctx, t1, func_addr);
 -		emit_insn(ctx, jirl, t1, LOONGARCH_GPR_RA, 0);
 +		emit_insn(ctx, jirl, LOONGARCH_GPR_RA, t1, 0);
  		move_reg(ctx, regmap[BPF_REG_0], LOONGARCH_GPR_A0);
  		break;
  

""""""
