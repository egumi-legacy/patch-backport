modified file: drivers/scsi/qla1280.h
--- patchfile/gregkh_linux_c064de/linux-6.12.y/drivers/scsi/qla1280.h
+++ patchfile/gregkh_linux_c064de/adapted_linux-6.12.y/drivers/scsi/qla1280.h
@@ -116,12 +116,12 @@
  	uint16_t id_h;		/* ID high */
  	uint16_t cfg_0;		/* Configuration 0 */
  #define ISP_CFG0_HWMSK   0x000f	/* Hardware revision mask */
 -#define ISP_CFG0_1020    BIT_0	/* ISP1020 */
 -#define ISP_CFG0_1020A	 BIT_1	/* ISP1020A */
 -#define ISP_CFG0_1040	 BIT_2	/* ISP1040 */
 -#define ISP_CFG0_1040A	 BIT_3	/* ISP1040A */
 -#define ISP_CFG0_1040B	 BIT_4	/* ISP1040B */
 -#define ISP_CFG0_1040C	 BIT_5	/* ISP1040C */
 +#define ISP_CFG0_1020	 1	/* ISP1020 */
 +#define ISP_CFG0_1020A	 2	/* ISP1020A */
 +#define ISP_CFG0_1040	 3	/* ISP1040 */
 +#define ISP_CFG0_1040A	 4	/* ISP1040A */
 +#define ISP_CFG0_1040B	 5	/* ISP1040B */
 +#define ISP_CFG0_1040C	 6	/* ISP1040C */
  	uint16_t cfg_1;		/* Configuration 1 */
  #define ISP_CFG1_F128    BIT_6  /* 128-byte FIFO threshold */
  #define ISP_CFG1_F64     BIT_4|BIT_5 /* 128-byte FIFO threshold */

""""""
