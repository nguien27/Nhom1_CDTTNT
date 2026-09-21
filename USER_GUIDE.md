# Hướng dẫn sử dụng PayrollCheck

Tài liệu này dành cho người dùng không chuyên kỹ thuật và người vận hành hệ thống PayrollCheck.

## 0. Cài đặt và chạy hệ thống

### 0.1. Yêu cầu

Máy cần cài Python phù hợp với project và có thể chạy lệnh `python` trong Terminal hoặc PowerShell.

Mở PowerShell tại thư mục đã giải nén PayrollCheck.

### 0.2. Tạo môi trường ảo

Chạy:

```powershell
python -m venv .venv
```

Kích hoạt môi trường ảo:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script, có thể chạy tạm cho phiên hiện tại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Khi môi trường ảo hoạt động, đầu dòng lệnh thường xuất hiện:

```text
(.venv)
```

### 0.3. Cài thư viện

Nâng cấp pip:

```powershell
python -m pip install --upgrade pip
```

Cài các thư viện bắt buộc:

```powershell
pip install -r requirements.txt
```

### 0.4. Chạy PayrollCheck

Chạy:

```powershell
python run_gd4_server.py
```

Sau đó mở trình duyệt:

```text
http://127.0.0.1:8000
```

Kiểm tra backend:

```text
http://127.0.0.1:8000/health
```

Để dừng server, quay lại PowerShell và nhấn:

```text
Ctrl + C
```

---

## 1. Đăng nhập ADMIN

Mở địa chỉ PayrollCheck do người vận hành cung cấp, ví dụ:

```text
http://127.0.0.1:8000
```

hoặc địa chỉ LAN của máy chạy server.

ADMIN có thể sử dụng các chức năng quản trị như:

- Nhập dữ liệu.
- Mapping.
- Validation.
- Commit.
- Quản lý nhân viên.
- Quản lý đơn vị.
- Quy tắc nghiệp vụ.
- Ngoại lệ cá nhân.
- Cơ sở dữ liệu.
- Các chức năng hệ thống dành cho quản trị viên.

Quyền ADMIN được backend kiểm tra. Không thể trở thành ADMIN chỉ bằng cách sửa giao diện hoặc JavaScript.

---

## 2. Cấu hình tài khoản ADMIN ban đầu

PayrollCheck tạo tài khoản ADMIN từ biến môi trường khi server khởi động.

Nếu không cấu hình riêng, bản demo có thể sử dụng giá trị mặc định của project:

```text
Username: admin
Password: Admin@123
```

Để cấu hình ADMIN riêng, trước khi chạy server hãy nhập trong PowerShell:

```powershell
$env:PAYROLLCHECK_ADMIN_USERNAME="admin"
$env:PAYROLLCHECK_ADMIN_PASSWORD="MatKhauAdmin@123"
$env:PAYROLLCHECK_ADMIN_EMAIL="admin@example.com"

python run_gd4_server.py
```

Nếu username ADMIN này chưa tồn tại, backend sẽ tạo account mới và lưu mật khẩu ở dạng hash, không lưu plaintext.

Lưu ý: nếu username đã tồn tại, thay đổi biến `PAYROLLCHECK_ADMIN_PASSWORD` không tự reset mật khẩu của account cũ.

---

## 3. Tạo thêm tài khoản ADMIN

Hiện tại ADMIN bổ sung được tạo bằng biến môi trường.

Ví dụ muốn tạo:

```text
Username: admin2
Password: SecondAdmin@456
Email: admin2@example.com
```

### Bước 1: Dừng server

Nhấn:

```text
Ctrl + C
```

### Bước 2: Khai báo ADMIN mới

Trong PowerShell:

```powershell
$env:PAYROLLCHECK_ADMIN_USERNAME="admin2"
$env:PAYROLLCHECK_ADMIN_PASSWORD="SecondAdmin@456"
$env:PAYROLLCHECK_ADMIN_EMAIL="admin2@example.com"
```

### Bước 3: Chạy server

```powershell
python run_gd4_server.py
```

Nếu `admin2` chưa tồn tại, hệ thống sẽ tự tạo thêm một account có role `ADMIN`.

Tài khoản ADMIN cũ không bị xóa.

Sau khi account mới đã được tạo, có thể dừng server và mở PowerShell mới hoặc cấu hình lại biến môi trường cho tài khoản vận hành chính.

Ví dụ:

```powershell
$env:PAYROLLCHECK_ADMIN_USERNAME="admin"
$env:PAYROLLCHECK_ADMIN_PASSWORD="Admin@123"
python run_gd4_server.py
```

Account `admin2` đã tạo vẫn còn trong database.

### Lưu ý khi tạo ADMIN

- ADMIN không liên kết với `MA_NHAN_VIEN`.
- Không dùng IP hoặc máy tính để xác định ADMIN.
- Bất kỳ máy nào trong LAN đăng nhập đúng tài khoản ADMIN đều có quyền ADMIN.
- Không chia sẻ mật khẩu ADMIN cho USER.
- Không sửa trực tiếp `password_hash` trong database.

---

## 4. Đăng nhập USER

Tài khoản nhân viên được tạo tự động khi ADMIN commit/import một nhân viên có email hợp lệ.

- Tên đăng nhập: chính là `MA_NHAN_VIEN`, ví dụ `NV001`.
- Mật khẩu ban đầu: phần trước dấu `@` của email tại thời điểm account được tạo.

Ví dụ:

```text
MA_NHAN_VIEN: NV001
EMAIL: nguyenvana@gmail.com
```

thì tài khoản ban đầu là:

```text
Username: NV001
Password: nguyenvana
```

Nếu nhân viên chưa có email, dữ liệu nhân viên vẫn được lưu nhưng chưa có tài khoản đăng nhập.

Import lại một nhân viên đã có account:

- Không tạo account trùng.
- Không reset mật khẩu.
- Email thay đổi sau này không tự reset mật khẩu.

---

## 5. Đổi mật khẩu lần đầu

USER mới đăng nhập lần đầu sẽ chưa được sử dụng hệ thống bình thường.

Hệ thống bắt buộc USER đổi mật khẩu trước.

Nhập:

1. Mật khẩu hiện tại.
2. Mật khẩu mới có ít nhất 6 ký tự.
3. Nhập lại mật khẩu mới.

Sau khi đổi thành công:

- Mật khẩu ban đầu không còn sử dụng được.
- `must_change_password` được chuyển thành `false`.
- USER có thể tiếp tục sử dụng chức năng tra cứu.

---

## 6. Tra cứu

Chọn **Tra cứu đối tượng**.

Nhập mã nhân viên, họ tên hoặc thông tin đơn vị cần tìm.

Hệ thống có thể hiển thị kết quả cho cá nhân hoặc đơn vị tùy dữ liệu và phạm vi tra cứu.

Khi chọn một kết quả, màn hình hiển thị trạng thái nghiệp vụ và căn cứ do Rule Engine xác định.

USER chỉ được sử dụng chức năng tra cứu và xem các thông tin được phép.

---

## 7. Ý nghĩa YES / NO / CHUA_XAC_DINH

- `YES`: Rule Engine tìm được quy tắc hợp lệ cho phép chi trả.
- `NO`: Rule Engine tìm được quy tắc hợp lệ không cho phép chi trả.
- `CHUA_XAC_DINH`: chưa có business rule hợp lệ nào đủ để kết luận YES hoặc NO.

`CHUA_XAC_DINH` không phải lỗi hệ thống và không được lưu thành business rule.

---

## 8. Căn cứ

Mỗi kết quả nghiệp vụ có thể kèm căn cứ như quyết định, quy tắc hoặc nguồn dữ liệu nghiệp vụ.

Căn cứ dùng để giải thích vì sao Rule Engine trả về kết quả hiện tại.

USER chỉ được xem thông tin phục vụ tra cứu.

Các API và màn hình quản trị được backend kiểm tra role. Việc ẩn menu trên giao diện không phải lớp bảo vệ duy nhất.

---

## 9. Quy trình ADMIN: Nhập dữ liệu → Mapping → Validation → Commit

Trang **Nhập dữ liệu** có hai cách đưa dữ liệu vào hệ thống.

### 9.1. Tải file

Ở tab **Tải file**, ô **Loại dữ liệu nạp vào hệ thống** cho phép chọn:

- **Hồ sơ nhân viên / CBCS**: CSV, XLSX, DOCX, PDF, TXT. Với PDF, hệ thống hỗ trợ tài liệu có lớp văn bản đọc được trực tiếp.
- **Quy tắc nghiệp vụ**: CSV, XLSX hoặc TXT dạng bảng. File cần `Tên quy tắc`, `Tên đơn vị áp dụng`, `Kết quả` (`YES/NO`) và `Căn cứ pháp lý / nghiệp vụ`. `Mã quy tắc` có thể để trống để hệ thống tự sinh. Đơn vị áp dụng phải tồn tại trong danh mục hệ thống trước; thông thường danh mục này được hình thành từ `Tên đơn vị` trong hồ sơ nhân viên.
- **Ngoại lệ cá nhân**: CSV, XLSX hoặc TXT dạng bảng. File cần `Mã nhân viên`, `Kết quả` (`YES/NO`) và `Căn cứ`. Nhân viên phải tồn tại trước khi nạp ngoại lệ.

Các file Business Rule và Ngoại lệ được coi là dữ liệu có cấu trúc. Không dùng PDF/DOCX để nạp trực tiếp hai loại này.

### 9.2. Nhập / dán văn bản thủ công

Tab **Nhập / Dán văn bản** chỉ dùng để nhập nhanh **Hồ sơ nhân viên / CBCS**.

Ví dụ nhân viên:

```text
Mã nhân viên: NVTEST01
Họ tên: Nguyễn Văn Test
Tên đơn vị: Cục Đào tạo
Email: nguyenvantest@gmail.com
```

Có thể dán bảng dùng dấu `|`, ví dụ:

```text
Mã nhân viên | Họ tên | Tên đơn vị | Email
NVTEST01 | Nguyễn Văn Test | Cục Đào tạo | nguyenvantest@gmail.com
```

Business Rule được thêm thủ công tại **Quy tắc nghiệp vụ → Thêm quy tắc**. Ngoại lệ được thêm thủ công tại **Ngoại lệ cá nhân → Thêm ngoại lệ**. Cách này tránh nhập nhầm dữ liệu nghiệp vụ qua một ô văn bản chung.

### 9.3. Mapping

Hệ thống gợi ý ánh xạ cột nguồn sang schema chuẩn. Với dữ liệu có cấu trúc, giá trị đã nhập được giữ nguyên; hệ thống không được tự sửa nội dung như họ tên hoặc tên đơn vị.

Các alias email được hỗ trợ gồm:

```text
Email
E-mail
Gmail
Email cá nhân
Địa chỉ email
```

Các tên trên được ánh xạ về trường chuẩn `EMAIL`.

Nếu mapping có độ tin cậy thấp, ADMIN phải xác nhận hoặc chỉnh sửa trước khi tiếp tục. Nếu hệ thống báo thiếu trường bắt buộc, cần quay lại bổ sung dữ liệu hoặc sửa mapping đúng trường.

### 9.4. Validation

Validation kiểm tra:

- Cấu trúc và trường bắt buộc.
- Mapping trùng.
- Định dạng mã nhân viên, email và các giá trị nghiệp vụ.
- Những mapping cần người dùng xác nhận.
- Tham chiếu: Business Rule phải trỏ tới đơn vị đã tồn tại; ngoại lệ phải trỏ tới nhân viên đã tồn tại.

Validation không tự quyết định `YES`, `NO` hay `CHUA_XAC_DINH`.

### 9.5. Commit Mode

- **APPEND**: chỉ thêm bản ghi mới; bản ghi trùng được bỏ qua.
- **UPSERT**: thêm mới và cập nhật bản ghi đã tồn tại.
- **REPLACE**: thay thế dữ liệu của loại đang chọn; chỉ dùng khi hiểu rõ ảnh hưởng và đọc cảnh báo trên giao diện.

### 9.6. Commit nhân viên và tài khoản USER

Chỉ commit khi Validation đạt yêu cầu. Với hồ sơ nhân viên:

- Có email hợp lệ và chưa có account: hệ thống tạo USER.
- Đã có account: không tạo trùng và không reset password.
- Không có email: vẫn commit nhân viên và trả warning rằng chưa tạo USER.

Ví dụ sau khi commit:

```text
MA_NHAN_VIEN: NVTEST01
EMAIL: nguyenvantest@gmail.com
```

tài khoản ban đầu sẽ là:

```text
Username: NVTEST01
Password: nguyenvantest
```

### 9.7. Quản lý Business Rule

Màn **Quy tắc nghiệp vụ** chỉ hiển thị các thông tin cần cho người vận hành:

- Mã quy tắc.
- Tên quy tắc.
- Tên đơn vị áp dụng.
- Kết quả (`YES` hoặc `NO`).
- Căn cứ pháp lý / nghiệp vụ.
- Trạng thái.

ADMIN có thể **Thêm**, **Chỉnh sửa**, **Ngừng áp dụng/Kích hoạt** và **Xóa** quy tắc. Khi tạo thủ công, mã quy tắc có thể để trống để hệ thống tự sinh. Các khóa kỹ thuật như mã đơn vị được hệ thống quản lý nội bộ, ADMIN không cần nhập.

---

## 10. Quản lý nhân viên dành cho ADMIN

Trong **Cá nhân (Nhân sự)**, ADMIN có các thao tác trên từng nhân viên:

- **Tra cứu**: mở kết quả tra cứu và trạng thái chi trả.
- **Chỉnh sửa**: cập nhật họ tên, đơn vị, chức vụ và email.
- **Ngừng hoạt động**: giữ hồ sơ trong cơ sở dữ liệu nhưng khóa tài khoản USER liên kết và thu hồi các phiên đăng nhập đang hoạt động.
- **Kích hoạt**: mở lại hồ sơ và tài khoản USER. Nếu nhân viên chưa có account nhưng đã có email hợp lệ, hệ thống có thể tạo USER theo quy tắc hiện hành.
- **Xóa**: xóa vĩnh viễn hồ sơ nhân viên, account USER và ngoại lệ cá nhân liên quan. Thao tác này không thể hoàn tác.

Khi chỉnh sửa email của nhân viên đã có account, hệ thống **không reset mật khẩu**.

Nên ưu tiên **Ngừng hoạt động** thay vì **Xóa** khi cần giữ lịch sử hồ sơ.

---

## 11. Nhập ngoại lệ cá nhân thủ công

ADMIN có thể tạo ngoại lệ ngay trên giao diện mà không cần chuẩn bị file Excel/CSV.

Vào:

```text
Ngoại lệ cá nhân → Thêm ngoại lệ
```

Nhập các trường:

- **Mã nhân viên**: bắt buộc và phải tồn tại trong hệ thống.
- **Kết quả ngoại lệ**: chỉ được chọn `YES` hoặc `NO`.
- **Căn cứ ngoại lệ**: bắt buộc.
- **Mức ưu tiên**: mặc định `100`.
- **Ngày hiệu lực**: không bắt buộc; nếu nhập thì dùng định dạng ngày trên giao diện.
- **Ngày hết hiệu lực**: không bắt buộc và không được trước ngày hiệu lực.
- **Ghi chú**: không bắt buộc.

Có thể bấm **Kiểm tra nhân viên** trước khi lưu để xác nhận đúng họ tên và đơn vị.

Sau khi lưu, ngoại lệ đang áp dụng được Rule Engine xét trước quy tắc đơn vị.

Trên từng ngoại lệ, ADMIN có thể:

- **Chỉnh sửa**.
- **Ngừng áp dụng**.
- **Kích hoạt** lại.
- **Xóa** vĩnh viễn.

Khi ngoại lệ bị ngừng áp dụng, Rule Engine quay về xét theo thứ tự còn lại:

```text
DON_VI > LOAI_DON_VI > CHUA_XAC_DINH
```

---

## 12. Kiểm tra nhanh tài khoản USER mới

Sau khi ADMIN commit nhân viên mới:

1. Logout ADMIN.
2. Đăng nhập bằng `MA_NHAN_VIEN`.
3. Dùng phần trước dấu `@` của email làm mật khẩu ban đầu.
4. Hệ thống phải bắt đổi mật khẩu.
5. Đổi sang mật khẩu mới.
6. Logout.
7. Thử lại mật khẩu cũ: phải thất bại.
8. Đăng nhập bằng mật khẩu mới: phải thành công.

USER gọi API hoặc chức năng chỉ dành cho ADMIN phải bị backend từ chối với HTTP `403`.

Người chưa đăng nhập gọi API bảo vệ phải nhận HTTP `401`.

---

## 13. Ràng buộc nghiệp vụ quan trọng

AI chỉ phục vụ:

- **Information Extraction**.
- **Schema Mapping**.

AI không được quyết định trạng thái chi trả.

Rule Engine là thành phần duy nhất quyết định theo thứ tự:

```text
ngoại lệ cá nhân > DON_VI > LOAI_DON_VI > CHUA_XAC_DINH
```

Ngoài ra:

- Không lưu YES/NO trực tiếp trong `nhan_vien`.
- Không tạo business rule có kết quả `CHUA_XAC_DINH`.
- Ngoại lệ cá nhân đang hiệu lực luôn được xét trước rule đơn vị.

---

## 14. Lỗi thường gặp

### Không kích hoạt được môi trường ảo

Nếu PowerShell báo không cho chạy script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Không đăng nhập được ADMIN

Kiểm tra:

- Đúng username/password.
- Account ADMIN đã được tạo chưa.
- Có đang dùng database cũ với mật khẩu khác hay không.

Thay đổi biến môi trường không tự reset password của ADMIN đã tồn tại.

### Không đăng nhập được USER

Kiểm tra:

- Nhân viên đã được Commit sau khi có chức năng account chưa.
- Có email hợp lệ tại thời điểm tạo account hay không.
- Username phải đúng `MA_NHAN_VIEN`.
- Password ban đầu phải là toàn bộ phần trước dấu `@`.

Ví dụ:

```text
nguyenvanan@example.com
```

thì password ban đầu là:

```text
nguyenvanan
```

### USER đăng nhập được nhưng chưa tra cứu được

Nếu là lần đầu, USER phải đổi mật khẩu trước.

### USER thấy lỗi 403 khi mở chức năng quản trị

Đây là hành vi đúng. USER không có quyền gọi API ADMIN.

### Nhập dữ liệu báo thiếu trường bắt buộc

Kiểm tra dữ liệu nguồn và Mapping.

Ví dụ nếu hệ thống báo:

```text
Thiếu trường bắt buộc: [HO_TEN, TEN_DON_VI]
```

thì dữ liệu cần bổ sung hoặc map đúng:

```text
Họ tên → HO_TEN
Tên đơn vị → TEN_DON_VI
```

### USER không tồn tại sau import

Kiểm tra nhân viên có email hợp lệ tại thời điểm tạo account hay không.

Nhân viên đã tồn tại từ trước khi chức năng account được thêm vào có thể chưa có USER nếu chưa được commit lại.

### Máy khác trong LAN không mở được PayrollCheck

Kiểm tra:

- Đúng IP máy chạy server.
- Hai máy cùng mạng LAN.
- Windows Firewall cho phép port `8000`.
- Server đang chạy.

### Truy cập bằng điện thoại hoặc máy tính bảng

Thiết bị di động phải cùng mạng LAN với máy chạy PayrollCheck. Mở trình duyệt và truy cập địa chỉ IP của máy chủ, ví dụ:

```text
http://192.168.1.163:8000
```

Trên màn hình nhỏ, menu bên trái được thu gọn. Bấm nút menu ở góc trên bên trái để mở danh mục chức năng. Các bảng dữ liệu rộng có thể vuốt ngang để xem đầy đủ cột.

Nếu điện thoại không truy cập được, kiểm tra IP máy chủ, Wi-Fi/LAN và Windows Firewall cho port `8000`.

### PDF không đọc được

Hệ thống hiện hỗ trợ PDF có lớp văn bản. Với tài liệu scan dạng ảnh, hãy chuyển dữ liệu sang CSV/XLSX/TXT hoặc PDF có lớp văn bản trước khi nhập.

### Kết quả là CHUA_XAC_DINH

Kiểm tra business rule hoặc ngoại lệ phù hợp.

Không sửa trực tiếp bảng nhân viên để gán `YES` hoặc `NO`.
