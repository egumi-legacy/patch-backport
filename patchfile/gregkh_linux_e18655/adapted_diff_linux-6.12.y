modified file: fs/smb/server/smb_common.c
--- patchfile/gregkh_linux_e18655/linux-6.12.y/fs/smb/server/smb_common.c
+++ patchfile/gregkh_linux_e18655/adapted_linux-6.12.y/fs/smb/server/smb_common.c
@@ -18,8 +18,8 @@
  #include "mgmt/share_config.h"
  
 -static const char basechars[43] = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_-!@#$%";
 -#define MANGLE_BASE (sizeof(basechars) / sizeof(char) - 1)
 +static const char *basechars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_-!@#$%";
 +#define MANGLE_BASE (strlen(basechars) - 1)
  #define MAGIC_CHAR '~'
  #define PERIOD '.'
  #define mangle(V) ((char)(basechars[(V) % MANGLE_BASE]))

""""""
