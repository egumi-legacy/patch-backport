modified file: drivers/bluetooth/btusb.c
--- patchfile/gregkh_linux_ad0c6f/linux-6.12.y/drivers/bluetooth/btusb.c
+++ patchfile/gregkh_linux_ad0c6f/adapted_linux-6.12.y/drivers/bluetooth/btusb.c
@@ -2734,11 +2734,14 @@
  {
  	struct btusb_data *data = hci_get_drvdata(hdev);
  	struct btmtk_data *btmtk_data = hci_get_priv(hdev);
 +	int ret;
 +
 +	ret = btmtk_usb_shutdown(hdev);
  
  	if (test_bit(BTMTK_ISOPKT_RUNNING, &btmtk_data->flags))
  		btusb_mtk_release_iso_intf(data);
  
 -	return btmtk_usb_shutdown(hdev);
 +	return ret;
  }
  
  #ifdef CONFIG_PM

""""""
