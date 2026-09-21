PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS don_vi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_don_vi TEXT UNIQUE NOT NULL,
    ten_don_vi TEXT NOT NULL,
    ten_don_vi_chuan TEXT NOT NULL UNIQUE,
    loai_don_vi TEXT,
    thong_tin_mo_rong TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nhan_vien (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_nhan_vien TEXT UNIQUE NOT NULL,
    ho_ten TEXT NOT NULL,
    ho_ten_chuan TEXT NOT NULL,
    ma_don_vi TEXT,
    ten_don_vi TEXT,
    don_vi TEXT,
    chuc_vu TEXT,
    email TEXT,
    thong_tin_mo_rong TEXT NOT NULL DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_don_vi) REFERENCES don_vi(ma_don_vi)
);

CREATE TABLE IF NOT EXISTS business_rule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_quy_tac TEXT UNIQUE NOT NULL,
    ten_quy_tac TEXT,
    pham_vi TEXT NOT NULL CHECK (pham_vi IN ('DON_VI','LOAI_DON_VI')),
    ma_don_vi TEXT,
    ten_don_vi TEXT,
    loai_don_vi TEXT,
    ket_qua TEXT NOT NULL CHECK (ket_qua IN ('YES','NO')),
    can_cu TEXT NOT NULL,
    muc_uu_tien INTEGER NOT NULL DEFAULT 0,
    ngay_hieu_luc TEXT,
    ngay_het_hieu_luc TEXT,
    dang_ap_dung INTEGER NOT NULL DEFAULT 1 CHECK (dang_ap_dung IN (0,1)),
    la_mock INTEGER NOT NULL DEFAULT 0 CHECK (la_mock IN (0,1)),
    ghi_chu TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_don_vi) REFERENCES don_vi(ma_don_vi)
);

CREATE TABLE IF NOT EXISTS ngoai_le_ca_nhan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_quy_tac TEXT,
    ma_nhan_vien TEXT NOT NULL,
    ket_qua TEXT NOT NULL CHECK (ket_qua IN ('YES','NO')),
    can_cu TEXT NOT NULL,
    muc_uu_tien INTEGER NOT NULL DEFAULT 100,
    ngay_hieu_luc TEXT,
    ngay_het_hieu_luc TEXT,
    dang_ap_dung INTEGER NOT NULL DEFAULT 1 CHECK (dang_ap_dung IN (0,1)),
    la_mock INTEGER NOT NULL DEFAULT 0 CHECK (la_mock IN (0,1)),
    ghi_chu TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_nhan_vien) REFERENCES nhan_vien(ma_nhan_vien)
);

CREATE TABLE IF NOT EXISTS don_vi_nguon (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ma_don_vi_nguon TEXT,
    ten_don_vi TEXT NOT NULL,
    loai_don_vi TEXT,
    don_vi_cha TEXT,
    thong_tin_mo_rong TEXT NOT NULL DEFAULT '{}'
);

DROP VIEW IF EXISTS quy_tac_tra_luong;
CREATE VIEW quy_tac_tra_luong AS
SELECT id, ma_quy_tac, ten_quy_tac, pham_vi, ma_don_vi, loai_don_vi,
       ket_qua, can_cu, muc_uu_tien, ngay_hieu_luc, ngay_het_hieu_luc,
       dang_ap_dung, ghi_chu, created_at, updated_at
FROM business_rule;

CREATE INDEX IF NOT EXISTS idx_nhan_vien_msnv ON nhan_vien(ma_nhan_vien);
CREATE INDEX IF NOT EXISTS idx_nhan_vien_ho_ten_chuan ON nhan_vien(ho_ten_chuan);
CREATE INDEX IF NOT EXISTS idx_nhan_vien_ma_don_vi ON nhan_vien(ma_don_vi);
CREATE INDEX IF NOT EXISTS idx_don_vi_ten_chuan ON don_vi(ten_don_vi_chuan);
CREATE INDEX IF NOT EXISTS idx_rule_ma_don_vi ON business_rule(ma_don_vi);
CREATE INDEX IF NOT EXISTS idx_rule_loai_don_vi ON business_rule(loai_don_vi);
CREATE INDEX IF NOT EXISTS idx_ngoai_le_msnv ON ngoai_le_ca_nhan(ma_nhan_vien);
CREATE INDEX IF NOT EXISTS idx_don_vi_nguon_ten ON don_vi_nguon(ten_don_vi);
