modified file: drivers/power/supply/cros_charge-control.c
--- patchfile/gregkh_linux_e5f84d/linux-6.12.y/drivers/power/supply/cros_charge-control.c
+++ patchfile/gregkh_linux_e5f84d/adapted_linux-6.12.y/drivers/power/supply/cros_charge-control.c
@@ -7,8 +7,10 @@
  #include <acpi/battery.h>
  #include <linux/container_of.h>
  #include <linux/dmi.h>
 +#include <linux/lockdep.h>
  #include <linux/mod_devicetable.h>
  #include <linux/module.h>
 +#include <linux/mutex.h>
  #include <linux/platform_data/cros_ec_commands.h>
  #include <linux/platform_data/cros_ec_proto.h>
  #include <linux/platform_device.h>
@@ -49,6 +51,7 @@
  	struct attribute *attributes[_CROS_CHCTL_ATTR_COUNT];
  	struct attribute_group group;
  
 +	struct mutex lock; /* protects fields below and cros_ec */
  	enum power_supply_charge_behaviour current_behaviour;
  	u8 current_start_threshold, current_end_threshold;
  };
@@ -85,6 +88,8 @@
  {
  	struct ec_params_charge_control req = {};
  
 +	lockdep_assert_held(&priv->lock);
 +
  	req.cmd = EC_CHARGE_CONTROL_CMD_SET;
  
  	switch (priv->current_behaviour) {
@@ -159,6 +164,7 @@
  	struct cros_chctl_priv *priv = cros_chctl_attr_to_priv(&attr->attr,
  							       CROS_CHCTL_ATTR_START_THRESHOLD);
  
 +	guard(mutex)(&priv->lock);
  	return sysfs_emit(buf, "%u\n", (unsigned int)priv->current_start_threshold);
  }
  
@@ -169,6 +175,7 @@
  	struct cros_chctl_priv *priv = cros_chctl_attr_to_priv(&attr->attr,
  							       CROS_CHCTL_ATTR_START_THRESHOLD);
  
 +	guard(mutex)(&priv->lock);
  	return cros_chctl_store_threshold(dev, priv, 0, buf, count);
  }
  
@@ -178,6 +185,7 @@
  	struct cros_chctl_priv *priv = cros_chctl_attr_to_priv(&attr->attr,
  							       CROS_CHCTL_ATTR_END_THRESHOLD);
  
 +	guard(mutex)(&priv->lock);
  	return sysfs_emit(buf, "%u\n", (unsigned int)priv->current_end_threshold);
  }
  
@@ -187,6 +195,7 @@
  	struct cros_chctl_priv *priv = cros_chctl_attr_to_priv(&attr->attr,
  							       CROS_CHCTL_ATTR_END_THRESHOLD);
  
 +	guard(mutex)(&priv->lock);
  	return cros_chctl_store_threshold(dev, priv, 1, buf, count);
  }
  
@@ -195,6 +204,7 @@
  	struct cros_chctl_priv *priv = cros_chctl_attr_to_priv(&attr->attr,
  							       CROS_CHCTL_ATTR_CHARGE_BEHAVIOUR);
  
 +	guard(mutex)(&priv->lock);
  	return power_supply_charge_behaviour_show(dev, EC_CHARGE_CONTROL_BEHAVIOURS,
  						  priv->current_behaviour, buf);
  }
@@ -210,6 +220,7 @@
  	if (ret < 0)
  		return ret;
  
 +	guard(mutex)(&priv->lock);
  	priv->current_behaviour = ret;
  
  	ret = cros_chctl_configure_ec(priv);
@@ -289,6 +300,10 @@
  	priv = devm_kzalloc(dev, sizeof(*priv), GFP_KERNEL);
  	if (!priv)
  		return -ENOMEM;
 +
 +	ret = devm_mutex_init(dev, &priv->lock);
 +	if (ret)
 +		return ret;
  
  	ret = cros_ec_get_cmd_versions(cros_ec, EC_CMD_CHARGE_CONTROL);
  	if (ret < 0)
@@ -327,7 +342,8 @@
  	priv->current_end_threshold = 100;
  
 -	ret = cros_chctl_configure_ec(priv);
 +	scoped_guard(mutex, &priv->lock)
 +		ret = cros_chctl_configure_ec(priv);
  	if (ret < 0)
  		return ret;
  

""""""
