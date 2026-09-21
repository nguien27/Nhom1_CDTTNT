// ==========================================================================
// PAYROLLCHECK - ENTERPRISE SAAS CLIENT SCRIPT
// Clean, Component-based Architecture, Auditable, Transparent
// ==========================================================================

// Global Application State
const AppState = {
    currentView: 'dashboard',
    userRole: 'ADMIN', // 'ADMIN' or 'USER'
    searchQuery: '',
    searchScope: 'ALL',
    searchPage: 1,
    searchPageSize: 20,
    searchTotalPages: 1,
    searchResults: [],
    selectedResultIndex: -1,
    stats: {},
    systemInfo: {}
};

// View Breadcrumb Titles
const BREADCRUMB_MAP = {
    dashboard: 'Tổng quan',
    search: 'Tra cứu đối tượng',
    employees: 'Cá nhân (Nhân sự)',
    units: 'Đơn vị tổ chức',
    upload: 'Nhập dữ liệu (Data Import)',
    database: 'Cơ sở dữ liệu (Database Explorer)',
    rules: 'Quy tắc nghiệp vụ (Business Rules)',
    exceptions: 'Ngoại lệ cá nhân (Overrides)',
    history: 'Lịch sử tra cứu & Audit Trail',
    system: 'Hệ thống & Mạng LAN'
};

// ==========================================================================
// 1. NAVIGATION & ROUTING
// ==========================================================================
function navigateTo(viewId) {
    AppState.currentView = viewId;

    // Update active nav button
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewId);
    });

    // Update active view panel
    document.querySelectorAll('.page-view').forEach(panel => {
        panel.classList.toggle('hidden', panel.id !== `view-${viewId}`);
    });

    // Update Breadcrumb
    const crumbEl = document.getElementById('current-breadcrumb');
    if (crumbEl) {
        crumbEl.textContent = BREADCRUMB_MAP[viewId] || viewId;
    }

    // Trigger View-specific Initializers
    if (viewId === 'dashboard') {
        loadDashboardStats();
        loadRecentSearches();
    } else if (viewId === 'employees') {
        loadEmployeesTable(1);
    } else if (viewId === 'units') {
        loadUnitsTable();
    } else if (viewId === 'rules') {
        loadRulesTable();
    } else if (viewId === 'exceptions') {
        loadExceptionsTable();
    } else if (viewId === 'history') {
        loadAuditHistory();
    } else if (viewId === 'system') {
        loadSystemSettings();
    } else if (viewId === 'database') {
        switchDbTab('nhan_vien');
    }

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    if (sidebar) sidebar.classList.toggle('open');
}

// Role-based UI switcher
function toggleUserRole(role) {
    AppState.userRole = role;
    const badge = document.getElementById('role-badge');
    if (badge) {
        badge.textContent = role;
        badge.className = `badge-role ${role.toLowerCase()}`;
    }

    // Hide or show admin-only navigation and features
    const adminElements = document.querySelectorAll('.admin-only');
    adminElements.forEach(el => {
        el.style.display = (role === 'ADMIN') ? '' : 'none';
    });

    if (role === 'USER' && ['upload', 'database', 'rules', 'exceptions'].includes(AppState.currentView)) {
        navigateTo('search');
    }
}

// ==========================================================================
// 2. ALERTS & NOTIFICATIONS
// ==========================================================================
function showAlert(message, type = 'info') {
    const alertEl = document.getElementById('global-alert');
    const msgEl = document.getElementById('alert-message');
    const iconEl = document.getElementById('alert-icon');
    if (!alertEl || !msgEl) return;

    alertEl.className = `global-alert ${type}`;
    msgEl.textContent = message;
    iconEl.textContent = type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️';
    alertEl.classList.remove('hidden');

    clearTimeout(window._alertTimer);
    window._alertTimer = setTimeout(() => closeAlert(), 7000);
}

function closeAlert() {
    const alertEl = document.getElementById('global-alert');
    if (alertEl) alertEl.classList.add('hidden');
}

// ==========================================================================
// 3. DASHBOARD CONTROLLER
// ==========================================================================
async function loadDashboardStats() {
    try {
        const res = await fetch('/api/dashboard/stats');
        if (!res.ok) return;
        const data = await res.json();
        AppState.stats = data;

        document.getElementById('dash-stat-nv').textContent = (data.total_employees || 0).toLocaleString();
        document.getElementById('dash-stat-dv').textContent = (data.total_units || 0).toLocaleString();
        document.getElementById('dash-stat-yes').textContent = (data.count_yes || 0).toLocaleString();
        document.getElementById('dash-stat-no').textContent = (data.count_no || 0).toLocaleString();
        document.getElementById('dash-stat-undef').textContent = (data.count_unidentified || 0).toLocaleString();
    } catch (e) {
        console.warn('Lỗi tải thống kê dashboard:', e);
    }
}

async function loadRecentSearches() {
    const tbody = document.getElementById('recent-searches-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/history');
        if (!res.ok) return;
        const data = await res.json();
        const history = data.history || [];

        if (history.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">Chưa có lượt tra cứu nào trong phiên này.</td></tr>`;
            return;
        }

        tbody.innerHTML = history.slice(0, 8).map(h => {
            const status = h.result || 'CHUA_XAC_DINH';
            const statusBadge = renderStatusBadge(status);
            return `
                <tr>
                    <td><code>${escapeHtml(h.query_id)}</code></td>
                    <td><strong>${escapeHtml(h.object_name)}</strong></td>
                    <td><span class="meta-tag">${escapeHtml(h.object_type)}</span></td>
                    <td><em>"${escapeHtml(h.query)}"</em></td>
                    <td>${statusBadge}</td>
                    <td><code>${escapeHtml(h.rule)}</code></td>
                    <td>${escapeHtml(h.timestamp)}</td>
                    <td><small class="text-muted">${escapeHtml(h.user)}</small></td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="quickFillAndSearch('${escapeHtml(h.query)}')">Tra cứu lại</button>
                    </td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">Không thể kết nối lịch sử tra cứu.</td></tr>`;
    }
}

function triggerDashboardSearch() {
    const input = document.getElementById('dashboard-quick-input');
    const scope = document.getElementById('quick-search-scope')?.value || 'ALL';
    if (!input || !input.value.trim()) {
        showAlert('Vui lòng nhập từ khóa tra cứu (MSNV, tên cá nhân hoặc đơn vị).', 'warning');
        return;
    }
    quickFillAndSearch(input.value.trim(), scope);
}

function quickFillAndSearch(term, scope = 'ALL') {
    navigateTo('search');
    const mainInput = document.getElementById('main-search-input');
    if (mainInput) mainInput.value = term;
    setSearchFilter(scope);
    doSearchNow(1);
}

// ==========================================================================
// 4. SEARCH & ELIGIBILITY CHECKER (CORE)
// ==========================================================================
function setSearchFilter(scope) {
    AppState.searchScope = scope;
    document.querySelectorAll('.search-tab-btn').forEach(btn => btn.classList.remove('active'));
    if (scope === 'ALL') document.getElementById('stab-all')?.classList.add('active');
    if (scope === 'CA_NHAN') document.getElementById('stab-canhan')?.classList.add('active');
    if (scope === 'DON_VI') document.getElementById('stab-donvi')?.classList.add('active');
}

async function doSearchNow(page = 1, append = false) {
    const input = document.getElementById('main-search-input');
    const q = (input?.value || '').trim();
    if (!q) {
        showAlert('Vui lòng nhập từ khóa tra cứu.', 'warning');
        return;
    }

    AppState.searchQuery = q;
    AppState.searchPage = page;

    const container = document.getElementById('search-results-container');
    if (!append) {
        container.innerHTML = `
            <div class="empty-state-card">
                <div class="empty-icon">⏳</div>
                <h3>Đang tra cứu dữ liệu...</h3>
                <p>Rule Engine đang tiến hành kiểm tra điều kiện chi trả theo thứ tự ưu tiên.</p>
            </div>`;
    }

    try {
        const res = await fetch(`/search?q=${encodeURIComponent(q)}&page=${page}&limit=${AppState.searchPageSize}`);
        const data = await res.json();

        if (!res.ok) {
            showAlert(data.detail || 'Lỗi khi tra cứu', 'error');
            container.innerHTML = `<div class="empty-state-card"><div class="empty-icon">⚠️</div><h3>Không thể hoàn thành</h3><p>${escapeHtml(data.detail)}</p></div>`;
            return;
        }

        let items = data.ket_qua || [];

        // Lọc theo Scope nếu người dùng chọn tab Cá nhân hoặc Đơn vị
        if (AppState.searchScope === 'CA_NHAN') {
            items = items.filter(it => it.loai_doi_tuong === 'NHAN_VIEN');
        } else if (AppState.searchScope === 'DON_VI') {
            items = items.filter(it => it.loai_doi_tuong === 'DON_VI');
        }

        AppState.searchTotalPages = data.total_pages || 1;

        if (append) {
            AppState.searchResults = AppState.searchResults.concat(items);
        } else {
            AppState.searchResults = items;
            AppState.selectedResultIndex = items.length > 0 ? 0 : -1;
        }

        renderSearchResultsList(AppState.searchResults, data.tong_ket_qua);
        updateSearchPaginationUI(data.tong_ket_qua);

        // Ambiguity check
        const ambiguityAlert = document.getElementById('ambiguity-alert');
        if (ambiguityAlert) {
            ambiguityAlert.classList.toggle('hidden', AppState.searchResults.length <= 1);
        }

        // Render detailed inspection pane for first item
        if (AppState.searchResults.length > 0 && AppState.selectedResultIndex >= 0) {
            renderDetailedInspection(AppState.searchResults[AppState.selectedResultIndex]);
        } else if (!append) {
            document.getElementById('detail-pane-container').innerHTML = `
                <div class="empty-state-card">
                    <div class="empty-icon">🔍</div>
                    <h3>Không tìm thấy đối tượng</h3>
                    <p>Không có cá nhân hoặc đơn vị nào khớp với từ khóa "${escapeHtml(q)}".</p>
                </div>`;
        }
    } catch (err) {
        showAlert('Lỗi kết nối tới máy chủ: ' + err.message, 'error');
    }
}

function renderSearchResultsList(items, totalCount) {
    const totalEl = document.getElementById('search-results-total');
    if (totalEl) totalEl.textContent = totalCount || items.length;

    const container = document.getElementById('search-results-container');
    if (!items || items.length === 0) {
        container.innerHTML = `
            <div class="empty-state-card">
                <div class="empty-icon">🍃</div>
                <h3>Không tìm thấy kết quả</h3>
                <p>Thử tìm kiếm với một phần họ tên hoặc mã số nhân viên khác.</p>
            </div>`;
        return;
    }

    container.innerHTML = items.map((item, idx) => {
        const isSelected = (idx === AppState.selectedResultIndex);
        const status = item.trang_thai_tra_luong?.ket_qua || 'CHUA_XAC_DINH';
        const isMock = item.trang_thai_tra_luong?.la_mock;
        const isNhanVien = (item.loai_doi_tuong === 'NHAN_VIEN');
        const d = item.doi_tuong || {};

        const msnv = isNhanVien ? (d.ma_nhan_vien || item.id_doi_tuong || '') : '';
        const donVi = d.don_vi || d.ten_don_vi || '';
        const hoTen = item.ten_hien_thi || d.ho_ten || d.ten_don_vi || '';
        const matchScore = item.do_khop ? Math.round(item.do_khop * 100) : 100;
        const matchType = item.loai_khop || 'EXACT';

        return `
            <div class="search-result-card ${isSelected ? 'active' : ''}" data-index="${idx}" onclick="selectSearchCard(${idx})">
                <div class="card-top-row">
                    <div>
                        <div class="card-entity-title">${escapeHtml(hoTen)}</div>
                        <div class="card-meta-line">
                            <span class="meta-tag">${isNhanVien ? '👤 Cá nhân' : '🏛️ Đơn vị'}</span>
                            ${msnv ? `<span class="meta-tag">MSNV: ${escapeHtml(msnv)}</span>` : ''}
                            ${donVi ? `<span>🏢 ${escapeHtml(donVi)}</span>` : ''}
                        </div>
                    </div>
                    <div>
                        ${renderStatusBadge(status)}
                    </div>
                </div>
                <div class="card-footer-row">
                    <span class="match-score-badge ${matchScore >= 90 ? 'high' : ''}">Độ phù hợp: ${matchScore}% (${matchType})</span>
                    ${isMock ? `<span class="badge-role user" style="background:#fef3c7;color:#b45309;border:1px dashed #f59e0b;">Mock Rule</span>` : ''}
                    <button class="btn btn-sm btn-outline" style="padding:2px 8px;font-size:11px;">Xem chi tiết ›</button>
                </div>
            </div>`;
    }).join('');
}

function selectSearchCard(index) {
    AppState.selectedResultIndex = index;
    document.querySelectorAll('.search-result-card').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });
    if (AppState.searchResults[index]) {
        renderDetailedInspection(AppState.searchResults[index]);
    }
}

// RENDER STATUS BADGE (CONSISTENT SAAS COMPONENT)
function renderStatusBadge(status) {
    if (status === 'YES') {
        return `<span class="badge-status-pill YES">✓ YES</span>`;
    } else if (status === 'NO') {
        return `<span class="badge-status-pill NO">✕ NO</span>`;
    } else {
        return `<span class="badge-status-pill CHUA_XAC_DINH">? CHƯA XÁC ĐỊNH</span>`;
    }
}

// RENDER DETAILED INSPECTION (FULL AUDIT & TRANSPARENCY)
function renderDetailedInspection(item) {
    const container = document.getElementById('detail-pane-container');
    if (!container) return;

    const statusObj = item.trang_thai_tra_luong || {};
    const status = statusObj.ket_qua || 'CHUA_XAC_DINH';
    const isMock = statusObj.la_mock;
    const isNhanVien = (item.loai_doi_tuong === 'NHAN_VIEN');
    const d = item.doi_tuong || {};

    const hoTen = item.ten_hien_thi || d.ho_ten || d.ten_don_vi || '';
    const msnv = d.ma_nhan_vien || (isNhanVien ? item.id_doi_tuong : '');
    const donVi = d.don_vi || d.ten_don_vi || '';
    const chucVu = d.chuc_vu || 'Chưa cập nhật';
    const email = d.email || 'Chưa cập nhật';
    const loaiDonVi = d.loai_don_vi || 'Phòng ban / Đơn vị thành viên';

    const canCu = statusObj.can_cu || 'Không tìm thấy quy tắc hoặc văn bản áp dụng phù hợp.';
    const maQuyTac = statusObj.ma_quy_tac || 'N/A';
    const nguonQuyTac = statusObj.nguon_quy_tac || (status === 'CHUA_XAC_DINH' ? 'Chưa có quy tắc' : 'BUSINESS_RULE');
    const ghiChu = statusObj.ghi_chu || '';

    let heroTitle = '';
    let heroSubtitle = 'Kết quả được xác định bởi Rule Engine dựa trên cơ sở dữ liệu và quy định.';
    if (status === 'YES') {
        heroTitle = '✓ THUỘC DIỆN ĐƯỢC TRẢ LƯƠNG';
    } else if (status === 'NO') {
        heroTitle = '✕ KHÔNG THUỘC DIỆN ĐƯỢC TRẢ LƯƠNG';
        heroSubtitle = 'Đối tượng thuộc nhóm không áp dụng chi trả theo quy tắc hiện hành.';
    } else {
        heroTitle = '? CHƯA XÁC ĐỊNH';
        heroSubtitle = 'Chưa đủ thông tin phân loại hoặc chưa có quy tắc nghiệp vụ phù hợp.';
    }

    // Step-by-step Audit Steps
    const auditSteps = generateAuditSteps(item, status);

    container.innerHTML = `
        <div class="detail-pane-header">
            <h3>Hồ sơ Chi tiết & Căn cứ Nghiệp vụ</h3>
            <span class="meta-tag">${isNhanVien ? 'Cá nhân' : 'Đơn vị'}</span>
        </div>
        <div class="detail-body-scroll">
            <!-- Identity Box -->
            <div class="identity-box">
                <div class="identity-avatar">${escapeHtml(hoTen.charAt(0).toUpperCase())}</div>
                <div>
                    <div class="identity-name">${escapeHtml(hoTen)}</div>
                    <div class="identity-sub">${isNhanVien ? `MSNV: ${escapeHtml(msnv)} • ${escapeHtml(donVi)}` : `Đơn vị tổ chức • ${escapeHtml(loaiDonVi)}`}</div>
                </div>
            </div>

            <!-- Big Status Hero Card -->
            <div class="status-hero-card ${status}">
                <div class="status-hero-badge">${heroTitle}</div>
                <div class="status-hero-subtitle">${heroSubtitle}</div>
            </div>

            <!-- "Căn cứ nghiệp vụ" (Why this result?) Section -->
            <div class="audit-flow-section">
                <div class="section-label-strong">
                    <span>📋 Căn cứ nghiệp vụ (Why this result?)</span>
                </div>
                <ol class="audit-steps-list">
                    ${auditSteps.map((step, idx) => `<li class="audit-step-item ${idx === auditSteps.length - 1 ? 'highlight' : ''}">${escapeHtml(step)}</li>`).join('')}
                </ol>
            </div>

            <!-- Legal / Policy Basis Box -->
            <div style="margin-bottom: 18px;">
                <div class="section-label-strong">Văn bản & Căn cứ Quy định</div>
                <div style="background:#f8fafc;border-left:4px solid var(--primary);padding:12px;border-radius:4px;font-size:13px;line-height:1.5;">
                    <strong>Quy định áp dụng:</strong> ${escapeHtml(canCu)}
                    ${isMock ? '<div style="margin-top:6px;color:#b45309;font-size:11.5px;"><em>(Lưu ý: Đây là Mock Business Rule dùng cho mục đích kiểm thử mô phỏng).</em></div>' : ''}
                </div>
            </div>

            <!-- Technical & Data Sources Table -->
            <div style="margin-bottom: 18px;">
                <div class="section-label-strong">Nguồn dữ liệu & Truy vết</div>
                <dl class="detail-grid">
                    <dt>Mã quy tắc (Rule ID):</dt><dd><code>${escapeHtml(maQuyTac)}</code></dd>
                    <dt>Nguồn phân giải:</dt><dd><span class="meta-tag">${escapeHtml(nguonQuyTac)}</span></dd>
                    <dt>Tệp nguồn nạp:</dt><dd><code>nhan_vien.csv / SQLite DB</code></dd>
                    <dt>Phiên bản dữ liệu:</dt><dd>v1.0 (Clean Data)</dd>
                    ${chucVu ? `<dt>Chức vụ:</dt><dd>${escapeHtml(chucVu)}</dd>` : ''}
                    ${email ? `<dt>Email liên hệ:</dt><dd>${escapeHtml(email)}</dd>` : ''}
                    ${ghiChu ? `<dt>Ghi chú kiểm tra:</dt><dd>${escapeHtml(ghiChu)}</dd>` : ''}
                </dl>
            </div>
        </div>
    `;
}

function generateAuditSteps(item, status) {
    const isNhanVien = (item.loai_doi_tuong === 'NHAN_VIEN');
    const d = item.doi_tuong || {};
    const donVi = d.don_vi || d.ten_don_vi || 'Đơn vị';
    const statusObj = item.trang_thai_tra_luong || {};
    const ruleId = statusObj.ma_quy_tac || 'RULE-DEFAULT';
    const isNgoaiLe = (statusObj.nguon_quy_tac === 'NGOAI_LE_CA_NHAN');

    if (status === 'YES') {
        if (isNgoaiLe) {
            return [
                `Cá nhân ${item.ten_hien_thi} tồn tại trong cơ sở dữ liệu.`,
                `Phát hiện bản ghi ngoại lệ cá nhân hợp lệ đang áp dụng trong bảng ngoai_le_ca_nhan.`,
                `Ngoại lệ cá nhân có độ ưu tiên cao nhất, ghi đè quy tắc đơn vị.`,
                `Kích hoạt căn cứ: "${statusObj.can_cu || 'Quyết định đặc thù'}".`,
                `Rule Engine kết luận: Thuộc diện được chi trả lương (YES).`
            ];
        }
        return [
            `Đối tượng ${item.ten_hien_thi} tồn tại trong cơ sở dữ liệu SQLite.`,
            `Xác định thuộc đơn vị công tác: "${donVi}".`,
            `Đơn vị "${donVi}" được gắn với quy tắc chi trả lương hợp lệ (${ruleId}).`,
            `Không phát hiện ngoại lệ loại trừ cá nhân.`,
            `Quy tắc ${ruleId} được kích hoạt với căn cứ: "${statusObj.can_cu}".`,
            `Rule Engine kết luận: Thuộc diện được chi trả lương (YES).`
        ];
    } else if (status === 'NO') {
        return [
            `Đối tượng ${item.ten_hien_thi} tồn tại trong cơ sở dữ liệu.`,
            `Xác định thuộc đơn vị: "${donVi}".`,
            `Đơn vị thuộc danh mục không áp dụng kinh phí chi trả hoặc đang tạm hoãn.`,
            `Quy tắc loại trừ ${ruleId} được kích hoạt: "${statusObj.can_cu}".`,
            `Rule Engine kết luận: Không thuộc diện được chi trả lương (NO).`
        ];
    } else {
        return [
            `Đối tượng ${item.ten_hien_thi} được tìm thấy trong hệ thống.`,
            `Tiến hành tra cứu quy tắc nghiệp vụ theo đơn vị "${donVi}".`,
            `Không tìm thấy quy tắc áp dụng phù hợp hoặc thiếu thông tin phân loại đơn vị.`,
            `Theo nguyên tắc an toàn dữ liệu: Hệ thống KHÔNG tự ý suy đoán bằng AI.`,
            `Rule Engine kết luận: CHƯA XÁC ĐỊNH (Cần bổ sung thông tin hoặc thiết lập quy tắc).`
        ];
    }
}

function updateSearchPaginationUI(totalCount) {
    const bar = document.getElementById('search-pagination-bar');
    if (!bar) return;

    if (totalCount <= AppState.searchPageSize && AppState.searchPage === 1) {
        bar.classList.add('hidden');
        return;
    }

    bar.classList.remove('hidden');
    document.getElementById('pagination-info').textContent = `Trang ${AppState.searchPage} / ${AppState.searchTotalPages} (Tổng ${totalCount} kết quả)`;
    document.getElementById('btn-prev-page').disabled = (AppState.searchPage <= 1);
    document.getElementById('btn-next-page').disabled = (AppState.searchPage >= AppState.searchTotalPages);
    document.getElementById('btn-load-more').disabled = (AppState.searchPage >= AppState.searchTotalPages);
}

function goToPage(delta) {
    const target = AppState.searchPage + delta;
    if (target >= 1 && target <= AppState.searchTotalPages) {
        doSearchNow(target, false);
    }
}

function appendNextPage() {
    if (AppState.searchPage < AppState.searchTotalPages) {
        doSearchNow(AppState.searchPage + 1, true);
    }
}

function handleExport(format) {
    const q = (AppState.searchQuery || '').trim() || 'all';
    window.location.href = `/export/search?q=${encodeURIComponent(q)}&format=${encodeURIComponent(format)}`;
}

// ==========================================================================
// 5. EMPLOYEES & UNITS DIRECTORIES
// ==========================================================================
async function loadEmployeesTable(page = 1, search = '') {
    const tbody = document.getElementById('employees-table-body');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4">Đang tải dữ liệu nhân sự...</td></tr>`;

    try {
        const query = search ? `&search=${encodeURIComponent(search)}` : '';
        const res = await fetch(`/api/employees?page=${page}&limit=20${query}`);
        if (!res.ok) return;
        const data = await res.json();
        const emps = data.employees || [];

        if (emps.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">Không có nhân sự nào phù hợp.</td></tr>`;
            return;
        }

        tbody.innerHTML = emps.map(e => {
            const st = e.trang_thai_tra_luong?.ket_qua || 'CHUA_XAC_DINH';
            return `
                <tr>
                    <td><code>${escapeHtml(e.ma_nhan_vien)}</code></td>
                    <td><strong>${escapeHtml(e.ho_ten)}</strong></td>
                    <td>${escapeHtml(e.don_vi || '—')}</td>
                    <td>${escapeHtml(e.chuc_vu || '—')}</td>
                    <td><small>${escapeHtml(e.email || '—')}</small></td>
                    <td>${renderStatusBadge(st)}</td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="quickFillAndSearch('${escapeHtml(e.ma_nhan_vien)}')">Tra cứu</button>
                    </td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">Lỗi khi nạp danh sách nhân sự.</td></tr>`;
    }
}

let _debounceEmpTimer = null;
function debounceEmployeeFilter(val) {
    clearTimeout(_debounceEmpTimer);
    _debounceEmpTimer = setTimeout(() => loadEmployeesTable(1, val), 350);
}

async function loadUnitsTable(search = '') {
    const tbody = document.getElementById('units-table-body');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4">Đang tải danh mục đơn vị...</td></tr>`;

    try {
        const res = await fetch('/api/units');
        if (!res.ok) return;
        const data = await res.json();
        let units = data.units || [];

        if (search) {
            const s = search.toLowerCase();
            units = units.filter(u => (u.ten_don_vi || '').toLowerCase().includes(s));
        }

        if (units.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Không tìm thấy đơn vị nào.</td></tr>`;
            return;
        }

        tbody.innerHTML = units.map(u => {
            const st = u.trang_thai_tra_luong?.ket_qua || 'CHUA_XAC_DINH';
            const rule = u.trang_thai_tra_luong?.ma_quy_tac || 'N/A';
            return `
                <tr>
                    <td><code>${escapeHtml(u.ma_don_vi_nguon || `DV_${u.id}`)}</code></td>
                    <td><strong>${escapeHtml(u.ten_don_vi)}</strong></td>
                    <td><span class="meta-tag">${escapeHtml(u.loai_don_vi || 'Phòng ban')}</span></td>
                    <td>${escapeHtml(u.don_vi_cha || '—')}</td>
                    <td><strong>${u.employee_count || 0}</strong> nhân viên</td>
                    <td>${renderStatusBadge(st)}</td>
                    <td><code>${escapeHtml(rule)}</code></td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="quickFillAndSearch('${escapeHtml(u.ten_don_vi)}', 'DON_VI')">Xem chi tiết</button>
                    </td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Lỗi khi tải danh mục đơn vị.</td></tr>`;
    }
}

let _debounceUnitTimer = null;
function debounceUnitFilter(val) {
    clearTimeout(_debounceUnitTimer);
    _debounceUnitTimer = setTimeout(() => loadUnitsTable(val), 350);
}

// ==========================================================================
// 6. BUSINESS RULES & EXCEPTIONS
// ==========================================================================
async function loadRulesTable() {
    const tbody = document.getElementById('rules-table-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/rules');
        if (!res.ok) return;
        const data = await res.json();
        const rules = data.rules || [];

        tbody.innerHTML = rules.map(r => {
            const stBadge = renderStatusBadge(r.ket_qua);
            const isMock = r.la_mock ? '<span class="badge-role user" style="background:#fef3c7;color:#b45309;">MOCK</span>' : '<span class="meta-tag">Chính thức</span>';
            return `
                <tr>
                    <td><code>${escapeHtml(r.ma_quy_tac)}</code></td>
                    <td><strong>${escapeHtml(r.ten_quy_tac || r.ma_quy_tac)}</strong></td>
                    <td><span class="meta-tag">${escapeHtml(r.pham_vi || 'DON_VI')}</span></td>
                    <td>${escapeHtml(r.ten_don_vi || '—')}</td>
                    <td>${escapeHtml(r.loai_don_vi || '—')}</td>
                    <td>${stBadge}</td>
                    <td><strong>${r.muc_uu_tien || 0}</strong></td>
                    <td><small>${escapeHtml(r.can_cu || '—')}</small></td>
                    <td>${isMock}</td>
                    <td><span class="status-chip active"><span class="dot"></span> Active</span></td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4 text-muted">Không thể tải quy tắc nghiệp vụ.</td></tr>`;
    }
}

async function loadExceptionsTable() {
    const tbody = document.getElementById('exceptions-table-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/exceptions');
        if (!res.ok) return;
        const data = await res.json();
        const exList = data.exceptions || [];

        if (exList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Chưa có bản ghi ngoại lệ cá nhân nào trong hệ thống.</td></tr>`;
            return;
        }

        tbody.innerHTML = exList.map(ex => {
            return `
                <tr>
                    <td><code>${escapeHtml(ex.ma_nhan_vien)}</code></td>
                    <td><strong>${escapeHtml(ex.ho_ten || 'Cá nhân ngoại lệ')}</strong></td>
                    <td>${escapeHtml(ex.don_vi || '—')}</td>
                    <td>${renderStatusBadge(ex.ket_qua)}</td>
                    <td><strong>${escapeHtml(ex.can_cu)}</strong></td>
                    <td><span class="meta-tag">${ex.muc_uu_tien || 100}</span></td>
                    <td>${escapeHtml(ex.ngay_hieu_luc || 'Áp dụng ngay')}</td>
                    <td><span class="status-chip active"><span class="dot"></span> Active</span></td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Lỗi khi tải danh sách ngoại lệ.</td></tr>`;
    }
}

// ==========================================================================
// 7. DATABASE EXPLORER & SYSTEM SETTINGS
// ==========================================================================
async function switchDbTab(tableName) {
    document.querySelectorAll('.db-tab-btn').forEach(b => b.classList.remove('active'));
    event?.target?.classList.add('active');

    const container = document.getElementById('db-tab-content');
    container.innerHTML = `<p class="text-muted">Đang truy vấn bảng <code>${tableName}</code>...</p>`;

    if (tableName === 'nhan_vien') {
        const res = await fetch('/api/employees?page=1&limit=10');
        const data = await res.json();
        container.innerHTML = `
            <h4>Bảng nhan_vien (Tổng ${data.total} bản ghi)</h4>
            <div class="table-responsive" style="margin-top:10px;">
                <table class="saas-table">
                    <thead><tr><th>ID</th><th>MSNV</th><th>Họ tên</th><th>Đơn vị</th><th>Chức vụ</th><th>Email</th></tr></thead>
                    <tbody>${(data.employees || []).map(r => `<tr><td>${r.id}</td><td><code>${escapeHtml(r.ma_nhan_vien)}</code></td><td>${escapeHtml(r.ho_ten)}</td><td>${escapeHtml(r.don_vi || '')}</td><td>${escapeHtml(r.chuc_vu || '')}</td><td>${escapeHtml(r.email || '')}</td></tr>`).join('')}</tbody>
                </table>
            </div>`;
    } else if (tableName === 'business_rule') {
        const res = await fetch('/api/rules');
        const data = await res.json();
        container.innerHTML = `
            <h4>Bảng business_rule (Tổng ${data.rules.length} bản ghi)</h4>
            <div class="table-responsive" style="margin-top:10px;">
                <table class="saas-table">
                    <thead><tr><th>Mã rule</th><th>Tên quy tắc</th><th>Đơn vị</th><th>Kết quả</th><th>Căn cứ</th><th>Ưu tiên</th></tr></thead>
                    <tbody>${(data.rules || []).map(r => `<tr><td><code>${escapeHtml(r.ma_quy_tac)}</code></td><td>${escapeHtml(r.ten_quy_tac || '')}</td><td>${escapeHtml(r.ten_don_vi || '')}</td><td>${renderStatusBadge(r.ket_qua)}</td><td>${escapeHtml(r.can_cu)}</td><td>${r.muc_uu_tien}</td></tr>`).join('')}</tbody>
                </table>
            </div>`;
    } else if (tableName === 'ngoai_le_ca_nhan') {
        const res = await fetch('/api/exceptions');
        const data = await res.json();
        container.innerHTML = `
            <h4>Bảng ngoai_le_ca_nhan (Tổng ${data.exceptions.length} bản ghi)</h4>
            <div class="table-responsive" style="margin-top:10px;">
                <table class="saas-table">
                    <thead><tr><th>MSNV</th><th>Họ tên</th><th>Kết quả</th><th>Căn cứ</th><th>Ưu tiên</th></tr></thead>
                    <tbody>${(data.exceptions || []).map(r => `<tr><td><code>${escapeHtml(r.ma_nhan_vien)}</code></td><td>${escapeHtml(r.ho_ten || '')}</td><td>${renderStatusBadge(r.ket_qua)}</td><td>${escapeHtml(r.can_cu)}</td><td>${r.muc_uu_tien}</td></tr>`).join('')}</tbody>
                </table>
            </div>`;
    } else if (tableName === 'don_vi_nguon') {
        const res = await fetch('/api/units');
        const data = await res.json();
        container.innerHTML = `
            <h4>Bảng don_vi_nguon (Tổng ${data.units.length} bản ghi)</h4>
            <div class="table-responsive" style="margin-top:10px;">
                <table class="saas-table">
                    <thead><tr><th>ID</th><th>Mã đơn vị</th><th>Tên đơn vị</th><th>Loại đơn vị</th><th>Đơn vị cha</th></tr></thead>
                    <tbody>${(data.units || []).map(r => `<tr><td>${r.id}</td><td><code>${escapeHtml(r.ma_don_vi_nguon || '')}</code></td><td>${escapeHtml(r.ten_don_vi)}</td><td>${escapeHtml(r.loai_don_vi || '')}</td><td>${escapeHtml(r.don_vi_cha || '')}</td></tr>`).join('')}</tbody>
                </table>
            </div>`;
    }
}

async function loadAuditHistory() {
    const tbody = document.getElementById('audit-table-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/history');
        if (!res.ok) return;
        const data = await res.json();
        const list = data.history || [];

        if (list.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Chưa có nhật ký truy vấn nào.</td></tr>`;
            return;
        }

        tbody.innerHTML = list.map(item => `
            <tr>
                <td><code>${escapeHtml(item.query_id)}</code></td>
                <td>${escapeHtml(item.user)}</td>
                <td><strong>"${escapeHtml(item.query)}"</strong></td>
                <td>${escapeHtml(item.object_name)}</td>
                <td><span class="meta-tag">${escapeHtml(item.object_type)}</span></td>
                <td>${renderStatusBadge(item.result)}</td>
                <td><code>${escapeHtml(item.rule)}</code></td>
                <td><small>${escapeHtml(item.timestamp)}</small></td>
            </tr>`).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Lỗi tải nhật ký kiểm tra.</td></tr>`;
    }
}

async function loadSystemSettings() {
    try {
        const res = await fetch('/api/system');
        if (!res.ok) return;
        const data = await res.json();
        AppState.systemInfo = data;

        document.getElementById('lan-full-url').textContent = data.lan_address || 'http://localhost:8000';
        document.getElementById('host-name-val').textContent = data.host_name || 'LEADER-PC';
        document.getElementById('db-size-val').textContent = `${data.db_size_kb || 120} KB`;
    } catch (e) {
        console.warn('Lỗi tải thông tin hệ thống:', e);
    }
}

function copyLanAddress() {
    const url = document.getElementById('lan-full-url')?.textContent || '';
    if (navigator.clipboard && url) {
        navigator.clipboard.writeText(url).then(() => {
            showAlert('Đã sao chép địa chỉ máy chủ LAN vào clipboard!', 'success');
        });
    } else {
        showAlert('Địa chỉ máy chủ LAN: ' + url, 'info');
    }
}

// ==========================================================================
// 8. DATA IMPORT PIPELINE CONTROLLER
// ==========================================================================
function onPipelineFileChange(input) {
    if (input.files && input.files[0]) {
        const f = input.files[0];
        document.getElementById('drop-zone-filename').innerHTML = `<strong>${escapeHtml(f.name)}</strong> (${(f.size / 1024).toFixed(1)} KB)`;
        document.getElementById('pipeline-preview-card').classList.add('hidden');
        document.getElementById('btn-pipeline-commit').disabled = true;
    } else {
        document.getElementById('drop-zone-filename').textContent = 'Kéo thả tệp vào đây hoặc bấm để chọn tệp từ máy tính';
    }
}

async function handlePipelinePreview() {
    const fileInput = document.getElementById('pipeline-file-input');
    if (!fileInput.files || !fileInput.files[0]) {
        showAlert('Vui lòng chọn tệp dữ liệu trước khi xem trước (Preview).', 'warning');
        return;
    }

    const file = fileInput.files[0];
    const dataType = document.getElementById('pipeline-data-type').value;

    const btn = document.getElementById('btn-pipeline-preview');
    btn.disabled = true;
    btn.textContent = '⏳ Đang phân tích schema & OCR...';

    // Update stepper
    document.getElementById('step-1').classList.add('active');
    document.getElementById('step-2').classList.add('active');
    document.getElementById('step-3').classList.add('active');
    document.getElementById('step-4').classList.add('active');

    const body = new FormData();
    body.append('file', file);

    try {
        const res = await fetch(`/upload/preview?data_type=${encodeURIComponent(dataType)}`, {
            method: 'POST',
            body: body
        });
        const data = await res.json();

        if (!res.ok) {
            showAlert(data.detail || 'Lỗi phân tích tệp', 'error');
            return;
        }

        renderPipelinePreview(data);
        showAlert(`Đã trích xuất và phân tích thành công ${data.so_dong_doc} bản ghi.`, 'success');
    } catch (err) {
        showAlert('Lỗi phân tích upload: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🔍 Bước 1: Xem trước & Phân tích Schema Mapping';
    }
}

function renderPipelinePreview(data) {
    const card = document.getElementById('pipeline-preview-card');
    card.classList.remove('hidden');

    const canCommit = data.can_commit;
    const commitBtn = document.getElementById('btn-pipeline-commit');
    commitBtn.disabled = !canCommit;

    const pill = document.getElementById('pipeline-validation-pill');
    pill.className = `badge-status-pill ${canCommit ? 'YES' : 'NO'}`;
    pill.textContent = canCommit ? `✓ Hợp lệ để Commit (${data.so_dong_doc} dòng)` : '✕ Thiếu trường bắt buộc';

    // Validation Report Box
    const reportBox = document.getElementById('pipeline-validation-report');
    let warningsHtml = '';
    if (data.warnings && data.warnings.length > 0) {
        warningsHtml = `
            <div style="background:#fffbeb;border:1px solid #fde68a;color:#92400e;padding:12px;border-radius:6px;font-size:13px;line-height:1.5;">
                <strong>⚠️ Báo cáo kiểm tra cấu trúc (Validation Report):</strong>
                <ul style="margin-left:20px;margin-top:6px;">
                    ${data.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
                </ul>
            </div>`;
    } else {
        warningsHtml = `
            <div style="background:#ecfdf5;border:1px solid #a7f3d0;color:#065f46;padding:12px;border-radius:6px;font-size:13px;">
                ✓ <strong>Xác thực hoàn hảo:</strong> Tất cả các trường nghiệp vụ bắt buộc đều được ánh xạ chính xác với độ tin cậy cao.
            </div>`;
    }
    reportBox.innerHTML = warningsHtml;

    // Schema Mapping Table
    const tbody = document.getElementById('pipeline-mapping-tbody');
    tbody.innerHTML = (data.mapping || []).map(m => {
        const conf = Math.round((m.confidence || 0) * 100);
        return `
            <tr>
                <td><strong>${escapeHtml(m.original_text)}</strong></td>
                <td><code>${escapeHtml(m.label)}</code></td>
                <td><span class="match-score-badge ${conf >= 90 ? 'high' : ''}">${conf}%</span></td>
                <td><span class="meta-tag">${escapeHtml(m.source || 'ai')}</span></td>
                <td>${m.accepted ? '<span style="color:var(--yes-green-dark);font-weight:600;">✓ Accepted</span>' : '<span style="color:var(--no-red-dark);font-weight:600;">✕ Review</span>'}</td>
            </tr>`;
    }).join('');

    // Sample Table
    const headers = data.headers || [];
    document.getElementById('pipeline-sample-thead').innerHTML = '<tr>' + headers.map(h => `<th>${escapeHtml(h)}</th>`).join('') + '</tr>';
    document.getElementById('pipeline-sample-tbody').innerHTML = (data.preview_rows || []).map(r => {
        return '<tr>' + headers.map(h => `<td>${escapeHtml(r[h] ?? '')}</td>`).join('') + '</tr>';
    }).join('');
}

async function handlePipelineCommit(e) {
    e.preventDefault();
    const fileInput = document.getElementById('pipeline-file-input');
    if (!fileInput.files || !fileInput.files[0]) {
        showAlert('Vui lòng chọn tệp.', 'warning');
        return;
    }

    const file = fileInput.files[0];
    const dataType = document.getElementById('pipeline-data-type').value;
    const mode = document.getElementById('pipeline-upload-mode').value;

    const btn = document.getElementById('btn-pipeline-commit');
    btn.disabled = true;
    btn.textContent = '⏳ Đang thực thi SQLite Transaction...';

    // Stepper to step 7
    document.getElementById('step-5').classList.add('active');
    document.getElementById('step-6').classList.add('active');
    document.getElementById('step-7').classList.add('active');

    const body = new FormData();
    body.append('file', file);

    try {
        const res = await fetch(`/upload/commit?data_type=${encodeURIComponent(dataType)}&mode=${encodeURIComponent(mode)}`, {
            method: 'POST',
            body: body
        });
        const data = await res.json();

        if (!res.ok) {
            showAlert(data.detail?.message || data.detail || 'Lỗi khi commit dữ liệu', 'error');
            return;
        }

        showAlert(
            `Thành công: Đã nạp ${data.so_dong_import} bản ghi (${data.data_type}) theo chế độ ${data.mode}. (Bỏ qua: ${data.so_dong_trung}, Lỗi: ${data.so_dong_loi})`,
            'success'
        );

        // Reset file input
        fileInput.value = '';
        document.getElementById('drop-zone-filename').textContent = 'Kéo thả tệp vào đây hoặc bấm để chọn tệp từ máy tính';
        document.getElementById('pipeline-preview-card').classList.add('hidden');
        btn.disabled = true;

        // Refresh stats
        loadDashboardStats();

        // Redirect to search view
        setTimeout(() => navigateTo('search'), 1200);
    } catch (err) {
        showAlert('Lỗi commit transaction: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Bước 2: Xác nhận ghi SQLite (Transaction Safe)';
    }
}

// ==========================================================================
// 9. MODAL & UTILITY FUNCTIONS
// ==========================================================================
function closeModal() {
    document.getElementById('modal-entity')?.classList.add('hidden');
}

function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// ==========================================================================
// 10. INITIALIZATION
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
    // Initial data load
    loadDashboardStats();
    loadRecentSearches();
    loadSystemSettings();

    // Setup initial search test value
    const mainInput = document.getElementById('main-search-input');
    if (mainInput) {
        mainInput.value = 'NV001';
        doSearchNow(1);
    }
});
