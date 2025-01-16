modified file: drivers/bluetooth/btusb.c
--- patchfile/gregkh_linux_defc33/linux-6.12.y/drivers/bluetooth/btusb.c
+++ patchfile/gregkh_linux_defc33/adapted_linux-6.12.y/drivers/bluetooth/btusb.c
@@ -2647,7 +2647,7 @@
  {
  	struct btmtk_data *btmtk_data = hci_get_priv(data->hdev);
  
 -	if (btmtk_data->isopkt_intf) {
 +	if (test_bit(BTMTK_ISOPKT_OVER_INTR, &btmtk_data->flags)) {
  		usb_kill_anchored_urbs(&btmtk_data->isopkt_anchor);
  		clear_bit(BTMTK_ISOPKT_RUNNING, &btmtk_data->flags);
  
@@ -2677,8 +2677,8 @@
  	if (err < 0)
  		return err;
  
 -	if (test_bit(BTMTK_ISOPKT_RUNNING, &btmtk_data->flags))
 -		btusb_mtk_release_iso_intf(data);
 +	/* Release MediaTek ISO data interface */
 +	btusb_mtk_release_iso_intf(hdev);
  
  	btusb_stop_traffic(data);
  	usb_kill_anchored_urbs(&data->tx_anchor);

""""""
