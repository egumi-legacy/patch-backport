modified file: drivers/power/supply/cros_charge-control.c
--- patchfile/gregkh_linux_c28dc9/linux-6.12.y/drivers/power/supply/cros_charge-control.c
+++ patchfile/gregkh_linux_c28dc9/adapted_linux-6.12.y/drivers/power/supply/cros_charge-control.c
@@ -134,6 +134,10 @@
  		return -EINVAL;
  
  	if (is_end_threshold) {
 +		/* Start threshold is not exposed, use fixed value */
 +		if (priv->cmd_version == 2)
 +			priv->current_start_threshold = val == 100 ? 0 : val;
 +
  		if (val <= priv->current_start_threshold)
  			return -EINVAL;
  		priv->current_end_threshold = val;
@@ -223,12 +227,10 @@
  {
  	struct cros_chctl_priv *priv = cros_chctl_attr_to_priv(attr, n);
  
 -	if (priv->cmd_version < 2) {
 -		if (n == CROS_CHCTL_ATTR_START_THRESHOLD)
 -			return 0;
 -		if (n == CROS_CHCTL_ATTR_END_THRESHOLD)
 -			return 0;
 -	}
 +	if (n == CROS_CHCTL_ATTR_START_THRESHOLD && priv->cmd_version < 3)
 +		return 0;
 +	else if (n == CROS_CHCTL_ATTR_END_THRESHOLD && priv->cmd_version < 2)
 +		return 0;
  
  	return attr->mode;
  }

""""""
