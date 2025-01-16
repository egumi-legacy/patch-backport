modified file: fs/ceph/file.c
--- patchfile/gregkh_linux_18d44c/linux-6.12.y/fs/ceph/file.c
+++ patchfile/gregkh_linux_18d44c/adapted_linux-6.12.y/fs/ceph/file.c
@@ -1130,7 +1130,7 @@
  						 false, false);
  
  		op = &req->r_ops[0];
 -		if (sparse) {
 +		if (!write && sparse) {
  			extent_cnt = __ceph_sparse_read_ext_count(inode, read_len);
  			ret = ceph_alloc_sparse_ext_map(op, extent_cnt);
  			if (ret) {

""""""
modified file: net/ceph/osd_client.c
--- patchfile/gregkh_linux_18d44c/linux-6.12.y/net/ceph/osd_client.c
+++ patchfile/gregkh_linux_18d44c/adapted_linux-6.12.y/net/ceph/osd_client.c
@@ -1173,6 +1173,8 @@
  
  int __ceph_alloc_sparse_ext_map(struct ceph_osd_req_op *op, int cnt)
  {
 +	WARN_ON(op->op != CEPH_OSD_OP_SPARSE_READ);
 +
  	op->extent.sparse_ext_cnt = cnt;
  	op->extent.sparse_ext = kmalloc_array(cnt,
  					      sizeof(*op->extent.sparse_ext),

""""""
