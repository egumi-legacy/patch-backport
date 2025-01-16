modified file: drivers/spi/spi-omap2-mcspi.c
--- patchfile/gregkh_linux_4c6ac5/linux-6.12.y/drivers/spi/spi-omap2-mcspi.c
+++ patchfile/gregkh_linux_4c6ac5/adapted_linux-6.12.y/drivers/spi/spi-omap2-mcspi.c
@@ -1561,10 +1561,10 @@
  	}
  
  	mcspi->ref_clk = devm_clk_get_optional_enabled(&pdev->dev, NULL);
 -	if (mcspi->ref_clk)
 +	if (IS_ERR(mcspi->ref_clk))
 +		mcspi->ref_clk_hz = OMAP2_MCSPI_MAX_FREQ;
 +	else
  		mcspi->ref_clk_hz = clk_get_rate(mcspi->ref_clk);
 -	else
 -		mcspi->ref_clk_hz = OMAP2_MCSPI_MAX_FREQ;
  	ctlr->max_speed_hz = mcspi->ref_clk_hz;
  	ctlr->min_speed_hz = mcspi->ref_clk_hz >> 15;
  

""""""
