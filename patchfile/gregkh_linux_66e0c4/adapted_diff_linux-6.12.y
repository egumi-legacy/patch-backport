modified file: fs/ceph/file.c
--- patchfile/gregkh_linux_66e0c4/linux-6.12.y/fs/ceph/file.c
+++ patchfile/gregkh_linux_66e0c4/adapted_linux-6.12.y/fs/ceph/file.c
@@ -1116,19 +1116,6 @@
  			len = read_off + read_len - off;
  		more = len < iov_iter_count(to);
  
 -		num_pages = calc_pages_for(read_off, read_len);
 -		page_off = offset_in_page(off);
 -		pages = ceph_alloc_page_vector(num_pages, GFP_KERNEL);
 -		if (IS_ERR(pages)) {
 -			ceph_osdc_put_request(req);
 -			ret = PTR_ERR(pages);
 -			break;
 -		}
 -
 -		osd_req_op_extent_osd_data_pages(req, 0, pages, read_len,
 -						 offset_in_page(read_off),
 -						 false, false);
 -
  		op = &req->r_ops[0];
  		if (sparse) {
  			extent_cnt = __ceph_sparse_read_ext_count(inode, read_len);
@@ -1138,6 +1125,19 @@
  				break;
  			}
  		}
 +
 +		num_pages = calc_pages_for(read_off, read_len);
 +		page_off = offset_in_page(off);
 +		pages = ceph_alloc_page_vector(num_pages, GFP_KERNEL);
 +		if (IS_ERR(pages)) {
 +			ceph_osdc_put_request(req);
 +			ret = PTR_ERR(pages);
 +			break;
 +		}
 +
 +		osd_req_op_extent_osd_data_pages(req, 0, pages, read_len,
 +						 offset_in_page(read_off),
 +						 false, false);
  
  		ceph_osdc_start_request(osdc, req);
  		ret = ceph_osdc_wait_request(osdc, req);
@@ -1553,6 +1553,16 @@
  			break;
  		}
  
 +		op = &req->r_ops[0];
 +		if (sparse) {
 +			extent_cnt = __ceph_sparse_read_ext_count(inode, size);
 +			ret = ceph_alloc_sparse_ext_map(op, extent_cnt);
 +			if (ret) {
 +				ceph_osdc_put_request(req);
 +				break;
 +			}
 +		}
 +
  		len = iter_get_bvecs_alloc(iter, size, &bvecs, &num_pages);
  		if (len < 0) {
  			ceph_osdc_put_request(req);
@@ -1561,6 +1571,8 @@
  		}
  		if (len != size)
  			osd_req_op_extent_update(req, 0, len);
 +
 +		osd_req_op_extent_osd_data_bvecs(req, 0, bvecs, num_pages, len);
  

""""""
