# PayrollCheck – Hệ thống Tra cứu Chi trả Lương

PayrollCheck hỗ trợ nhập dữ liệu nhân sự, ánh xạ trường dữ liệu, kiểm tra dữ liệu, quản lý quy tắc nghiệp vụ và tra cứu trạng thái chi trả. Quyết định `YES`, `NO` hoặc `CHUA_XAC_DINH` do Rule Engine xác định theo dữ liệu và quy tắc nghiệp vụ; AI chỉ hỗ trợ đọc/trích xuất và ánh xạ dữ liệu đầu vào.

## 1. Yêu cầu

- Windows 10/11 hoặc hệ điều hành có Python tương thích.
- Python 3.10 trở lên được khuyến nghị.
- Có quyền mở cổng 8000 nếu cần truy cập từ máy khác trong mạng LAN.

Kiểm tra Python:

```powershell
python --version
```

## 2. Tạo môi trường ảo

Mở PowerShell tại thư mục PayrollCheck và chạy:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Nếu PowerShell chặn script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 3. Cài thư viện

```powershell
pip install -r requirements.txt
```



## 4. Cấu hình tài khoản ADMIN

Có thể cấu hình tài khoản quản trị trước khi chạy server:

```powershell
$env:PAYROLLCHECK_ADMIN_USERNAME="admin"
$env:PAYROLLCHECK_ADMIN_PASSWORD="MatKhauAdmin@123"
$env:PAYROLLCHECK_ADMIN_EMAIL="admin@example.com"
```

Nếu username chưa tồn tại, hệ thống tạo tài khoản ADMIN và lưu mật khẩu ở dạng hash.

Nếu không cấu hình riêng, hệ thống sử dụng giá trị mặc định được khai báo trong cấu hình ứng dụng.

Để tạo thêm một ADMIN, dừng server, đặt `PAYROLLCHECK_ADMIN_USERNAME` thành username mới cùng mật khẩu/email tương ứng rồi chạy server lại một lần. Account ADMIN cũ không bị xóa và account đã tồn tại không bị tự động reset mật khẩu.

## 5. Chạy hệ thống

```powershell
python run_gd4_server.py
```

Truy cập trên máy chạy server:

```text
http://127.0.0.1:8000
```

Kiểm tra trạng thái backend:

```text
http://127.0.0.1:8000/health
```

Tài liệu API dành cho quản trị/kỹ thuật:

```text
http://127.0.0.1:8000/docs
```

## 6. Truy cập từ máy khác trong LAN

Máy khác phải cùng mạng LAN/Wi-Fi với máy chạy PayrollCheck.

Trong giao diện ADMIN, mở phần **Hệ thống & Mạng LAN** để xem địa chỉ truy cập. Địa chỉ thường có dạng:

```text
http://192.168.x.x:8000
```

Nếu máy khác không truy cập được, kiểm tra Windows Firewall và bảo đảm cổng 8000 được cho phép.

## 7. Tài khoản USER

Khi ADMIN commit/import nhân viên có email hợp lệ, hệ thống tạo USER nếu account chưa tồn tại:

```text
Username = MA_NHAN_VIEN
Mật khẩu ban đầu = phần trước dấu @ của email
```

Ví dụ:

```text
MA_NHAN_VIEN: NV001
EMAIL: nguyenvana@gmail.com
```

Tài khoản ban đầu:

```text
Username: NV001
Password: nguyenvana
```

USER mới phải đổi mật khẩu trong lần đăng nhập đầu tiên.

Import lại nhân viên đã có account không tạo trùng và không reset mật khẩu. Nhân viên không có email vẫn được commit nhưng chưa được tạo tài khoản USER.

## 8. Phân quyền

- `ADMIN`: nhập dữ liệu, mapping, validation, commit, quản lý nhân viên/đơn vị, business rule, ngoại lệ, cơ sở dữ liệu và chức năng hệ thống.
- `USER`: chỉ tra cứu và xem thông tin được phép.
- Chưa đăng nhập: API bảo vệ trả `401`.
- USER gọi API chỉ dành cho ADMIN: backend trả `403`.

## 9. Quy tắc nghiệp vụ

AI chỉ hỗ trợ:

- Information Extraction (trích xuất thông tin).
- Schema Mapping (ánh xạ trường dữ liệu).

AI không quyết định `YES`, `NO`, `CHUA_XAC_DINH`.

Rule Engine áp dụng thứ tự ưu tiên:

```text
ngoại lệ cá nhân > DON_VI > LOAI_DON_VI > CHUA_XAC_DINH
```

Không lưu trực tiếp `YES/NO` trong bảng `nhan_vien`, và không lưu `CHUA_XAC_DINH` thành business rule.

## 10. Dừng server

Trong cửa sổ PowerShell đang chạy server, nhấn:

```text
Ctrl + C
```

## 11. Hướng dẫn sử dụng

Xem `USER_GUIDE.md` để biết chi tiết về đăng nhập ADMIN/USER, đổi mật khẩu lần đầu, nhập dữ liệu, mapping, validation, commit, tra cứu và xử lý lỗi thường gặp.
