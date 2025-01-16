modified file: sound/core/ump.c
--- patchfile/gregkh_linux_e29e50/linux-6.12.y/sound/core/ump.c
+++ patchfile/gregkh_linux_e29e50/adapted_linux-6.12.y/sound/core/ump.c
@@ -1254,8 +1254,9 @@
  		name = ump->groups[idx].name;
  		if (!*name)
  			name = ump->info.name;
 -		snprintf(s->name, sizeof(s->name), "Group %d (%.16s)",
 -			 idx + 1, name);
 +		snprintf(s->name, sizeof(s->name), "Group %d (%.16s)%s",
 +			 idx + 1, name,
 +			 ump->groups[idx].active ? "" : " [Inactive]");
  	}
  }
  

""""""
