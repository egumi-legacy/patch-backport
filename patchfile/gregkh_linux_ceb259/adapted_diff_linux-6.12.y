modified file: drivers/spi/spi-intel-pci.c
--- patchfile/gregkh_linux_ceb259/linux-6.12.y/drivers/spi/spi-intel-pci.c
+++ patchfile/gregkh_linux_ceb259/adapted_linux-6.12.y/drivers/spi/spi-intel-pci.c
@@ -86,6 +86,8 @@
  	{ PCI_VDEVICE(INTEL, 0xa324), (unsigned long)&cnl_info },
  	{ PCI_VDEVICE(INTEL, 0xa3a4), (unsigned long)&cnl_info },
  	{ PCI_VDEVICE(INTEL, 0xa823), (unsigned long)&cnl_info },
 +	{ PCI_VDEVICE(INTEL, 0xe323), (unsigned long)&cnl_info },
 +	{ PCI_VDEVICE(INTEL, 0xe423), (unsigned long)&cnl_info },
  	{ },
  };
  MODULE_DEVICE_TABLE(pci, intel_spi_pci_ids);

""""""
