modified file: sound/pci/hda/patch_conexant.c
--- patchfile/gregkh_linux_947c40/linux-6.12.y/sound/pci/hda/patch_conexant.c
+++ patchfile/gregkh_linux_947c40/adapted_linux-6.12.y/sound/pci/hda/patch_conexant.c
@@ -307,6 +307,7 @@
  	CXT_FIXUP_HP_MIC_NO_PRESENCE,
  	CXT_PINCFG_SWS_JS201D,
  	CXT_PINCFG_TOP_SPEAKER,
 +	CXT_FIXUP_HP_A_U,
  };
  
@@ -774,6 +775,18 @@
  	}
  }
  
 +static void cxt_setup_gpio_unmute(struct hda_codec *codec,
 +				  unsigned int gpio_mute_mask)
 +{
 +	if (gpio_mute_mask) {
 +		// set gpio data to 0.
 +		snd_hda_codec_write(codec, 0x01, 0, AC_VERB_SET_GPIO_DATA, 0);
 +		snd_hda_codec_write(codec, 0x01, 0, AC_VERB_SET_GPIO_MASK, gpio_mute_mask);
 +		snd_hda_codec_write(codec, 0x01, 0, AC_VERB_SET_GPIO_DIRECTION, gpio_mute_mask);
 +		snd_hda_codec_write(codec, 0x01, 0, AC_VERB_SET_GPIO_STICKY_MASK, 0);
 +	}
 +}
 +
  static void cxt_fixup_mute_led_gpio(struct hda_codec *codec,
  				const struct hda_fixup *fix, int action)
  {
@@ -786,6 +799,15 @@
  {
  	if (action == HDA_FIXUP_ACT_PRE_PROBE)
  		cxt_setup_mute_led(codec, 0x10, 0x20);
 +}
 +
 +static void cxt_fixup_hp_a_u(struct hda_codec *codec,
 +			     const struct hda_fixup *fix, int action)
 +{
 +	// Init vers in BIOS mute the spk/hp by set gpio high to avoid pop noise,
 +	// so need to unmute once by clearing the gpio data when runs into the system.
 +	if (action == HDA_FIXUP_ACT_INIT)
 +		cxt_setup_gpio_unmute(codec, 0x2);
  }
  
@@ -997,6 +1019,10 @@
  			{ 0x1d, 0x82170111 },
  			{ }
  		},
 +	},
 +	[CXT_FIXUP_HP_A_U] = {
 +		.type = HDA_FIXUP_FUNC,
 +		.v.func = cxt_fixup_hp_a_u,
  	},
  };
  
@@ -1072,6 +1098,7 @@
  	SND_PCI_QUIRK(0x103c, 0x8457, "HP Z2 G4 mini", CXT_FIXUP_HP_MIC_NO_PRESENCE),
  	SND_PCI_QUIRK(0x103c, 0x8458, "HP Z2 G4 mini premium", CXT_FIXUP_HP_MIC_NO_PRESENCE),
  	SND_PCI_QUIRK(0x1043, 0x138d, "Asus", CXT_FIXUP_HEADPHONE_MIC_PIN),
 +	SND_PCI_QUIRK(0x14f1, 0x0252, "MBX-Z60MR100", CXT_FIXUP_HP_A_U),
  	SND_PCI_QUIRK(0x14f1, 0x0265, "SWS JS201D", CXT_PINCFG_SWS_JS201D),
  	SND_PCI_QUIRK(0x152d, 0x0833, "OLPC XO-1.5", CXT_FIXUP_OLPC_XO),
  	SND_PCI_QUIRK(0x17aa, 0x20f2, "Lenovo T400", CXT_PINCFG_LENOVO_TP410),
@@ -1117,6 +1144,7 @@
  	{ .id = CXT_PINCFG_LENOVO_NOTEBOOK, .name = "lenovo-20149" },
  	{ .id = CXT_PINCFG_SWS_JS201D, .name = "sws-js201d" },
  	{ .id = CXT_PINCFG_TOP_SPEAKER, .name = "sirius-top-speaker" },
 +	{ .id = CXT_FIXUP_HP_A_U, .name = "HP-U-support" },
  	{}
  };
  

""""""
