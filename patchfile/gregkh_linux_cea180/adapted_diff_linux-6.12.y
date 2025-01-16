modified file: drivers/bluetooth/btusb.c
--- patchfile/gregkh_linux_cea180/linux-6.12.y/drivers/bluetooth/btusb.c
+++ patchfile/gregkh_linux_cea180/adapted_linux-6.12.y/drivers/bluetooth/btusb.c
@@ -870,6 +870,7 @@
  
  	int (*suspend)(struct hci_dev *hdev);
  	int (*resume)(struct hci_dev *hdev);
 +	int (*disconnect)(struct hci_dev *hdev);
  
  	int oob_wake_irq;   /* irq for out-of-band wake-on-bt */
  	unsigned cmd_timeout_cnt;
@@ -4040,6 +4041,9 @@
  	if (data->diag)
  		usb_set_intfdata(data->diag, NULL);
  
 +	if (data->disconnect)
 +		data->disconnect(hdev);
 +
  	hci_unregister_dev(hdev);
  
  	if (intf == data->intf) {

""""""
