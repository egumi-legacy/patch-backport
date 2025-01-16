modified file: drivers/scsi/mpi3mr/mpi3mr.h
--- patchfile/gregkh_linux_711201/linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr.h
+++ patchfile/gregkh_linux_711201/adapted_linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr.h
@@ -133,8 +133,6 @@
  #define MPI3MR_RESET_TIMEOUT			510
  
  #define MPI3MR_WATCHDOG_INTERVAL		1000 /* in milli seconds */
 -
 -#define MPI3MR_DEFAULT_CFG_PAGE_SZ		1024 /* in bytes */
  
  #define MPI3MR_RESET_TOPOLOGY_SETTLE_TIME	10
  
@@ -1133,9 +1131,6 @@
   * @io_throttle_low: I/O size to stop throttle in 512b blocks
   * @num_io_throttle_group: Maximum number of throttle groups
   * @throttle_groups: Pointer to throttle group info structures
 - * @cfg_page: Default memory for configuration pages
 - * @cfg_page_dma: Configuration page DMA address
 - * @cfg_page_sz: Default configuration page memory size
   * @sas_transport_enabled: SAS transport enabled or not
   * @scsi_device_channel: Channel ID for SCSI devices
   * @transport_cmds: Command tracker for SAS transport commands
@@ -1331,10 +1326,6 @@
  	u32 io_throttle_low;
  	u16 num_io_throttle_group;
  	struct mpi3mr_throttle_group_info *throttle_groups;
 -
 -	void *cfg_page;
 -	dma_addr_t cfg_page_dma;
 -	u16 cfg_page_sz;
  
  	u8 sas_transport_enabled;
  	u8 scsi_device_channel;

""""""
modified file: drivers/scsi/mpi3mr/mpi3mr_fw.c
--- patchfile/gregkh_linux_711201/linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr_fw.c
+++ patchfile/gregkh_linux_711201/adapted_linux-6.12.y/drivers/scsi/mpi3mr/mpi3mr_fw.c
@@ -4186,17 +4186,6 @@
  	mpi3mr_read_tsu_interval(mrioc);
  	mpi3mr_print_ioc_info(mrioc);
  
 -	if (!mrioc->cfg_page) {
 -		dprint_init(mrioc, "allocating config page buffers\n");
 -		mrioc->cfg_page_sz = MPI3MR_DEFAULT_CFG_PAGE_SZ;
 -		mrioc->cfg_page = dma_alloc_coherent(&mrioc->pdev->dev,
 -		    mrioc->cfg_page_sz, &mrioc->cfg_page_dma, GFP_KERNEL);
 -		if (!mrioc->cfg_page) {
 -			retval = -1;
 -			goto out_failed_noretry;
 -		}
 -	}
 -
  	dprint_init(mrioc, "allocating host diag buffers\n");
  	mpi3mr_alloc_diag_bufs(mrioc);
  
@@ -4768,11 +4757,7 @@
  		    mrioc->admin_req_base, mrioc->admin_req_dma);
  		mrioc->admin_req_base = NULL;
  	}
 -	if (mrioc->cfg_page) {
 -		dma_free_coherent(&mrioc->pdev->dev, mrioc->cfg_page_sz,
 -		    mrioc->cfg_page, mrioc->cfg_page_dma);
 -		mrioc->cfg_page = NULL;
 -	}
 +
  	if (mrioc->pel_seqnum_virt) {
  		dma_free_coherent(&mrioc->pdev->dev, mrioc->pel_seqnum_sz,
  		    mrioc->pel_seqnum_virt, mrioc->pel_seqnum_dma);
@@ -5392,55 +5377,6 @@
  	return retval;
  }
  
 -
 -/**
 - * mpi3mr_free_config_dma_memory - free memory for config page
 - * @mrioc: Adapter instance reference
 - * @mem_desc: memory descriptor structure
 - *
 - * Check whether the size of the buffer specified by the memory
 - * descriptor is greater than the default page size if so then
 - * free the memory pointed by the descriptor.
 - *
 - * Return: Nothing.
 - */
 -static void mpi3mr_free_config_dma_memory(struct mpi3mr_ioc *mrioc,
 -	struct dma_memory_desc *mem_desc)
 -{
 -	if ((mem_desc->size > mrioc->cfg_page_sz) && mem_desc->addr) {
 -		dma_free_coherent(&mrioc->pdev->dev, mem_desc->size,
 -		    mem_desc->addr, mem_desc->dma_addr);
 -		mem_desc->addr = NULL;
 -	}
 -}
 -
 -/**
 - * mpi3mr_alloc_config_dma_memory - Alloc memory for config page
 - * @mrioc: Adapter instance reference
 - * @mem_desc: Memory descriptor to hold dma memory info
 - *
 - * This function allocates new dmaable memory or provides the
 - * default config page dmaable memory based on the memory size
 - * described by the descriptor.
 - *
 - * Return: 0 on success, non-zero on failure.
 - */
 -static int mpi3mr_alloc_config_dma_memory(struct mpi3mr_ioc *mrioc,
 -	struct dma_memory_desc *mem_desc)
 -{
 -	if (mem_desc->size > mrioc->cfg_page_sz) {
 -		mem_desc->addr = dma_alloc_coherent(&mrioc->pdev->dev,
 -		    mem_desc->size, &mem_desc->dma_addr, GFP_KERNEL);
 -		if (!mem_desc->addr)
 -			return -ENOMEM;
 -	} else {
 -		mem_desc->addr = mrioc->cfg_page;
 -		mem_desc->dma_addr = mrioc->cfg_page_dma;
 -		memset(mem_desc->addr, 0, mrioc->cfg_page_sz);
 -	}
 -	return 0;
 -}
 -

""""""
