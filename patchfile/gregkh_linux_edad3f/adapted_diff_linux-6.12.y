modified file: sound/core/ump.c
--- patchfile/gregkh_linux_edad3f/linux-6.12.y/sound/core/ump.c
+++ patchfile/gregkh_linux_edad3f/adapted_linux-6.12.y/sound/core/ump.c
@@ -37,6 +37,7 @@
  				 u32 *buffer, int count);
  static void process_legacy_input(struct snd_ump_endpoint *ump, const u32 *src,
  				 int words);
 +static void update_legacy_names(struct snd_ump_endpoint *ump);
  #else
  static inline int process_legacy_output(struct snd_ump_endpoint *ump,
  					u32 *buffer, int count)
@@ -45,6 +46,9 @@
  }
  static inline void process_legacy_input(struct snd_ump_endpoint *ump,
  					const u32 *src, int words)
 +{
 +}
 +static inline void update_legacy_names(struct snd_ump_endpoint *ump)
  {
  }
  #endif
@@ -861,6 +865,7 @@
  		fill_fb_info(ump, &fb->info, buf);
  		if (ump->parsed) {
  			snd_ump_update_group_attrs(ump);
 +			update_legacy_names(ump);
  			seq_notify_fb_change(ump, fb);
  		}
  	}
@@ -893,6 +898,7 @@
  	if (ret > 0 && ump->parsed) {
  		snd_ump_update_group_attrs(ump);
 +		update_legacy_names(ump);
  		seq_notify_fb_change(ump, fb);
  	}
  	return ret;
@@ -1259,6 +1265,14 @@
  	}
  }
  
 +static void update_legacy_names(struct snd_ump_endpoint *ump)
 +{
 +	struct snd_rawmidi *rmidi = ump->legacy_rmidi;
 +
 +	fill_substream_names(ump, rmidi, SNDRV_RAWMIDI_STREAM_INPUT);
 +	fill_substream_names(ump, rmidi, SNDRV_RAWMIDI_STREAM_OUTPUT);
 +}
 +
  int snd_ump_attach_legacy_rawmidi(struct snd_ump_endpoint *ump,
  				  char *id, int device)
  {
@@ -1295,10 +1309,7 @@
  	rmidi->ops = &snd_ump_legacy_ops;
  	rmidi->private_data = ump;
  	ump->legacy_rmidi = rmidi;
 -	if (input)
 -		fill_substream_names(ump, rmidi, SNDRV_RAWMIDI_STREAM_INPUT);
 -	if (output)
 -		fill_substream_names(ump, rmidi, SNDRV_RAWMIDI_STREAM_OUTPUT);
 +	update_legacy_names(ump);
  
  	ump_dbg(ump, "Created a legacy rawmidi #%d (%s)\n", device, id);
  	return 0;

""""""
