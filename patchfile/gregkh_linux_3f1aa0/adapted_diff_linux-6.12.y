modified file: drivers/base/regmap/regmap.c
--- patchfile/gregkh_linux_3f1aa0/linux-6.12.y/drivers/base/regmap/regmap.c
+++ patchfile/gregkh_linux_3f1aa0/adapted_linux-6.12.y/drivers/base/regmap/regmap.c
@@ -1063,13 +1063,13 @@
  
  		if (range_cfg->range_max < range_cfg->range_min) {
 -			dev_err(map->dev, "Invalid range %d: %d < %d\n", i,
 +			dev_err(map->dev, "Invalid range %d: %u < %u\n", i,
  				range_cfg->range_max, range_cfg->range_min);
  			goto err_range;
  		}
  
  		if (range_cfg->range_max > map->max_register) {
 -			dev_err(map->dev, "Invalid range %d: %d > %d\n", i,
 +			dev_err(map->dev, "Invalid range %d: %u > %u\n", i,
  				range_cfg->range_max, map->max_register);
  			goto err_range;
  		}

""""""
