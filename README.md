# Finished Good Pack RFID Scan for Frappe 16

App độc lập cho quét RFID thành phẩm theo booking. Module **Finished Good Pack RFID Scan** xuất hiện trong Desk; trang `/finished-good-pack-rfid-scan` bố trí một cột giữa màn hình trên điện thoại, có logo và nút header dạng icon. Giao diện dùng nền Desk/Bootstrap của Frappe và CSS riêng được giới hạn trong `#rfid-app`. Patch cập nhật HTML của Web Page khi nâng cấp app.

## Phạm vi dữ liệu

- Booking được đọc trực tiếp từ SOAP bằng cấu hình **RFID SOAP Account** theo Company. Mật khẩu dùng trường Password của Frappe và phải được admin nhập trên site.
- Phiên mới, snapshot booking và scan detail được lưu trong database Frappe. App không kết nối SQL Server và không nhập lịch sử hoặc thiết bị từ project .NET.
- Thiết bị phải là **Factory Device** đã Approved, active và gán Company trong `factory_management`. ID Frappe của thiết bị được dùng trên tablet.
- Trang web có thể lưu snapshot và scan chưa hoàn thành trong IndexedDB. Lần đầu mở tablet phải có mạng để tải shell, xác thực thiết bị và nạp booking. Cache của host .NET cũ không được dùng lại. Camera QR cần HTTPS hoặc localhost.

## Cài bằng Pilot

App: `finished_good_pack_rfid_scan`.
Repository: `finished-good-pack-rfid-scan-frappe`.
Branch: `version-16`.
Yêu cầu: Frappe `>=16.53,<17`, `factory_management >=0.1.76,<0.2`.

1. Thêm repository và branch vào **bench** trên Pilot, sau đó chọn **Install App** cho đúng **site** đang mở Desk. Chỉ có file trong `/assets/` nghĩa là mã đã có trên bench, chưa chứng minh app đã cài vào site.
2. Chạy migration qua quy trình Pilot. `bench migrate` đồng bộ DocType, Module Def và chạy patch để tạo hoặc cập nhật HTML trang tablet; bản `0.1.10` thêm patch `v0_1_10_sync_session_tabs`. Không sửa trực tiếp trên máy chủ.
3. Biểu tượng app hiện cho người dùng đã đăng nhập Desk. Gán vai trò **RFID Scan Manager** hoặc **RFID Scan Operator** để xem các DocType tương ứng; manager tạo **RFID SOAP Account** theo Company và nhập URL, username, password trên Frappe.
4. Tạo và duyệt thiết bị trong **Factory Device**; mở trang tablet trên HTTPS, nhập hoặc quét ID thiết bị Frappe.
5. Nghiệm thu: chọn nhiều booking → xem xung đột → tạo phiên → scan RFID (có thể offline) → kết nối lại → hoàn thành → xem lịch sử.

Không đưa thông tin đăng nhập SOAP, SQL hoặc SSH vào GitHub, OpenAPI hay Postman collection. Dữ liệu phiên .NET trước đây tiếp tục xem trên ứng dụng cũ.

Nếu Desk chưa hiện biểu tượng, kiểm tra **Installed Apps** của đúng site trong Pilot. App phải có tên `finished_good_pack_rfid_scan` và trang `/finished-good-pack-rfid-scan` phải mở được. Nếu API báo `App finished_good_pack_rfid_scan is not installed`, hãy dùng bước **Install App** trên site; thao tác **Update App** trên bench chưa đủ.

Khi API trả HTTP 500, nội dung response vẫn giữ thông báo chung; **Error Log** của Frappe ghi traceback trong bản `0.1.6` trở lên để quản trị viên truy nguyên lỗi.

Bản `0.1.7` đọc operation từ query string trực tiếp để tương thích với cách Frappe bind request POST JSON.

Bản `0.1.8` loại ký tự không hợp lệ theo XML 1.0 trong phản hồi SOAP kiểu legacy và ghi tên operation cùng lỗi parser vào **Error Log** khi parse vẫn thất bại; nội dung SOAP không được ghi log.

Bản `0.1.9` giữ nguyên kích hoạt khi mở cài đặt thiết bị từ biểu tượng trên header; nút **Đổi thiết bị** vẫn có thao tác xóa kích hoạt rõ ràng. Nút quay lại phục hồi màn hình đang dùng, kể cả phiên quét đang mở.

Bản `0.1.10` chia dữ liệu phiên thành tab PO, Mã hàng, Thùng, Đồng bộ; bổ sung lọc và tìm số thùng. Trên màn hình quét, thanh RFID/hoàn thành cố định ở đáy. Biển số xe, tài xế và ghi chú được nhập ở bước hoàn thành; phiên đã hoàn thành hiển thị lại thông tin dưới dạng chỉ đọc.

Bản `0.1.11` thêm nút **Hoàn thành** và **Xóa phiên** trên từng thẻ trong **Phiên đang quét**. Nút hoàn thành mở bước xác nhận của đúng phiên; nút xóa yêu cầu xác nhận trước khi gọi API. Số RFID trên thẻ đang quét lấy từ scan đã lưu trên tablet.

Bản `0.1.12` gộp tab **Mã hàng** theo booking, PO và mã hàng để hiển thị số RFID đã quét/tổng. Nút **Chi tiết** mở số lượng theo thị trường, màu và size bằng hộp thoại dùng style Desk mặc định. Patch `v0_1_12_sync_item_details` cập nhật Web Page đã lưu khi Pilot migrate.

Bản `0.1.13` hiển thị mã hàng bằng `SampleCode` như RFID cũ, và đặt **Đã scan**, **Rà kim**, **Thùng hoàn thành/kế hoạch** trong ba thẻ đầu phiên. Tab PO cũng tính số thùng hoàn thành thay cho số item đã scan. Khi số thùng trong SOAP thấp hơn kế hoạch booking, mẫu chỉ có một mã hàng và cùng `QtyPerSet` sẽ hiển thị số item kế hoạch ước tính; cảnh báo và chi tiết vẫn phân biệt phần chưa có RFID. Patch `v0_1_13_sync_session_metrics` cập nhật Web Page đã lưu khi Pilot migrate.

Bản `0.1.14` giữ bốn tab phiên trên cùng một hàng ở điện thoại, giảm khoảng cách ngang giữa các tab và bỏ Booking ID cùng nút Trang chủ khỏi phần đầu thẻ chỉ số. Nút Trang chủ dạng icon nằm trên header cạnh Wi-Fi và cài đặt thiết bị, chỉ hiện khi đang xem phiên. Patch `v0_1_14_sync_session_navigation` cập nhật Web Page đã lưu khi Pilot migrate.

Bản `0.1.15` thay `nav-tabs` bằng nhóm nút chuẩn Desk vì CSS website của site thêm lề phải 32px vào từng tab, làm cắt tab đầu trên điện thoại. Nhóm mới nằm gọn một hàng, giữ điều hướng bàn phím và trạng thái ARIA. Tab Mã hàng bỏ khung ngoài, mỗi mã chỉ còn một viền bo. Patch `v0_1_15_sync_compact_tabs` cập nhật Web Page đã lưu khi Pilot migrate.

Bản `0.1.16` dàn nhóm bốn tab rộng bằng cột nội dung, vẫn giữ cùng một hàng trên điện thoại. Bảng PO bỏ viền ô bên trong và giữ khung bo ngoài của panel. Patch `v0_1_16_sync_full_width_tabs` cập nhật Web Page đã lưu khi Pilot migrate.

Bản `0.1.17` nhận máy quét RFID khi ô nhập chưa được focus, xử lý Enter/Tab và chuỗi có ký tự kết thúc, đồng thời tự chốt sau 60 ms im lặng. Quy tắc chuẩn hóa RFID giống .NET; lỗi không tìm thấy và RFID trùng trong kế hoạch có thông báo riêng. Tăng cache service worker để tablet nạp client mới.

Bản `0.1.18` bỏ tab và danh sách RFID Đồng bộ, dàn đều ba tab PO/Mã hàng/Thùng; các tùy chọn cập nhật booking, khôi phục kế hoạch và xóa phiên chuyển vào phần tùy chọn phiên. Khi hoàn tất, giao diện hiển thị số bản ghi đang xử lý, đã tải lên trên tổng số, hoặc trạng thái chưa xác nhận. Patch `v0_1_18_hide_sync_tab_and_show_upload_count` cập nhật Web Page đã lưu khi Pilot migrate; cache service worker tăng lên v13.

Bản `0.1.19` báo trạng thái đang tải booking khi tạo phiên và chuyển sang màn hình quét ngay sau khi API tạo phiên thành công. Nếu IndexedDB không lưu được, phiên vẫn mở để hiện rõ lỗi bộ nhớ offline. Cache service worker tăng lên v14.

Bản `0.1.20` đưa thông báo số RFID đã tải lên ra màn hình danh sách sau khi hoàn tất phiên và bỏ phần Tùy chọn phiên khỏi trang quét.

Bản `0.1.21` chạy lại cập nhật Web Page đã lưu để gỡ phần Tùy chọn phiên còn sót trên site đã cài bản trước. Patch `v0_1_21_hide_session_options` cập nhật nội dung trang khi Pilot migrate; cache service worker tăng lên v16.

## Luồng API

Một endpoint Frappe: `/api/method/finished_good_pack_rfid_scan.api.dispatch?operation=...`. GET: `device_check`, `active`, `history`, `session`, `preview_conflicts`. POST JSON: `start`, `preload`, `refresh_delta`, `rehydrate`, `complete`, `delete`. Mọi thao tác kiểm tra lại ID của Factory Device và dùng Company lấy từ thiết bị. Payload phản hồi nằm trong `message` chuẩn của Frappe, bên trong có `success`, `data`, `message` và `errorCode` khi lỗi.

`start` trả lỗi xung đột 409 nếu booking đang có phiên active và chưa gửi `confirmConflicts: true`. `complete` đối chiếu toàn bộ scan với snapshot phía server, ghi scan và chuyển trạng thái trong cùng giao dịch; retry cùng phiên đã hoàn thành trả lại kết quả đã lưu.

Tài liệu: [OpenAPI](docs/openapi.yaml) · [Postman collection](docs/postman-collection.json).

## Kiểm thử cục bộ

```sh
python -m unittest discover -s tests -v
python -m compileall -q finished_good_pack_rfid_scan tests
node --check finished_good_pack_rfid_scan/public/rfid/client.js
```

Chưa thể kiểm thử SOAP thực, Pilot migration, HTTPS/camera và luồng tablet trên site Frappe trong repo cục bộ. Trước khi vận hành, chạy thử trên site pilot với tài khoản SOAP và thiết bị thử nghiệm của từng Company.

Bản `0.1.22` cập nhật giao diện theo RFID Scan: khung 480px, thẻ thống kê gradient, danh sách PO dạng thẻ, giao diện sáng/tối, thanh quét cố định với tạm dừng/tiếp tục, Trang chủ, Làm mới booking và Hoàn thành. Giữ ba tab hiện tại. Patch cập nhật Web Page khi migrate; service worker v17 nạp CSS và client mới.

Bản `0.1.23` đồng bộ trang tạo phiên, lịch sử, kích hoạt và thông tin thiết bị với giao diện RFID mẫu. Trang chủ có tab Phiên quét/Lịch sử, booking dạng danh sách, thẻ phiên có trạng thái và chỉ số, hộp thoại thiết bị hỗ trợ bàn phím. Chỉ số Thùng đã scan trên lịch sử là số thùng đã có RFID, không phải số thùng quét đủ. Patch cập nhật Web Page khi migrate; service worker v18.

Bản `0.1.24` giữ Trang chủ/Làm mới/Hoàn thành ở thanh cố định dưới cùng cả khi xem lịch sử. Phiên đã hoàn thành ẩn ô quét, khóa Làm mới/Hoàn thành và bỏ phần hiển thị biển số xe, tài xế, ghi chú trên màn hình phiên. Form nhập lúc hoàn thành vẫn được giữ. Patch cập nhật Web Page; service worker v19.
