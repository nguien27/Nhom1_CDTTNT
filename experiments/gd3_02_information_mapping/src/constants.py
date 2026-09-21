"""Hằng số dùng chung cho GĐ3-02 Information Extraction + Schema Mapping.

Ranh giới module:
- Được phép: extraction, schema mapping, confidence, validation.
- Không được phép: Search, Rule Engine hoặc quyết định YES/NO/CHUA_XAC_DINH.
"""

STANDARD_FIELDS = [
    "ma_nhan_vien",
    "ho_ten",
    "don_vi",
    "loai_don_vi",
    "chuc_vu",
    "email",
    "extension",
]

REQUIRED_FIELDS = [
    "ma_nhan_vien",
    "ho_ten",
    "don_vi",
]

# Alias cục bộ chỉ là lớp tương thích/fallback. Mapper chính vẫn ưu tiên GĐ2-02.
FIELD_ALIASES = {
    "ma_nhan_vien": [
        "ma_nhan_vien", "mã nhân viên", "ma nhan vien", "mã nv", "ma nv", "msnv",
        "mã cán bộ", "ma can bo", "mã cb", "ma cb", "mã cbcs", "ma cbcs",
        "mã cán bộ chiến sĩ", "số hiệu", "so hieu", "employee id", "employee_id",
        "emp id", "emp_id", "employee code", "staff code",
    ],
    "ho_ten": [
        "ho_ten", "họ tên", "ho ten", "họ và tên", "ho va ten", "tên cán bộ",
        "ten can bo", "tên nhân viên", "ten nhan vien", "tên cbcs", "ten cbcs",
        "full name", "fullname", "employee name", "staff name", "name",
    ],
    "don_vi": [
        "don_vi", "đơn vị", "don vi", "tên đơn vị", "ten don vi", "đơn vị công tác",
        "don vi cong tac", "phòng ban", "phong ban", "cơ quan công tác", "co quan cong tac",
        "đơn vị làm việc", "don vi lam viec", "bộ phận", "bo phan", "department",
        "organization", "unit name", "dept",
    ],
    "loai_don_vi": [
        "loai_don_vi", "loại đơn vị", "loai don vi", "loại cơ quan", "loai co quan",
        "loại tổ chức", "loai to chuc", "phân loại đơn vị", "phan loai don vi", "unit type",
        "organization type",
    ],
    "chuc_vu": [
        "chuc_vu", "chức vụ", "chuc vu", "chức danh", "chuc danh", "vị trí", "vi tri",
        "vị trí công tác", "vi tri cong tac", "position", "title", "role",
    ],
    "email": [
        "email", "e-mail", "mail", "gmail", "email cá nhân", "email ca nhan",
        "địa chỉ email", "dia chi email", "thư điện tử", "thu dien tu",
    ],
    "extension": [
        "extension", "ext", "số nội bộ", "so noi bo", "máy lẻ", "may le", "số máy lẻ",
        "so may le", "số điện thoại nội bộ", "so dien thoai noi bo", "điện thoại nội bộ",
        "dien thoai noi bo",
    ],
}

# GĐ2-02 hiện huấn luyện trực tiếp trên 5 nhãn này.
GD2_02_SUPPORTED_LABELS = {
    "MA_NHAN_VIEN": "ma_nhan_vien",
    "HO_TEN": "ho_ten",
    "TEN_DON_VI": "don_vi",
    "LOAI_DON_VI": "loai_don_vi",
}

CONFIDENCE_THRESHOLDS = {
    "high": 0.85,
    "medium": 0.60,
    "low": 0.40,
}

# Mapping thấp hơn ngưỡng này được xem là quá yếu để dùng làm gợi ý có mục tiêu.
MIN_MAPPING_CONFIDENCE = 0.30

# Quy tắc GĐ3-02: dưới 0.85 phải có Human Confirmation/Correction.
CONFIRMATION_THRESHOLD = 0.85

VALIDATION_ERRORS = {
    "MISSING_MA_NHAN_VIEN": "Thiếu mã nhân viên.",
    "MISSING_HO_TEN": "Thiếu họ tên.",
    "MISSING_DON_VI": "Thiếu đơn vị.",
    "DUPLICATE_MAPPING": "Có nhiều trường nguồn cùng ánh xạ vào một trường đích.",
    "UNKNOWN_FIELD": "Có trường dữ liệu chưa xác định được schema chuẩn.",
    "MULTIPLE_EMPLOYEES": "Phát hiện nhiều nhân viên trong cùng nguồn dữ liệu.",
    "EMPLOYEE_NOT_FOUND": "Không tìm thấy thông tin nhân viên trong dữ liệu đầu vào.",
    "LOW_CONFIDENCE": "Có dữ liệu độ tin cậy dưới 0.85, cần người dùng xác nhận/sửa.",
    "EMPTY_INPUT": "Dữ liệu đầu vào rỗng.",
    "UPSTREAM_ERROR": "Module đầu nguồn trả lỗi.",
}

SUPPORTED_STRUCTURED_EXTENSIONS = [".csv", ".xlsx"]
SUPPORTED_UNSTRUCTURED_EXTENSIONS = [".docx", ".pdf", ".txt"]

EMPLOYEE_CODE_PATTERN = r"\b[A-Za-z]{2,6}\d{2,8}\b"
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
EXTENSION_PATTERN = (
    r"(?:extension|ext|máy\s*lẻ|may\s*le|số\s*nội\s*bộ|so\s*noi\s*bo|"
    r"số\s*máy\s*lẻ|so\s*may\s*le|điện\s*thoại\s*nội\s*bộ|dien\s*thoai\s*noi\s*bo)"
    r"\s*[:\-]?\s*(\d{2,6})"
)

# 2-5 từ, mỗi từ bắt đầu bằng chữ hoa. Hỗ trợ tiếng Việt có dấu và ASCII.
VIETNAMESE_NAME_PATTERN = r"[A-ZÀ-ỴĐ][a-zà-ỹđ]+(?:\s+[A-ZÀ-ỴĐ][a-zà-ỹđ]+){1,4}"

UNIT_PREFIX_PATTERN = (
    r"(?:Phòng|Phong|Ban|Cục|Cuc|Vụ|Vu|Sở|So|Trung\s+tâm|Trung\s+tam|Viện|Vien|"
    r"Khoa|Tổ|To|Đội|Doi|Đoàn|Doan|Bộ\s+phận|Bo\s+phan|Văn\s+phòng|Van\s+phong|"
    r"Chi\s+nhánh|Chi\s+nhanh)"
)

COMMON_POSITIONS = [
    "Chuyên viên", "Chuyên viên chính", "Cán bộ", "Chiến sĩ", "Nhân viên",
    "Đội trưởng", "Đội phó", "Trưởng phòng", "Phó phòng", "Trưởng ban", "Phó ban",
    "Trưởng khoa", "Phó khoa", "Giám đốc", "Phó giám đốc", "Cục trưởng",
    "Phó cục trưởng", "Trưởng đơn vị", "Phó trưởng đơn vị", "Kế toán", "Kế toán viên",
    "Kỹ thuật viên", "Thư ký", "Kỹ sư", "Kỹ sư trưởng AI", "Trưởng nhóm Content",
]

# Chuẩn hóa giá trị loai_don_vi chỉ khi văn bản ghi rõ loại; không suy diễn từ tên đơn vị.
UNIT_TYPE_VALUE_ALIASES = {
    "co quan nha nuoc": "CO_QUAN_NHA_NUOC",
    "don vi su nghiep": "DON_VI_SU_NGHIEP",
    "khoi ho tro": "KHOI_HO_TRO",
    "khoi kinh doanh": "KHOI_KINH_DOANH",
    "khoi san xuat": "KHOI_SAN_XUAT",
    "co_quan_nha_nuoc": "CO_QUAN_NHA_NUOC",
    "don_vi_su_nghiep": "DON_VI_SU_NGHIEP",
    "khoi_ho_tro": "KHOI_HO_TRO",
    "khoi_kinh_doanh": "KHOI_KINH_DOANH",
    "khoi_san_xuat": "KHOI_SAN_XUAT",
}
