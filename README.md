# Finished Good Pack RFID Scan for Frappe 16

App độc lập cho quét RFID thành phẩm theo booking. Module **Finished Good Pack RFID Scan** xuất hiện trong Desk; trang tablet là `/finished-good-pack-rfid-scan` và dùng `desk.bundle.css` mặc định của Frappe, không có CSS riêng.

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
2. Chạy migration qua quy trình Pilot. `bench migrate` đồng bộ DocType, Module Def và chạy patch `v0_1_0_setup` để tạo trang tablet và index. Không sửa trực tiếp trên máy chủ.
3. Biểu tượng app hiện cho người dùng đã đăng nhập Desk. Gán vai trò **RFID Scan Manager** hoặc **RFID Scan Operator** để xem các DocType tương ứng; manager tạo **RFID SOAP Account** theo Company và nhập URL, username, password trên Frappe.
4. Tạo và duyệt thiết bị trong **Factory Device**; mở trang tablet trên HTTPS, nhập hoặc quét ID thiết bị Frappe.
5. Nghiệm thu: chọn nhiều booking → xem xung đột → tạo phiên → scan RFID (có thể offline) → kết nối lại → hoàn thành → xem lịch sử.

Không đưa thông tin đăng nhập SOAP, SQL hoặc SSH vào GitHub, OpenAPI hay Postman collection. Dữ liệu phiên .NET trước đây tiếp tục xem trên ứng dụng cũ.

Nếu Desk chưa hiện biểu tượng, kiểm tra **Installed Apps** của đúng site trong Pilot. App phải có tên `finished_good_pack_rfid_scan` và trang `/finished-good-pack-rfid-scan` phải mở được. Nếu API báo `App finished_good_pack_rfid_scan is not installed`, hãy dùng bước **Install App** trên site; thao tác **Update App** trên bench chưa đủ.

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
