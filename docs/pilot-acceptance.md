# Kiểm tra trên site Pilot

Chỉ thực hiện qua Pilot trên site thử nghiệm có `factory_management`. Không đăng nhập SSH và không sửa SQL Server.

1. Cài nhánh `version-16`, chạy migrate. Xác nhận Module **Finished Good Pack RFID Scan**, bốn DocType, hai Role, trang `/finished-good-pack-rfid-scan` và patch `v0_1_0_setup` đã được ghi trong Patch Log.
2. Mở tablet qua HTTPS. Xác nhận giao diện chỉ dùng style Desk; không có `site.css` hoặc theme khác. Đổi Việt/Anh và kiểm tra nhãn, lỗi, toast, fallback.
3. Thử ID thiết bị sai, Pending, Deactivated, khác Company; chỉ Approved + active + Company được dùng. Kiểm tra thiết bị của Company A không mở/xóa/hoàn tất phiên của Company B hoặc thiết bị khác.
4. Tạo **RFID SOAP Account** cho từng Company bằng thông tin thử nghiệm nhập trực tiếp trên site. Thử URL sai, mật khẩu sai, SOAP timeout, booking không tồn tại hoặc chưa có thùng. Không có mật khẩu trong GitHub hay API response.
5. Nạp hai booking, xem xung đột phiên và thử tạo không xác nhận (409), sau đó xác nhận. Kiểm tra PO, item, box, thùng chưa map và cảnh báo kế hoạch.
6. Quét RFID hợp lệ, quét trùng trong phiên, RFID không thuộc snapshot, gỡ scan nhầm. Làm mới một booking và kiểm tra delta tăng/giảm; nếu RFID cũ biến mất, gỡ scan cũ rồi retry hoàn tất.
7. Tắt mạng sau khi shell và booking đã nạp. Mở lại trang, quét tiếp, khởi động lại trình duyệt và kiểm tra IndexedDB giữ scan. Bật mạng, hoàn tất và kiểm tra scan detail/đếm rà kim/lịch sử. Retry hoàn tất sau khi giả lập mất response phải trả cùng phiên đã hoàn thành.
8. Quét QR trên HTTPS; trên trình duyệt không có BarcodeDetector hoặc camera bị từ chối, nhập ID thiết bị thủ công. Trên host HTTP, kiểm tra thông báo yêu cầu HTTPS.
9. Xóa một phiên active và xác nhận không còn trong danh sách; phiên đã hoàn thành và scan mới chỉ nằm trong Frappe. Lịch sử .NET cũ vẫn chỉ ở ứng dụng cũ.
