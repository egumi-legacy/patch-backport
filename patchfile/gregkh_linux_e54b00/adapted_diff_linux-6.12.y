modified file: drivers/gpu/drm/display/drm_dp_mst_topology.c
--- patchfile/gregkh_linux_e54b00/linux-6.12.y/drivers/gpu/drm/display/drm_dp_mst_topology.c
+++ patchfile/gregkh_linux_e54b00/adapted_linux-6.12.y/drivers/gpu/drm/display/drm_dp_mst_topology.c
@@ -4108,9 +4108,10 @@
  static int drm_dp_mst_handle_up_req(struct drm_dp_mst_topology_mgr *mgr)
  {
  	struct drm_dp_pending_up_req *up_req;
 +	struct drm_dp_mst_branch *mst_primary;
  
  	if (!drm_dp_get_one_sb_msg(mgr, true, NULL))
 -		goto out;
 +		goto out_clear_reply;
  
  	if (!mgr->up_req_recv.have_eomt)
  		return 0;
@@ -4128,10 +4129,19 @@
  		drm_dbg_kms(mgr->dev, "Received unknown up req type, ignoring: %x\n",
  			    up_req->msg.req_type);
  		kfree(up_req);
 -		goto out;
 -	}
 -
 -	drm_dp_send_up_ack_reply(mgr, mgr->mst_primary, up_req->msg.req_type,
 +		goto out_clear_reply;
 +	}
 +
 +	mutex_lock(&mgr->lock);
 +	mst_primary = mgr->mst_primary;
 +	if (!mst_primary || !drm_dp_mst_topology_try_get_mstb(mst_primary)) {
 +		mutex_unlock(&mgr->lock);
 +		kfree(up_req);
 +		goto out_clear_reply;
 +	}
 +	mutex_unlock(&mgr->lock);
 +
 +	drm_dp_send_up_ack_reply(mgr, mst_primary, up_req->msg.req_type,
  				 false);
  
  	if (up_req->msg.req_type == DP_CONNECTION_STATUS_NOTIFY) {
@@ -4148,13 +4158,13 @@
  			    conn_stat->peer_device_type);
  
  		mutex_lock(&mgr->probe_lock);
 -		handle_csn = mgr->mst_primary->link_address_sent;
 +		handle_csn = mst_primary->link_address_sent;
  		mutex_unlock(&mgr->probe_lock);
  
  		if (!handle_csn) {
  			drm_dbg_kms(mgr->dev, "Got CSN before finish topology probing. Skip it.");
  			kfree(up_req);
 -			goto out;
 +			goto out_put_primary;
  		}
  	} else if (up_req->msg.req_type == DP_RESOURCE_STATUS_NOTIFY) {
  		const struct drm_dp_resource_status_notify *res_stat =
@@ -4171,7 +4181,9 @@
  	mutex_unlock(&mgr->up_req_lock);
  	queue_work(system_long_wq, &mgr->up_req_work);
  
 -out:
 +out_put_primary:
 +	drm_dp_mst_topology_put_mstb(mst_primary);
 +out_clear_reply:
  	memset(&mgr->up_req_recv, 0, sizeof(struct drm_dp_sideband_msg_rx));
  	return 0;
  }

""""""
