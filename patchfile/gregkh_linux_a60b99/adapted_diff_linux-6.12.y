modified file: drivers/pci/msi/irqdomain.c
--- patchfile/gregkh_linux_a60b99/linux-6.12.y/drivers/pci/msi/irqdomain.c
+++ patchfile/gregkh_linux_a60b99/adapted_linux-6.12.y/drivers/pci/msi/irqdomain.c
@@ -350,8 +350,11 @@
  
  	domain = dev_get_msi_domain(&pdev->dev);
  
 -	if (!domain || !irq_domain_is_hierarchy(domain))
 -		return mode == ALLOW_LEGACY;
 +	if (!domain || !irq_domain_is_hierarchy(domain)) {
 +		if (IS_ENABLED(CONFIG_PCI_MSI_ARCH_FALLBACKS))
 +			return mode == ALLOW_LEGACY;
 +		return false;
 +	}
  
  	if (!irq_domain_is_msi_parent(domain)) {

""""""
modified file: drivers/pci/msi/msi.c
--- patchfile/gregkh_linux_a60b99/linux-6.12.y/drivers/pci/msi/msi.c
+++ patchfile/gregkh_linux_a60b99/adapted_linux-6.12.y/drivers/pci/msi/msi.c
@@ -432,6 +432,10 @@
  
  	if (WARN_ON_ONCE(dev->msi_enabled))
  		return -EINVAL;
 +
 +	/* Test for the availability of MSI support */
 +	if (!pci_msi_domain_supports(dev, 0, ALLOW_LEGACY))
 +		return -ENOTSUPP;
  
  	nvec = pci_msi_vec_count(dev);
  	if (nvec < 0)

""""""
