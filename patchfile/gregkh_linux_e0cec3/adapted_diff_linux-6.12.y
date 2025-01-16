modified file: drivers/i2c/busses/i2c-imx.c
--- patchfile/gregkh_linux_e0cec3/linux-6.12.y/drivers/i2c/busses/i2c-imx.c
+++ patchfile/gregkh_linux_e0cec3/adapted_linux-6.12.y/drivers/i2c/busses/i2c-imx.c
@@ -282,6 +282,7 @@
  	{ .compatible = "fsl,imx6sll-i2c", .data = &imx6_i2c_hwdata, },
  	{ .compatible = "fsl,imx6sx-i2c", .data = &imx6_i2c_hwdata, },
  	{ .compatible = "fsl,imx6ul-i2c", .data = &imx6_i2c_hwdata, },
 +	{ .compatible = "fsl,imx7d-i2c", .data = &imx6_i2c_hwdata, },
  	{ .compatible = "fsl,imx7s-i2c", .data = &imx6_i2c_hwdata, },
  	{ .compatible = "fsl,imx8mm-i2c", .data = &imx6_i2c_hwdata, },
  	{ .compatible = "fsl,imx8mn-i2c", .data = &imx6_i2c_hwdata, },

""""""
