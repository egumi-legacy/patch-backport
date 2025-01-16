modified file: drivers/i2c/busses/i2c-microchip-corei2c.c
--- patchfile/gregkh_linux_49e1f0/linux-6.12.y/drivers/i2c/busses/i2c-microchip-corei2c.c
+++ patchfile/gregkh_linux_49e1f0/adapted_linux-6.12.y/drivers/i2c/busses/i2c-microchip-corei2c.c
@@ -238,8 +238,6 @@
  		ctrl &= ~CTRL_STA;
  		writeb(idev->addr, idev->base + CORE_I2C_DATA);
  		writeb(ctrl, idev->base + CORE_I2C_CTRL);
 -		if (idev->msg_len == 0)
 -			finished = true;
  		break;
  	case STATUS_M_ARB_LOST:
  		idev->msg_err = -EAGAIN;

""""""
