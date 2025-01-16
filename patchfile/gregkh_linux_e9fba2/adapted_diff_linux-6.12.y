modified file: drivers/platform/x86/asus-nb-wmi.c
--- patchfile/gregkh_linux_e9fba2/linux-6.12.y/drivers/platform/x86/asus-nb-wmi.c
+++ patchfile/gregkh_linux_e9fba2/adapted_linux-6.12.y/drivers/platform/x86/asus-nb-wmi.c
@@ -623,6 +623,7 @@
  	{ KE_KEY, 0xC4, { KEY_KBDILLUMUP } },
  	{ KE_KEY, 0xC5, { KEY_KBDILLUMDOWN } },
  	{ KE_IGNORE, 0xC6, },  /* Ambient Light Sensor notification */
 +	{ KE_IGNORE, 0xCF, },	/* AC mode */
  	{ KE_KEY, 0xFA, { KEY_PROG2 } },           /* Lid flip action */
  	{ KE_KEY, 0xBD, { KEY_PROG2 } },           /* Lid flip action on ROG xflow laptops */
  	{ KE_END, 0},

""""""
