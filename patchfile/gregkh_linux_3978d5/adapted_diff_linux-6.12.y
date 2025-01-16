modified file: sound/core/ump.c
--- patchfile/gregkh_linux_3978d5/linux-6.12.y/sound/core/ump.c
+++ patchfile/gregkh_linux_3978d5/adapted_linux-6.12.y/sound/core/ump.c
@@ -1087,6 +1087,8 @@
  	guard(mutex)(&ump->open_mutex);
  	if (ump->legacy_substreams[dir][group])
  		return -EBUSY;
 +	if (!ump->groups[group].active)
 +		return -ENODEV;
  	if (dir == SNDRV_RAWMIDI_STREAM_OUTPUT) {
  		if (!ump->legacy_out_opens) {
  			err = snd_rawmidi_kernel_open(&ump->core, 0,

""""""
