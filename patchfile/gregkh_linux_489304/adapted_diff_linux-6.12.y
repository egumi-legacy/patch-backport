modified file: drivers/bluetooth/btusb.c
--- patchfile/gregkh_linux_489304/linux-6.12.y/drivers/bluetooth/btusb.c
+++ patchfile/gregkh_linux_489304/adapted_linux-6.12.y/drivers/bluetooth/btusb.c
@@ -2643,9 +2643,9 @@
  	init_usb_anchor(&btmtk_data->isopkt_anchor);
  }
  
 -static void btusb_mtk_release_iso_intf(struct btusb_data *data)
 -{
 -	struct btmtk_data *btmtk_data = hci_get_priv(data->hdev);
 +static void btusb_mtk_release_iso_intf(struct hci_dev *hdev)
 +{
 +	struct btmtk_data *btmtk_data = hci_get_priv(hdev);
  
  	if (btmtk_data->isopkt_intf) {
  		usb_kill_anchored_urbs(&btmtk_data->isopkt_anchor);
@@ -2661,6 +2661,16 @@
  	clear_bit(BTMTK_ISOPKT_OVER_INTR, &btmtk_data->flags);
  }
  
 +static int btusb_mtk_disconnect(struct hci_dev *hdev)
 +{
 +	/* This function describes the specific additional steps taken by MediaTek
 +	 * when Bluetooth usb driver's resume function is called.
 +	 */
 +	btusb_mtk_release_iso_intf(hdev);
 +
 +	return 0;
 +}
 +
  static int btusb_mtk_reset(struct hci_dev *hdev, void *rst_data)
  {
  	struct btusb_data *data = hci_get_drvdata(hdev);
@@ -2678,7 +2688,7 @@
  		return err;
  
  	if (test_bit(BTMTK_ISOPKT_RUNNING, &btmtk_data->flags))
 -		btusb_mtk_release_iso_intf(data);
 +		btusb_mtk_release_iso_intf(hdev);
  
  	btusb_stop_traffic(data);
  	usb_kill_anchored_urbs(&data->tx_anchor);
@@ -3850,6 +3860,7 @@
  		data->recv_acl = btmtk_usb_recv_acl;
  		data->suspend = btmtk_usb_suspend;
  		data->resume = btmtk_usb_resume;
 +		data->disconnect = btusb_mtk_disconnect;
  	}
  
  	if (id->driver_info & BTUSB_SWAVE) {

""""""
