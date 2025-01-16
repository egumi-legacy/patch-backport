modified file: sound/sh/sh_dac_audio.c
--- patchfile/gregkh_linux_9b5f8e/linux-6.12.y/sound/sh/sh_dac_audio.c
+++ patchfile/gregkh_linux_9b5f8e/adapted_linux-6.12.y/sound/sh/sh_dac_audio.c
@@ -163,7 +163,7 @@
  	struct snd_sh_dac *chip = snd_pcm_substream_chip(substream);
  
 -	if (copy_from_iter_toio(chip->data_buffer + pos, src, count))
 +	if (copy_from_iter(chip->data_buffer + pos, src, count) != count)
  		return -EFAULT;
  	chip->buffer_end = chip->data_buffer + pos + count;
  
@@ -182,7 +182,7 @@
  	struct snd_sh_dac *chip = snd_pcm_substream_chip(substream);
  
 -	memset_io(chip->data_buffer + pos, 0, count);
 +	memset(chip->data_buffer + pos, 0, count);
  	chip->buffer_end = chip->data_buffer + pos + count;
  
  	if (chip->empty) {
@@ -211,7 +211,6 @@
  	.pointer	= snd_sh_dac_pcm_pointer,
  	.copy		= snd_sh_dac_pcm_copy,
  	.fill_silence	= snd_sh_dac_pcm_silence,
 -	.mmap		= snd_pcm_lib_mmap_iomem,
  };
  
  static int snd_sh_dac_pcm(struct snd_sh_dac *chip, int device)

""""""
