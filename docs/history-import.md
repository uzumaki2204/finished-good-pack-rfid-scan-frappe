# Import lịch sử RFID (0.1.48)

Trong Data Import, chọn Reference DocType và tải template mới từ production sau khi migrate. Nhập bằng System Manager hoặc RFID Scan Manager. Nhập Session trước, Detail sau, kiểu Insert New Records. Không nhập lại cùng Session ID / Pack Detail ID để tạo bản mới; các khóa trùng bị từ chối. Muốn chỉnh sửa dùng Update Existing Records và ID bản ghi đã có.

## RFID Scan Session

Bắt buộc: Session ID (giữ UUID hệ thống cũ), Company (ID công ty Frappe), Factory Device (ID thiết bị đã có thuộc công ty), Status = Completed, Started At, Completed At, Booking IDs (JSON array, ví dụ `["B26110300003"]`). Nhập Planned RFID, Planned Boxes và biển số/tài xế/ghi chú nếu có. Không tự lấy ERP để bổ sung lịch sử.

## RFID Scan Detail

Bắt buộc: Session (Session ID đã nhập), Company, Factory Device, Pack Detail ID (giữ ID chi tiết nguồn), RFID, Scanned At, Booking ID (thuộc Booking IDs của phiên).

Bổ sung Order No (PO), DO No, Item Code, Box No, Metal Checked (0/1), Sample Code đầy đủ, Set Code, mã/tên thị trường/màu/size và các trường nguồn khác nếu có. Lấy tên cột chính xác từ template. Giữ cột mã dưới dạng Text trong Excel để không mất số 0 đầu.

Không điền Scan Key, Normalized RFID, Storage Version, Source Layout: hệ thống tạo tự động. Scan Snapshot đã bị loại bỏ. Tổng hàng scan/rà kim của phiên được tính lại từ chi tiết đã nhập; thùng scan được báo cáo tính theo Booking+PO+DO+số thùng. Nhập đủ file chi tiết trước khi đối chiếu với báo cáo nguồn.

Thời gian nhập vào Started At, Completed At và Scanned At dùng UTC dạng `YYYY-MM-DD HH:mm:ss` theo cách lưu của ứng dụng RFID (giờ Việt Nam trừ 7 giờ). Báo cáo chuyển sang giờ Việt Nam khi hiển thị. Source Scanned At nếu nhập là ISO 8601 và phải khớp thời gian scan; có thể bỏ trống để hệ thống tạo.

Nhập hai bảng này không tạo kế hoạch RFID chưa scan. Các tổng kế hoạch lấy từ Session; không dựng lại danh sách hàng chưa scan bằng ERP hiện tại. Dùng báo cáo Desk để đối chiếu lịch sử được nhập.
