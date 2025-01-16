modified file: Documentation/arch/arm64/silicon-errata.rst
--- patchfile/gregkh_linux_c2b46a/linux-6.12.y/Documentation/arch/arm64/silicon-errata.rst
+++ patchfile/gregkh_linux_c2b46a/adapted_linux-6.12.y/Documentation/arch/arm64/silicon-errata.rst
@@ -255,8 +255,9 @@
  +----------------+-----------------+-----------------+-----------------------------+
  | Hisilicon      | Hip08 SMMU PMCG | #162001800      | N/A                         |
  +----------------+-----------------+-----------------+-----------------------------+
 -| Hisilicon      | Hip{08,09,10,10C| #162001900      | N/A                         |
 -|                | ,11} SMMU PMCG  |                 |                             |
 +| Hisilicon      | Hip{08,09,09A,10| #162001900      | N/A                         |
 +|                | ,10C,11}        |                 |                             |
 +|                | SMMU PMCG       |                 |                             |
  +----------------+-----------------+-----------------+-----------------------------+
  | Hisilicon      | Hip09           | #162100801      | HISILICON_ERRATUM_162100801 |
  +----------------+-----------------+-----------------+-----------------------------+

""""""
modified file: drivers/acpi/arm64/iort.c
--- patchfile/gregkh_linux_c2b46a/linux-6.12.y/drivers/acpi/arm64/iort.c
+++ patchfile/gregkh_linux_c2b46a/adapted_linux-6.12.y/drivers/acpi/arm64/iort.c
@@ -1703,6 +1703,8 @@
  	{"HISI  ", "HIP09   ", 0, ACPI_SIG_IORT, greater_than_or_equal,
  	 "Erratum #162001900", IORT_SMMU_V3_PMCG_HISI_HIP09},
 +	{"HISI  ", "HIP09A  ", 0, ACPI_SIG_IORT, greater_than_or_equal,
 +	 "Erratum #162001900", IORT_SMMU_V3_PMCG_HISI_HIP09},
  	{"HISI  ", "HIP10   ", 0, ACPI_SIG_IORT, greater_than_or_equal,
  	 "Erratum #162001900", IORT_SMMU_V3_PMCG_HISI_HIP09},

""""""
