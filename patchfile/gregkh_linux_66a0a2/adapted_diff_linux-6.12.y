modified file: sound/sh/sh_dac_audio.c
--- patchfile/gregkh_linux_66a0a2/linux-6.12.y/sound/sh/sh_dac_audio.c
+++ patchfile/gregkh_linux_66a0a2/adapted_linux-6.12.y/sound/sh/sh_dac_audio.c
@@ -163,7 +163,7 @@
  	struct snd_sh_dac *chip = snd_pcm_substream_chip(substream);
  
 -	if (copy_from_iter_toio(chip->data_buffer + pos, src, count))
 +	if (copy_from_iter_toio(chip->data_buffer + pos, count, src) != count)
  		return -EFAULT;
  	chip->buffer_end = chip->data_buffer + pos + count;
  

""""""
