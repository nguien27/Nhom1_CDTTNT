// ==========================================================================
// PAYROLLCHECK - CLIENT APPLICATION
// Modular Service Abstractions, State Machine, Transparent Audit
// ==========================================================================

// Global Application State
const AppState = {
    currentView: 'dashboard',
    userRole: null,
    currentUser: null,
    searchQuery: '',
    searchScope: 'ALL',
    searchPage: 1,
    searchPageSize: 20,
    searchTotalPages: 1,
    searchResults: [],
    selectedResultIndex: -1,
    stats: {},
    systemInfo: {},
    exceptions: [],
    rules: [],

    // Input pipeline state
    pipeline: {
        state: 'INPUT_EMPTY', // INPUT_EMPTY, PROCESSING, MAPPING_READY, MAPPING_EDITED, VALIDATING, VALIDATION_FAILED, VALIDATION_PASSED, COMMITTING, COMMIT_SUCCESS, COMMIT_FAILED
        inputMethod: 'FILE', // 'FILE' or 'RAW_STRING'
        filename: '',
        metadata: {},
        dataType: 'NHAN_VIEN_KHONG_KET_QUA',
        mode: 'APPEND',
        headers: [],
        rows: [],
        previewRows: [],
        mappingItems: [],
        schemaOptions: [],
        duplicates: [],
        missingFields: [],
        validationResult: null,
        commitResult: null,
        firstImportedKey: ''
    }
};

// Breadcrumbs
const BREADCRUMB_MAP = {
    dashboard: 'Tổng quan',
    search: 'Tra cứu đối tượng',
    employees: 'Cá nhân (Nhân sự)',
    upload: 'Nhập dữ liệu',
    database: 'Cơ sở dữ liệu (Database Explorer)',
    rules: 'Quy tắc nghiệp vụ (Business Rules)',
    exceptions: 'Ngoại lệ cá nhân (Overrides)',
    history: 'Lịch sử tra cứu & Audit Trail',
    system: 'Hệ thống & Mạng LAN'
};

// ==========================================================================
// 1. SERVICE LAYER ABSTRACTIONS (Prompt Section 37)
// ==========================================================================
function normalizeAnalysisResponse(data, inputMethod, filename = '') {
    const rows = data.rows || [];

    return {
        ok: data.status === 'ok' || data.ok === true,
        input_method: inputMethod,
        filename: filename || data.metadata?.filename ||
            (inputMethod === 'RAW_STRING' ? 'Văn bản dán trực tiếp' : 'upload'),
        metadata: data.metadata || {},
        data_type: data.data_type || 'NHAN_VIEN_KHONG_KET_QUA',

        headers: data.headers || [],
        so_dong: rows.length,
        rows: rows,
        preview_rows: data.preview_rows || [],

        mapping_items: data.mapping_items || [],
        duplicates: data.duplicates || [],
        missing_fields: data.missing_fields || [],
        pending_confirmation: data.pending_confirmation || [],
        schema_options: data.schema_options || [],

        requires_confirmation: Boolean(data.requires_confirmation),
        confirmation_items:
            data.confirmation_items ||
            data.pending_confirmation ||
            [],

        upstream_validation: data.upstream_validation || null,

        pipeline_modules: {
            reader: 'GD3-01',
            information_mapping: 'GD3-02',
            backend: 'GD3-04'
        }
    };
}

const InputService = {
    async analyzeFile(file, dataType) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('data_type', dataType || 'NHAN_VIEN_KHONG_KET_QUA');

        const res = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                'Lỗi khi phân tích tệp đầu vào.'
            );
        }

        return normalizeAnalysisResponse(data, 'FILE', file.name);
    },

    async analyzeText(rawText, dataType) {
        const res = await fetch('/input', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw_text: rawText, data_type: dataType || 'NHAN_VIEN_KHONG_KET_QUA' })
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                'Lỗi khi phân tích chuỗi văn bản.'
            );
        }

        return normalizeAnalysisResponse(
            data,
            'RAW_STRING',
            'Văn bản dán trực tiếp'
        );
    }
};

const ValidationService = {
    async validate(rows, mappingItems, dataType) {
        const res = await fetch('/validation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rows: rows,
                mapping_items: mappingItems,
                data_type: dataType
            })
        });

        const data = await res.json();

        // GĐ3-04 dùng HTTP 422 cho Validation FAIL.
        // Đây vẫn là kết quả validation hợp lệ để UI hiển thị.
        if (!res.ok && res.status !== 422) {
            throw new Error(
                data.detail ||
                data.message ||
                'Lỗi khi thực hiện kiểm tra dữ liệu.'
            );
        }

        return data;
    }
};

const CommitService = {
    async commit(rows, mappingItems, dataType, mode) {
        const res = await fetch('/commit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rows: rows,
                mapping_items: mappingItems,
                data_type: dataType,
                mode: mode
            })
        });

        const data = await res.json();

        if (!res.ok) {
            const msg =
                data.message ||
                data.detail?.message ||
                data.detail ||
                'Lỗi khi commit cơ sở dữ liệu.';

            throw new Error(
                typeof msg === 'string'
                    ? msg
                    : JSON.stringify(msg)
            );
        }

        // GĐ3-04 wrap kết quả CommitService trong field "commit".
        return data.commit || data;
    }
};

// ==========================================================================
// 2. NAVIGATION & ROUTING
// ==========================================================================
function navigateTo(viewId) {
    const adminViews = new Set(['dashboard', 'upload', 'employees', 'rules', 'exceptions', 'database', 'history', 'system']);
    if (AppState.userRole === 'USER' && adminViews.has(viewId)) {
        viewId = 'search';
    }

    AppState.currentView = viewId;

    document.querySelectorAll('.sidebar-nav .nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewId);
    });

    document.querySelectorAll('.page-view').forEach(panel => {
        panel.classList.toggle('hidden', panel.id !== `view-${viewId}`);
    });

    const crumbEl = document.getElementById('current-breadcrumb');
    if (crumbEl) {
        crumbEl.textContent = BREADCRUMB_MAP[viewId] || viewId;
    }

    if (viewId === 'dashboard') {
        loadDashboardStats();
        loadRecentSearches();
    } else if (viewId === 'employees') {
        loadEmployeesTable(1);

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

    closeSidebar();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function setSidebarState(open) {
    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!sidebar) return;

    sidebar.classList.toggle('open', Boolean(open));
    overlay?.classList.toggle('open', Boolean(open));
    document.body.classList.toggle('sidebar-mobile-open', Boolean(open));

    const toggleButton = document.querySelector('.menu-toggle-btn');
    toggleButton?.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function toggleSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    if (!sidebar) return;
    setSidebarState(!sidebar.classList.contains('open'));
}

function closeSidebar() {
    setSidebarState(false);
}

window.addEventListener('resize', () => {
    if (window.innerWidth > 1024) {
        closeSidebar();
    }
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeSidebar();
    }
});

function applyAuthenticatedUser(user) {
    AppState.currentUser = user || null;
    AppState.userRole = user?.role || null;

    const role = AppState.userRole;
    const badge = document.getElementById('role-badge');
    if (badge) {
        badge.textContent = role || '--';
        badge.className = `badge-role ${(role || 'user').toLowerCase()}`;
    }

    document.querySelectorAll('.admin-only').forEach(el => {
        el.style.display = (role === 'ADMIN') ? '' : 'none';
    });

    const username = user?.username || 'Chưa đăng nhập';
    const sidebarUsername = document.getElementById('sidebar-username');
    if (sidebarUsername) sidebarUsername.textContent = username;

    const nameEl = document.getElementById('current-user-name');
    const roleEl = document.getElementById('current-user-role');
    const avatarEl = document.getElementById('current-user-avatar');
    if (nameEl) nameEl.textContent = username;
    if (roleEl) roleEl.textContent = role === 'ADMIN' ? 'Quản trị viên' : (role === 'USER' ? 'Nhân viên tra cứu' : '--');
    if (avatarEl) avatarEl.textContent = username.substring(0, 2).toUpperCase() || '--';
}

function authErrorMessage(data, fallback) {
    const detail = data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail?.message) return detail.message;
    return data?.message || fallback;
}

function showLoginScreen(message = '') {
    document.getElementById('password-change-screen')?.classList.add('hidden');
    document.getElementById('auth-login-screen')?.classList.remove('hidden');
    const errorEl = document.getElementById('login-error');
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.classList.toggle('hidden', !message);
    }
}

function showPasswordChangeScreen(user) {
    applyAuthenticatedUser(user);
    document.getElementById('auth-login-screen')?.classList.add('hidden');
    document.getElementById('password-change-screen')?.classList.remove('hidden');
}

function enterAuthenticatedApp(user) {
    applyAuthenticatedUser(user);
    document.getElementById('auth-login-screen')?.classList.add('hidden');
    document.getElementById('password-change-screen')?.classList.add('hidden');

    if (user.role === 'ADMIN') {
        navigateTo('dashboard');
    } else {
        navigateTo('search');
    }
}

async function bootstrapAuth() {
    try {
        const res = await fetch('/api/auth/me');
        if (!res.ok) {
            applyAuthenticatedUser(null);
            showLoginScreen();
            return;
        }
        const data = await res.json();
        const user = data.user;
        if (user?.must_change_password) {
            showPasswordChangeScreen(user);
        } else {
            enterAuthenticatedApp(user);
        }
    } catch (e) {
        applyAuthenticatedUser(null);
        showLoginScreen('Không thể kết nối máy chủ.');
    }
}

async function handleLogin(event) {
    event?.preventDefault();
    const username = document.getElementById('login-username')?.value?.trim() || '';
    const password = document.getElementById('login-password')?.value || '';
    const errorEl = document.getElementById('login-error');
    if (errorEl) errorEl.classList.add('hidden');

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Đăng nhập thất bại.'));

        document.getElementById('login-password').value = '';
        if (data.user?.must_change_password) {
            showPasswordChangeScreen(data.user);
        } else {
            enterAuthenticatedApp(data.user);
        }
    } catch (e) {
        if (errorEl) {
            errorEl.textContent = e.message;
            errorEl.classList.remove('hidden');
        }
    }
}

async function handleFirstPasswordChange(event) {
    event?.preventDefault();
    const currentPassword = document.getElementById('current-password')?.value || '';
    const newPassword = document.getElementById('new-password')?.value || '';
    const confirmPassword = document.getElementById('confirm-password')?.value || '';
    const errorEl = document.getElementById('password-change-error');

    if (newPassword !== confirmPassword) {
        errorEl.textContent = 'Mật khẩu nhập lại không khớp.';
        errorEl.classList.remove('hidden');
        return;
    }

    try {
        const res = await fetch('/api/auth/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể đổi mật khẩu.'));

        document.getElementById('current-password').value = '';
        document.getElementById('new-password').value = '';
        document.getElementById('confirm-password').value = '';
        errorEl.classList.add('hidden');
        enterAuthenticatedApp(data.user);
        showAlert('Đổi mật khẩu thành công.', 'success');
    } catch (e) {
        errorEl.textContent = e.message;
        errorEl.classList.remove('hidden');
    }
}

async function handleLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } finally {
        AppState.searchResults = [];
        AppState.selectedResultIndex = -1;
        applyAuthenticatedUser(null);
        document.getElementById('login-password') && (document.getElementById('login-password').value = '');
        showLoginScreen();
    }
}

function showAlert(message, type = 'info') {
    const alertEl = document.getElementById('global-alert');
    const msgEl = document.getElementById('alert-message');
    if (!alertEl || !msgEl) return;

    alertEl.className = `global-alert ${type}`;
    msgEl.textContent = message;
    alertEl.classList.remove('hidden');

    clearTimeout(window._alertTimer);
    window._alertTimer = setTimeout(() => closeAlert(), 7000);
}

function closeAlert() {
    const alertEl = document.getElementById('global-alert');
    if (alertEl) alertEl.classList.add('hidden');
}

// ==========================================================================
// 3. INPUT CONTROLLER & STEPPER
// ==========================================================================
const STEP_SYMBOLS = ['1', '2', '3', '4', '5', '6'];
function updateWorkflowStepper(stepIndex, isError = false) {
    for (let i = 1; i <= 6; i++) {
        const node = document.getElementById(`wnode-${i}`);
        if (!node) continue;
        node.classList.remove('active', 'completed', 'error');
        const numEl = node.querySelector('.step-num');
        if (i < stepIndex) {
            node.classList.add('completed');
            if (numEl) numEl.textContent = String(i);
        } else if (i === stepIndex) {
            if (isError) {
                node.classList.add('error');
                if (numEl) numEl.textContent = String(i);
            } else {
                node.classList.add('active');
                if (numEl) numEl.textContent = STEP_SYMBOLS[i - 1];
            }
        } else {
            if (numEl) numEl.textContent = STEP_SYMBOLS[i - 1];
        }
    }
}

const INPUT_TYPE_OPTIONS = {
    FILE: [
        ['NHAN_VIEN_KHONG_KET_QUA', 'Hồ sơ nhân viên / CBCS'],
        ['BUSINESS_RULE', 'Quy tắc nghiệp vụ'],
        ['NHAN_VIEN_CO_KET_QUA', 'Ngoại lệ cá nhân']
    ],
    RAW_STRING: [
        ['NHAN_VIEN_KHONG_KET_QUA', 'Hồ sơ nhân viên / CBCS']
    ]
};

const INPUT_TYPE_INFO = {
    NHAN_VIEN_KHONG_KET_QUA: {
        helper: 'Hồ sơ nhân viên: bắt buộc Mã nhân viên, Họ tên và Tên đơn vị. Email không bắt buộc nhưng cần có để tự tạo tài khoản USER.',
        extensions: ['csv', 'xlsx', 'docx', 'pdf', 'txt'],
        formats: 'CSV / XLSX / DOCX / PDF / TXT',
        paste: '<span class="text-muted">Ví dụ:</span><br><code>Mã nhân viên: NV001</code><br><code>Họ tên: Nguyễn Văn A</code><br><code>Tên đơn vị: Cục Đào tạo</code><br><code>Email: nguyenvana@example.com</code>'
    },
    BUSINESS_RULE: {
        helper: 'Quy tắc nghiệp vụ: file cần có Tên quy tắc, Tên đơn vị áp dụng, Kết quả YES/NO và Căn cứ. Mã quy tắc có thể để trống để hệ thống tự sinh.',
        extensions: ['csv', 'xlsx', 'txt'],
        formats: 'CSV / XLSX / TXT',
        paste: ''
    },
    NHAN_VIEN_CO_KET_QUA: {
        helper: 'Ngoại lệ cá nhân: file cần có Mã nhân viên đã tồn tại, Kết quả YES/NO và Căn cứ. Có thể thêm thủ công tại màn Ngoại lệ cá nhân.',
        extensions: ['csv', 'xlsx', 'txt'],
        formats: 'CSV / XLSX / TXT',
        paste: ''
    }
};

function refreshDataTypeOptions() {
    const select = document.getElementById('pipeline-data-type');
    if (!select) return;
    const method = AppState.pipeline.inputMethod === 'RAW_STRING' ? 'RAW_STRING' : 'FILE';
    const options = INPUT_TYPE_OPTIONS[method] || INPUT_TYPE_OPTIONS.FILE;
    const current = select.value || AppState.pipeline.dataType;
    select.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
    select.value = options.some(([value]) => value === current) ? current : options[0][0];
    AppState.pipeline.dataType = select.value;
    updateInputTypeHelp();
}

function updateInputTypeHelp() {
    const dataType = document.getElementById('pipeline-data-type')?.value || AppState.pipeline.dataType;
    const info = INPUT_TYPE_INFO[dataType] || INPUT_TYPE_INFO.NHAN_VIEN_KHONG_KET_QUA;
    const helper = document.getElementById('pipeline-data-type-helper');
    if (helper) helper.textContent = info.helper;

    const input = document.getElementById('pipeline-file-input');
    if (input) input.accept = info.extensions.map(ext => `.${ext}`).join(',');
    const subtitle = document.getElementById('file-format-subtitle');
    if (subtitle) subtitle.textContent = info.formats;
    const hint = document.getElementById('drop-zone-format-hint');
    if (hint) hint.innerHTML = `Định dạng được hỗ trợ: <strong>${info.formats.replaceAll(' / ', ', ')}</strong>`;
    const example = document.getElementById('paste-example-box');
    if (example && info.paste) example.innerHTML = info.paste;
    onCommitModeChange();
}

function onCommitModeChange() {
    const mode = document.getElementById('pipeline-upload-mode')?.value || 'APPEND';
    document.getElementById('replace-mode-warning')?.classList.toggle('hidden', mode !== 'REPLACE');
}

function switchInputTab(tab) {
    AppState.pipeline.inputMethod = (tab === 'file') ? 'FILE' : 'RAW_STRING';

    document.getElementById('tab-btn-file')?.classList.toggle('active', tab === 'file');
    document.getElementById('tab-btn-paste')?.classList.toggle('active', tab === 'paste');
    document.getElementById('tab-content-file')?.classList.toggle('hidden', tab !== 'file');
    document.getElementById('tab-content-paste')?.classList.toggle('hidden', tab !== 'paste');
    refreshDataTypeOptions();
}

function onDataTypeChange() {
    const dt = document.getElementById('pipeline-data-type')?.value || 'NHAN_VIEN_KHONG_KET_QUA';
    AppState.pipeline.dataType = dt;
    updateInputTypeHelp();

    // Mapping cũ thuộc schema trước đó không còn hợp lệ. Giữ nguyên file/text
    // nhưng yêu cầu người dùng bấm Phân tích lại với loại dữ liệu mới.
    if (AppState.pipeline.headers.length > 0) {
        AppState.pipeline.headers = [];
        AppState.pipeline.rows = [];
        AppState.pipeline.previewRows = [];
        AppState.pipeline.mappingItems = [];
        AppState.pipeline.schemaOptions = [];
        AppState.pipeline.missingFields = [];
        AppState.pipeline.duplicates = [];
        AppState.pipeline.state = 'INPUT_EMPTY';
        document.getElementById('mapping-preview-section')?.classList.add('hidden');
        updateWorkflowStepper(1);
        showAlert('Đã đổi loại dữ liệu. Hãy phân tích lại dữ liệu đầu vào.', 'info');
    }
}

function onInputFileSelected(input) {
    const fileErrorBox = document.getElementById('file-error-container');
    fileErrorBox.classList.add('hidden');
    document.getElementById('pdf-text-alert')?.classList.add('hidden');

    if (input.files && input.files[0]) {
        const f = input.files[0];
        const ext = f.name.split('.').pop().toLowerCase();
        const dataType = document.getElementById('pipeline-data-type')?.value || 'NHAN_VIEN_KHONG_KET_QUA';
        const validExts = (INPUT_TYPE_INFO[dataType] || INPUT_TYPE_INFO.NHAN_VIEN_KHONG_KET_QUA).extensions;

        if (!validExts.includes(ext)) {
            showFileError(`Định dạng tệp ".${ext}" không phù hợp với loại dữ liệu đang chọn. Hỗ trợ: ${validExts.join(', ').toUpperCase()}.`, 'UNSUPPORTED_FILE_TYPE');
            input.value = '';
            document.getElementById('drop-zone').classList.remove('hidden');
            document.getElementById('file-selected-card').classList.add('hidden');
            return;
        }

        if (f.size === 0) {
            showFileError('Tệp rỗng (0 bytes). Vui lòng chọn tệp chứa dữ liệu hợp lệ.', 'EMPTY_FILE');
            input.value = '';
            document.getElementById('drop-zone').classList.remove('hidden');
            document.getElementById('file-selected-card').classList.add('hidden');
            return;
        }

        // Calculate formatted size
        const sizeStr = (f.size >= 1024 * 1024)
            ? (f.size / (1024 * 1024)).toFixed(1) + ' MB'
            : (f.size / 1024).toFixed(1) + ' KB';

        // Update File Selected Card
        document.getElementById('selected-file-name').textContent = f.name;
        document.getElementById('selected-file-type').textContent = ext.toUpperCase();
        document.getElementById('selected-file-size').textContent = sizeStr;


        // Show File Selected Card, Hide Drop Zone
        document.getElementById('drop-zone').classList.add('hidden');
        document.getElementById('file-selected-card').classList.remove('hidden');
        document.getElementById('btn-process-file').disabled = false;
        AppState.pipeline.filename = f.name;
        AppState.pipeline.selectedFile = f;
    } else {
        removeSelectedFile();
    }
}

function removeSelectedFile() {
    const input = document.getElementById('pipeline-file-input');
    if (input) input.value = '';
    document.getElementById('drop-zone').classList.remove('hidden');
    document.getElementById('file-selected-card').classList.add('hidden');
    document.getElementById('file-error-container').classList.add('hidden');
    AppState.pipeline.selectedFile = null;
    AppState.pipeline.filename = '';
}

function onPasteTextInput(textarea) {
    const val = (textarea.value || '').trim();
    const btn = document.getElementById('btn-process-paste');
    const emptyMsg = document.getElementById('raw-paste-empty-msg');
    if (!val) {
        btn.disabled = true;
        emptyMsg?.classList.remove('hidden');
    } else {
        btn.disabled = false;
        emptyMsg?.classList.add('hidden');
    }
}

function clearPasteText() {
    const txt = document.getElementById('raw-paste-textarea');
    if (txt) {
        txt.value = '';
        onPasteTextInput(txt);
    }
}

function showFileError(friendlyMsg, techMsg) {
    const box = document.getElementById('file-error-container');
    const msg = document.getElementById('file-error-friendly');
    const tech = document.getElementById('file-error-tech');
    box.classList.remove('hidden');
    msg.textContent = friendlyMsg;
    tech.textContent = techMsg || friendlyMsg;
    tech.classList.add('hidden');
}

function toggleTechDetails() {
    const tech = document.getElementById('file-error-tech');
    tech.classList.toggle('hidden');
}

async function simulateProgressAnimation(callback) {
    const box = document.getElementById('pipeline-progress-box');
    box.classList.remove('hidden');
    const isFile = AppState.pipeline.inputMethod === 'FILE';
    const title = document.getElementById('pipeline-progress-title');
    if (title) title.textContent = isFile ? 'Đang xử lý file' : 'Đang xử lý dữ liệu nhập trực tiếp';
    const received = document.getElementById('pstep-1-label');
    if (received) received.textContent = isFile ? 'Đã nhận file' : 'Đã nhận dữ liệu';

    const steps = ['pstep-1', 'pstep-2', 'pstep-3', 'pstep-4', 'pstep-5'];
    steps.forEach(s => {
        const el = document.getElementById(s);
        if (el) {
            el.className = 'p-check-item pending';
            const ico = el.querySelector('.p-ico');

        }
    });

    const setStepState = (id, state) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = `p-check-item ${state}`;
        const ico = el.querySelector('.p-ico');

    };

    setStepState('pstep-1', 'done');
    setStepState('pstep-2', 'in-progress');
    await new Promise(r => setTimeout(r, 120));

    setStepState('pstep-2', 'done');
    setStepState('pstep-3', 'in-progress');
    await new Promise(r => setTimeout(r, 120));

    setStepState('pstep-3', 'done');
    setStepState('pstep-4', 'in-progress');
    await new Promise(r => setTimeout(r, 120));

    try {
        await callback();
        setStepState('pstep-4', 'done');
        setStepState('pstep-5', 'done');
        await new Promise(r => setTimeout(r, 150));
    } finally {
        box.classList.add('hidden');
    }
}

// ==========================================================================
// 4. MAPPING & PREVIEW CONTROLLER
// ==========================================================================
async function handleAnalyzeFile() {
    const input = document.getElementById('pipeline-file-input');
    if (!input.files || !input.files[0]) {
        showAlert('Vui lòng chọn tệp dữ liệu trước khi phân tích.', 'warning');
        return;
    }

    const file = input.files[0];
    const dataType = document.getElementById('pipeline-data-type').value;
    AppState.pipeline.dataType = dataType;

    await simulateProgressAnimation(async () => {
        try {
            const data = await InputService.analyzeFile(file, dataType);
            applyInputDataToState(data);
            renderMappingPreview(data);

            const meta = data.metadata || {};
            if (meta.file_type === 'pdf' && meta.pdf_mode !== 'scan') {
                document.getElementById('pdf-text-alert')?.classList.remove('hidden');
            } else {
                document.getElementById('pdf-text-alert')?.classList.add('hidden');
            }

            showAlert(`Đã phân tích thành công ${data.so_dong} dòng dữ liệu từ ${data.filename}.`, 'success');
        } catch (err) {
            showFileError('Không thể đọc file này. Vui lòng kiểm tra file hoặc chọn một file khác.', err.message);
            showAlert('Lỗi: ' + err.message, 'error');
            throw err;
        }
    });
}

async function handleAnalyzeText() {
    const txt = document.getElementById('raw-paste-textarea');
    const rawText = (txt?.value || '').trim();
    if (!rawText) {
        showAlert('Vui lòng nhập hoặc dán nội dung văn bản.', 'warning');
        return;
    }

    const dataType = document.getElementById('pipeline-data-type').value;
    AppState.pipeline.dataType = dataType;

    await simulateProgressAnimation(async () => {
        try {
            const data = await InputService.analyzeText(rawText, dataType);
            applyInputDataToState(data);
            renderMappingPreview(data);
            showAlert(`Đã phân tích thành công ${data.so_dong} dòng dữ liệu văn bản.`, 'success');
        } catch (err) {
            showAlert('Lỗi: ' + err.message, 'error');
            throw err;
        }
    });
}

function applyInputDataToState(data) {
    AppState.pipeline.headers = data.headers || [];
    AppState.pipeline.rows = data.rows || [];
    AppState.pipeline.previewRows = data.preview_rows || [];
    AppState.pipeline.mappingItems = (data.mapping_items || []).map(item => ({
        ...item,
        original_target_field: item.target_field,
        original_confirmed_by_user: false
    }));
    AppState.pipeline.schemaOptions = data.schema_options || [];
    AppState.pipeline.duplicates = data.duplicates || [];
    AppState.pipeline.missingFields = data.missing_fields || [];
    AppState.pipeline.metadata = data.metadata || {};
    AppState.pipeline.dataType = data.data_type || document.getElementById('pipeline-data-type')?.value || AppState.pipeline.dataType;
    AppState.pipeline.state = 'MAPPING_READY';

    const firstRow = (data.rows && data.rows.length > 0) ? data.rows[0] : {};
    const codeKeys = ['Mã nhân viên', 'Mã NV', 'MSNV', 'Mã CBCS', 'ma_nhan_vien'];
    let keyVal = '';
    for (const key of codeKeys) {
        if (firstRow[key]) {
            keyVal = String(firstRow[key]);
            break;
        }
    }
    if (!keyVal && Object.values(firstRow).length > 0) {
        keyVal = String(Object.values(firstRow)[0]);
    }
    AppState.pipeline.firstImportedKey = keyVal;
    document.getElementById('ind-source-name').textContent = data.filename;
    document.getElementById('ind-method').textContent = data.input_method;
    document.getElementById('ind-type').textContent = (data.metadata?.file_type || 'TEXT').toUpperCase();
    document.getElementById('ind-id').textContent = data.metadata?.input_id || 'INP-AUTO';
    document.getElementById('ind-time').textContent = data.metadata?.timestamp || new Date().toLocaleString();

    recalculateDuplicatesAndMissing();
    updateWorkflowStepper(2);
}

function renderMappingPreview() {
    const previewSection = document.getElementById('mapping-preview-section');
    previewSection.classList.remove('hidden');

    document.getElementById('validation-running-box').classList.add('hidden');
    document.getElementById('validation-fail-banner').classList.add('hidden');
    document.getElementById('validation-pass-banner').classList.add('hidden');
    document.getElementById('commit-success-card').classList.add('hidden');
    document.getElementById('commit-fail-card').classList.add('hidden');
    document.getElementById('validation-action-card').classList.remove('hidden');
    document.getElementById('validation-cta-header')?.classList.remove('hidden');
    document.getElementById('btn-run-validation').disabled = false;

    renderMappingTableRows();
    checkAndRenderAlertBanners();
    renderDataPreviewTable();
    updateWorkflowStepper(3);
    previewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function mappingNeedsConfirmation(item) {
    if (!item || !item.target_field || item.target_field === 'IGNORE' || item.target_field === 'OTHER') return false;
    const ratio = Number(item.confidence_ratio ?? ((Number(item.confidence || 0) > 1) ? Number(item.confidence || 0) / 100 : Number(item.confidence || 0)));
    return Boolean(item.requires_confirmation) || ratio < 0.85;
}

function mappingIsConfirmed(item) {
    return Boolean(item?.confirmed_by_user) || Boolean(item?.is_edited);
}

function updateMappingSummary() {
    const items = AppState.pipeline.mappingItems || [];
    const missing = AppState.pipeline.missingFields || [];
    const dups = AppState.pipeline.duplicates || [];

    const totalFields = items.length;
    const mappedFields = items.filter(it => it.target_field && it.target_field !== 'IGNORE' && it.target_field !== 'OTHER').length;
    const lowConfFields = items.filter(it => mappingNeedsConfirmation(it) && !mappingIsConfirmed(it)).length;
    const unknownFields = items.filter(it => !it.target_field || it.target_field === 'OTHER').length;
    const dataErrors = AppState.pipeline.validationResult?.summary?.invalid_records || 0;

    document.getElementById('sum-total-fields').textContent = totalFields;
    document.getElementById('sum-mapped-fields').textContent = mappedFields;
    document.getElementById('sum-low-conf').textContent = lowConfFields;
    document.getElementById('sum-unknown-fields').textContent = unknownFields;
    document.getElementById('sum-missing-req').textContent = missing.length;
    document.getElementById('sum-dup-fields').textContent = dups.length;
    document.getElementById('sum-data-errors').textContent = dataErrors;
}

function renderMappingTableRows() {
    const tbody = document.getElementById('mapping-table-body');
    const items = AppState.pipeline.mappingItems || [];
    const schemaOpts = AppState.pipeline.schemaOptions || [];
    const duplicateTargets = new Set((AppState.pipeline.duplicates || []).map(d => d.target_field));

    tbody.innerHTML = items.map((item, idx) => {
        const conf = Number(item.confidence || 0);
        const confLevel = item.confidence_level || (conf >= 85 ? 'HIGH' : conf >= 60 ? 'MEDIUM' : conf >= 40 ? 'LOW' : 'VERY_LOW');
        const isDuplicate = duplicateTargets.has(item.target_field) && item.target_field !== 'IGNORE';
        const needsConfirmation = mappingNeedsConfirmation(item);
        const confirmed = mappingIsConfirmed(item);

        let badgeClass = 'high';
        let confIcon = '';
        if (confLevel === 'MEDIUM') {
            badgeClass = 'medium';
            confIcon = '';
        } else if (confLevel === 'LOW' || confLevel === 'VERY_LOW') {
            badgeClass = 'low';
            confIcon = '';
        }

        const optionsHtml = schemaOpts.map(opt => {
            const selected = (opt.field === item.target_field) ? 'selected' : '';
            return `<option value="${escapeHtml(opt.field)}" ${selected}>${escapeHtml(opt.label)}</option>`;
        }).join('');

        const editedBadge = item.is_edited ? '<span class="badge-edited">Đã chỉnh sửa</span>' : '';
        const confirmedBadge = confirmed && needsConfirmation ? '<span class="badge-edited">Đã xác nhận</span>' : '';
        const rowHighlightClass = isDuplicate ? 'row-duplicate-highlight' : '';
        const selectClass = isDuplicate ? 'mapping-select duplicate' : (item.is_edited ? 'mapping-select edited' : 'mapping-select');

        let statusBadge = '<span style="color:var(--yes-green-dark);font-weight:600;">Hợp lệ</span>';
        if (item.target_field === 'IGNORE') {
            statusBadge = '<span style="color:var(--slate-500);font-weight:600;">Bỏ qua</span>';
        } else if (item.status === 'UNKNOWN') {
            statusBadge = '<span style="color:var(--slate-500);font-weight:600;">Chưa xác định</span>';
        } else if (isDuplicate) {
            statusBadge = '<span style="color:var(--no-red-dark);font-weight:600;">Trùng lặp</span>';
        } else if (needsConfirmation && !confirmed) {
            statusBadge = '<span style="color:var(--no-red-dark);font-weight:600;" title="Confidence dưới 85% phải được xác nhận hoặc chỉnh sửa.">Cần xác nhận</span>';
        } else if (needsConfirmation && confirmed) {
            statusBadge = '<span style="color:var(--yes-green-dark);font-weight:600;">Đã xác nhận</span>';
        }

        const confirmButton = (needsConfirmation && !confirmed && item.target_field !== 'IGNORE')
            ? `<button class="btn btn-sm btn-primary" onclick="confirmMapping(${idx})">Xác nhận</button>`
            : '';

        return `
            <tr class="${rowHighlightClass}" id="map-row-${idx}">
                <td><strong>${escapeHtml(item.source_column)}</strong></td>
                <td>
                    <select class="${selectClass}" onchange="onMappingDropdownChanged(${idx}, this.value)">
                        ${optionsHtml}
                    </select>
                    ${editedBadge} ${confirmedBadge}
                </td>
                <td>
                    ${item.target_field === 'IGNORE'
                        ? '<span class="match-score-badge" title="Trường nguồn này không được sử dụng trong schema hiện tại.">Không áp dụng</span>'
                        : `<span class="match-score-badge ${badgeClass}" title="Độ tin cậy của ánh xạ tự động. Dưới 85% phải được xác nhận.">${confIcon} ${conf.toFixed(1)}% (${escapeHtml(item.confidence_label || confLevel)})</span>`}
                </td>
                <td><code style="background:var(--slate-100);padding:2px 6px;border-radius:4px;font-size:12px;">${escapeHtml(item.sample_value || '—')}</code></td>
                <td>${statusBadge}</td>
                <td style="display:flex;gap:6px;flex-wrap:wrap;">${confirmButton}<button class="btn btn-sm btn-outline" onclick="resetSingleMapping(${idx})">Đặt lại</button></td>
            </tr>`;
    }).join('');

    updateMappingSummary();
}

function invalidateValidationAfterMappingChange() {
    AppState.pipeline.validationResult = null;
    document.getElementById('validation-pass-banner')?.classList.add('hidden');
    document.getElementById('validation-fail-banner')?.classList.add('hidden');
    document.getElementById('btn-run-validation').disabled = false;
    updateWorkflowStepper(2);
}

function onMappingDropdownChanged(idx, newTarget) {
    const item = AppState.pipeline.mappingItems[idx];
    if (!item) return;

    item.target_field = newTarget;
    item.is_edited = true;
    item.confirmed_by_user = true;
    AppState.pipeline.state = 'MAPPING_EDITED';

    recalculateDuplicatesAndMissing();
    checkAndRenderAlertBanners();
    renderMappingTableRows();
    renderDataPreviewTable();
    invalidateValidationAfterMappingChange();
}

function confirmMapping(idx) {
    const item = AppState.pipeline.mappingItems[idx];
    if (!item || item.target_field === 'IGNORE') return;
    item.confirmed_by_user = true;
    AppState.pipeline.state = 'MAPPING_EDITED';
    renderMappingTableRows();
    checkAndRenderAlertBanners();
    invalidateValidationAfterMappingChange();
    showAlert(`Đã xác nhận mapping "${item.source_column}" - ${item.target_field}.`, 'success');
}

function resetSingleMapping(idx) {
    const item = AppState.pipeline.mappingItems[idx];
    if (!item) return;
    item.target_field = item.original_target_field || 'IGNORE';
    item.is_edited = false;
    item.confirmed_by_user = Boolean(item.original_confirmed_by_user);
    recalculateDuplicatesAndMissing();
    renderMappingTableRows();
    checkAndRenderAlertBanners();
    renderDataPreviewTable();
    invalidateValidationAfterMappingChange();
}

function recalculateDuplicatesAndMissing() {
    const items = AppState.pipeline.mappingItems || [];
    const targetCounts = {};
    items.forEach(it => {
        const tgt = it.target_field;
        if (tgt && tgt !== 'IGNORE' && tgt !== 'OTHER') {
            targetCounts[tgt] = (targetCounts[tgt] || []).concat(it.source_column);
        }
    });

    AppState.pipeline.duplicates = Object.entries(targetCounts)
        .filter(([, columns]) => columns.length > 1)
        .map(([target, columns]) => ({
            target_field: target,
            columns,
            message: `Các cột [${columns.join(', ')}] đều được gán vào trường '${target}'.`
        }));

    const required = (AppState.pipeline.schemaOptions || [])
        .filter(option => option.required)
        .map(option => option.field);
    const mappedTargets = new Set(items.map(i => i.target_field).filter(t => t && t !== 'IGNORE' && t !== 'OTHER'));
    AppState.pipeline.missingFields = required.filter(field => !mappedTargets.has(field));
    updateMappingSummary();
}

function checkAndRenderAlertBanners() {
    const dupBanner = document.getElementById('banner-duplicate-mapping');
    const dupMsg = document.getElementById('banner-duplicate-msg');
    const missBanner = document.getElementById('banner-missing-required');
    const missMsg = document.getElementById('banner-missing-msg');
    const confBanner = document.getElementById('banner-low-confidence');
    const confMsg = document.getElementById('banner-low-confidence-msg');

    if (AppState.pipeline.duplicates.length > 0) {
        dupBanner?.classList.remove('hidden');
        if (dupMsg) dupMsg.textContent = AppState.pipeline.duplicates.map(d => d.message).join(' | ');
    } else {
        dupBanner?.classList.add('hidden');
    }

    if (AppState.pipeline.missingFields.length > 0) {
        missBanner?.classList.remove('hidden');
        if (missMsg) missMsg.textContent = `Thiếu trường bắt buộc: [${AppState.pipeline.missingFields.join(', ')}].`;
    } else {
        missBanner?.classList.add('hidden');
    }

    const pending = (AppState.pipeline.mappingItems || []).filter(item => mappingNeedsConfirmation(item) && !mappingIsConfirmed(item));
    if (pending.length > 0) {
        confBanner?.classList.remove('hidden');
        if (confMsg) confMsg.textContent = `${pending.length} mapping có confidence dưới 85%. Hãy bấm Xác nhận hoặc chỉnh sửa dropdown trước khi KIỂM TRA.`;
    } else {
        confBanner?.classList.add('hidden');
    }
}

function renderDataPreviewTable() {
    const thead = document.getElementById('data-preview-thead');
    const tbody = document.getElementById('data-preview-tbody');
    const rows = AppState.pipeline.previewRows || [];
    const items = AppState.pipeline.mappingItems || [];

    document.getElementById('preview-rows-counter').textContent = `Đang hiển thị ${Math.min(rows.length, 15)} / ${AppState.pipeline.rows.length} bản ghi`;

    // Headers with both SOURCE and SYSTEM MAPPED FIELD
    thead.innerHTML = '<tr>' + items.map(it => {
        const sysLabel = (it.target_field === 'IGNORE') ? '<em style="color:var(--slate-400);">(Bỏ qua)</em>' : `<code>${escapeHtml(it.target_field)}</code>`;
        return `
            <th>
                <div>${escapeHtml(it.source_column)}</div>
                <div style="font-size:11px;font-weight:normal;margin-top:2px;">${sysLabel}</div>
            </th>`;
    }).join('') + '</tr>';

    tbody.innerHTML = rows.map(r => {
        return '<tr>' + items.map(it => {
            const val = r[it.source_column] ?? '';
            return `<td>${escapeHtml(val)}</td>`;
        }).join('') + '</tr>';
    }).join('');
}

function scrollToMappingTable() {
    document.getElementById('mapping-table')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ==========================================================================
// 5. VALIDATION CONTROLLER (Prompt Section 31 - 37)
// ==========================================================================
async function handleRunValidation() {
    const btn = document.getElementById('btn-run-validation');
    btn.disabled = true;
    updateWorkflowStepper(4); // Bước 4: Kiểm tra dữ liệu

    const runningBox = document.getElementById('validation-running-box');
    runningBox.classList.remove('hidden');

    const failBanner = document.getElementById('validation-fail-banner');
    const passBanner = document.getElementById('validation-pass-banner');
    failBanner.classList.add('hidden');
    passBanner.classList.add('hidden');

    const checklistGrid = document.getElementById('validation-checklist-items');
    checklistGrid.innerHTML = `
        <div class="check-item"><span class="spinner-sm"></span> Required fields</div>
        <div class="check-item"><span class="spinner-sm"></span> Schema conformance</div>
        <div class="check-item"><span class="spinner-sm"></span> Mapping completeness</div>
        <div class="check-item"><span class="spinner-sm"></span> Duplicate mapping</div>
        <div class="check-item"><span class="spinner-sm"></span> Data format</div>
        <div class="check-item"><span class="spinner-sm"></span> Data type</div>
        <div class="check-item"><span class="spinner-sm"></span> Data consistency</div>
        <div class="check-item"><span class="spinner-sm"></span> Referential integrity</div>
    `;

    try {
        await new Promise(r => setTimeout(r, 250));

        const result = await ValidationService.validate(
            AppState.pipeline.rows,
            AppState.pipeline.mappingItems,
            AppState.pipeline.dataType
        );
        AppState.pipeline.validationResult = result;
        updateMappingSummary();

        // Render detailed checklist
        checklistGrid.innerHTML = (result.checklist || []).map(ch => {
            const cls = ch.passed ? 'passed' : 'failed';
            return `<div class="check-item ${cls}"><div>${escapeHtml(ch.name)}: <small class="text-muted">${escapeHtml(ch.detail)}</small></div></div>`;
        }).join('');

        if (result.status === 'PASS' && result.can_commit) {
            AppState.pipeline.state = 'VALIDATION_PASSED';
            updateWorkflowStepper(4);

            passBanner.classList.remove('hidden');
            document.getElementById('val-pass-rec-count').textContent = (result.summary?.total_records || 0).toLocaleString();
            document.getElementById('val-pass-warn-count').textContent = result.warning_count || 0;

            showAlert('Kiểm tra dữ liệu đạt chuẩn (Validation PASS)! Đã sẵn sàng Commit.', 'success');
            passBanner.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
            AppState.pipeline.state = 'VALIDATION_FAILED';
            updateWorkflowStepper(4, true);

            failBanner.classList.remove('hidden');
            document.getElementById('val-fail-err-count').textContent = result.error_count || 0;
            document.getElementById('val-fail-warn-count').textContent = result.warning_count || 0;

            const errList = document.getElementById('validation-errors-list');
            errList.innerHTML = (result.errors || []).map((err, i) => {
                return `
                    <div class="error-item-clickable" onclick="highlightErrorRow(${err.row_idx}, '${escapeHtml(err.field)}')">
                        <div><strong>${escapeHtml(err.field || 'Lỗi')}:</strong> ${escapeHtml(err.message)}</div>
                    </div>`;
            }).join('');

            showAlert(`Kiểm tra không đạt (Validation FAIL) với ${result.error_count} lỗi. Commit đã bị khóa.`, 'error');
            failBanner.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    } catch (err) {
        showAlert('Lỗi khi chạy validation: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

function highlightErrorRow(rowIdx, fieldName) {
    showAlert(`Lỗi tại trường "${fieldName}" (Dòng ${rowIdx}). Hãy kiểm tra lại ánh xạ cột.`, 'warning');
    const items = AppState.pipeline.mappingItems || [];
    const idx = items.findIndex(it => it.source_column === fieldName || it.target_field === fieldName);
    if (idx !== -1) {
        const rowEl = document.getElementById(`map-row-${idx}`);
        if (rowEl) {
            rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
            rowEl.classList.add('row-duplicate-highlight');
            setTimeout(() => {
                if (!AppState.pipeline.duplicates.some(d => d.columns.includes(items[idx].source_column))) {
                    rowEl.classList.remove('row-duplicate-highlight');
                }
            }, 3000);
            return;
        }
    }
    scrollToMappingTable();
}

// ==========================================================================
// 6. COMMIT CONTROLLER (Prompt Section 38 - 42)
// ==========================================================================
function openCommitConfirmModal() {
    if (AppState.pipeline.state !== 'VALIDATION_PASSED') {
        showAlert('Dữ liệu chưa vượt qua kiểm tra (Validation). Không thể Commit.', 'warning');
        return;
    }

    const modal = document.getElementById('modal-commit-confirm');
    document.getElementById('modal-summary-source').textContent = AppState.pipeline.filename || 'Văn bản trực tiếp';
    document.getElementById('modal-summary-records').textContent = `${(AppState.pipeline.rows.length || 0).toLocaleString()} bản ghi`;
    document.getElementById('modal-summary-warnings').textContent = `${AppState.pipeline.validationResult?.warning_count || 0} cảnh báo`;
    document.getElementById('modal-summary-mode').textContent = document.getElementById('pipeline-upload-mode').value;

    modal.classList.remove('hidden');
}

function closeCommitModal() {
    document.getElementById('modal-commit-confirm')?.classList.add('hidden');
}

async function executeCommitNow() {
    closeCommitModal();

    const btn = document.getElementById('btn-open-commit-modal');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Đang Commit dữ liệu...';
    }
    updateWorkflowStepper(5); // Bước 5 Commit

    const mode = document.getElementById('pipeline-upload-mode').value;

    try {
        const result = await CommitService.commit(
            AppState.pipeline.rows,
            AppState.pipeline.mappingItems,
            AppState.pipeline.dataType,
            mode
        );
        AppState.pipeline.commitResult = result;
        AppState.pipeline.state = 'COMMIT_SUCCESS';

        updateWorkflowStepper(6); // Bước 6 Completed

        // Ẩn phần thao tác validation nhưng giữ card cha để kết quả Commit vẫn hiển thị.
        document.getElementById('validation-pass-banner').classList.add('hidden');
        document.getElementById('validation-fail-banner').classList.add('hidden');
        document.getElementById('validation-running-box').classList.add('hidden');
        document.getElementById('validation-cta-header')?.classList.add('hidden');
        document.getElementById('validation-action-card').classList.remove('hidden');

        // Show success card
        const successCard = document.getElementById('commit-success-card');
        successCard.classList.remove('hidden');
        document.getElementById('commit-success-details').textContent =
            `${result.so_dong_import.toLocaleString()} bản ghi đã được cập nhật vào hệ thống.`;
        document.getElementById('commit-success-time').textContent = `Timestamp: ${result.timestamp}`;

        const cId = result.batch_id || result.commit_id || 'BATCH-UNKNOWN';
        const totalProc = (result.so_dong_import || 0) + (result.so_dong_trung || 0) + (result.so_dong_loi || 0);
        document.getElementById('commit-meta-id').innerHTML = `Commit ID: <strong>${cId}</strong>`;
        document.getElementById('commit-meta-processed').innerHTML = `Đã xử lý: <strong>${totalProc}</strong>`;
        document.getElementById('commit-meta-inserted').innerHTML = `Đã thêm mới: <strong>${result.so_dong_import}</strong>`;
        document.getElementById('commit-meta-skipped').innerHTML = `Bỏ qua trùng: <strong>${result.so_dong_trung}</strong>`;

        showAlert('Commit dữ liệu thành công!', 'success');
        successCard.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Refresh stats in background
        loadDashboardStats();
    } catch (err) {
        AppState.pipeline.state = 'COMMIT_FAILED';
        const failCard = document.getElementById('commit-fail-card');
        failCard.classList.remove('hidden');
        document.getElementById('commit-fail-reason').textContent = err.message || 'Giao dịch đã được khôi phục nguyên vẹn (Rollback).';
        const errId = 'ERR-' + Math.random().toString(36).substring(2, 7).toUpperCase();
        document.getElementById('commit-fail-error-id').textContent = `Error ID: ${errId}`;
        showAlert('Commit thất bại: ' + err.message, 'error');
        failCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'COMMIT DỮ LIỆU';
        }
    }
}

function handlePostCommitSearch() {
    navigateTo('search');
    let q = AppState.pipeline.firstImportedKey || '';
    if (!q && AppState.pipeline.rows && AppState.pipeline.rows.length > 0) {
        const first = AppState.pipeline.rows[0];
        q = first.ma_nhan_vien || first.MSNV || first['Mã nhân viên'] || first['Mã CBCS'] || first.ho_ten || Object.values(first)[0] || '';
    }
    if (q) {
        const input = document.getElementById('dashboard-quick-input') || document.getElementById('header-search-input');
        // Let's set search input in view-search
        const searchInput = document.querySelector('#view-search input[type="text"]') || document.getElementById('dashboard-quick-input');
        if (searchInput) {
            searchInput.value = q;
        }
        quickFillAndSearch(q);
    }
}

function resetInputWorkflow() {
    AppState.pipeline.state = 'INPUT_EMPTY';
    AppState.pipeline.headers = [];
    AppState.pipeline.rows = [];
    AppState.pipeline.previewRows = [];
    AppState.pipeline.mappingItems = [];

    document.getElementById('mapping-preview-section').classList.add('hidden');
    document.getElementById('commit-success-card').classList.add('hidden');
    document.getElementById('commit-fail-card').classList.add('hidden');
    document.getElementById('validation-action-card').classList.remove('hidden');
    document.getElementById('validation-cta-header')?.classList.remove('hidden');
    document.getElementById('pipeline-file-input').value = '';
    document.getElementById('drop-zone-filename').textContent = 'Kéo và thả file vào đây';
    document.getElementById('btn-process-file').disabled = true;
    clearPasteText();

    updateWorkflowStepper(1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ==========================================================================
// 7. DASHBOARD & SEARCH CONTROLLERS
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
                    <td><code>${escapeHtml(h.rule || 'N/A')}</code></td>
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
        showAlert('Vui lòng nhập từ khóa tra cứu.', 'warning');
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

function setSearchFilter(scope) {
    AppState.searchScope = scope;
    document.querySelectorAll('.search-tab-btn').forEach(btn => btn.classList.remove('active'));
    if (scope === 'ALL') document.getElementById('stab-all')?.classList.add('active');
    if (scope === 'CA_NHAN') document.getElementById('stab-canhan')?.classList.add('active');
    if (scope === 'DON_VI') document.getElementById('stab-donvi')?.classList.add('active');
}

// ==========================================================================
// ADAPTER KẾT QUẢ SEARCH
// Chuẩn hóa contract kết quả cho giao diện
// ==========================================================================

function normalizeSearchItem(item) {
    const isEmployee =
        item.loai_doi_tuong === 'NHAN_VIEN';

    const rawScore = Number(
        item.do_khop ?? 0
    );

    const scorePercent =
        rawScore <= 1
            ? rawScore * 100
            : rawScore;

    const doiTuong = isEmployee
        ? {
            id: item.id,
            ma_nhan_vien:
                item.ma_nhan_vien ||
                item.id_doi_tuong ||
                '',

            ho_ten:
                item.ho_ten ||
                '',

            ma_don_vi:
                item.ma_don_vi ||
                '',

            ten_don_vi:
                item.ten_don_vi ||
                item.don_vi ||
                '',

            don_vi:
                item.don_vi ||
                item.ten_don_vi ||
                '',

            chuc_vu:
                item.chuc_vu ||
                '',

            email:
                item.email ||
                ''
        }
        : {
            id: item.id,

            ma_don_vi:
                item.ma_don_vi ||
                item.id_doi_tuong ||
                '',

            ten_don_vi:
                item.ten_don_vi ||
                '',

            loai_don_vi:
                item.loai_don_vi ||
                ''
        };

    return {
        ...item,

        ten_hien_thi:
            item.ten_hien_thi ||
            (
                isEmployee
                    ? item.ho_ten
                    : item.ten_don_vi
            ) ||
            item.id_doi_tuong ||
            '',

        doi_tuong:
            item.doi_tuong ||
            doiTuong,

        trang_thai_tra_luong:
            item.trang_thai_tra_luong ||
            item.business_status ||
            {
                ket_qua: 'CHUA_XAC_DINH',
                ma_quy_tac: null,
                can_cu:
                    'Chưa có quy tắc áp dụng.'
            },

        do_khop:
            scorePercent
    };
}

function normalizeSearchResponse(data) {
    const rawItems =
        data.ket_qua ||
        data.data ||
        [];

    const items =
        rawItems.map(normalizeSearchItem);

    return {
        ...data,

        ket_qua: items,
        data: items,

        tong_ket_qua:
            data.tong_ket_qua ??
            data.pagination?.total ??
            items.length,

        total_pages:
            data.total_pages ??
            data.pagination?.total_pages ??
            1
    };
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
                <h3>Đang tra cứu dữ liệu...</h3>
                <p>Rule Engine đang phân giải điều kiện chi trả lương theo thứ tự ưu tiên.</p>
            </div>`;
    }

    try {
        const fetchByKind = async (kind) => {
            const url = `/search?q=${encodeURIComponent(q)}`
                + `&kind=${encodeURIComponent(kind)}`
                + `&page=${page}`
                + `&limit=${AppState.searchPageSize}`;

            const response = await fetch(url);
            const payload = await response.json();

            if (!response.ok) {
                throw new Error(
                    payload.detail
                    || payload.message
                    || 'Lỗi khi tra cứu'
                );
            }

            return normalizeSearchResponse(payload);
        };

        let data;

        if (AppState.searchScope === 'ALL') {
            const [employeeData, unitData] = await Promise.all([
                fetchByKind('employee'),
                fetchByKind('unit')
            ]);

            const employeeItems = employeeData.ket_qua || [];
            const unitItems = unitData.ket_qua || [];

            data = {
                ket_qua: employeeItems.concat(unitItems),
                data: employeeItems.concat(unitItems),
                tong_ket_qua:
                    (employeeData.tong_ket_qua || 0)
                    + (unitData.tong_ket_qua || 0),
                total_pages: Math.max(
                    employeeData.total_pages || 1,
                    unitData.total_pages || 1
                )
            };
        } else if (AppState.searchScope === 'DON_VI') {
            data = await fetchByKind('unit');
        } else {
            data = await fetchByKind('employee');
        }

        const items = data.ket_qua || [];

        AppState.searchResults = append ? AppState.searchResults.concat(items) : items;
        AppState.searchTotalPages = data.total_pages || 1;

        document.getElementById('search-results-total').textContent = (data.tong_ket_qua || items.length).toLocaleString();

        const ambAlert = document.getElementById('ambiguity-alert');
        if (items.length > 1) {
            ambAlert?.classList.remove('hidden');
        } else {
            ambAlert?.classList.add('hidden');
        }

        if (AppState.searchResults.length === 0) {
            container.innerHTML = `
                <div class="empty-state-card">
                    <h3>Không tìm thấy đối tượng phù hợp</h3>
                    <p>Không có kết quả nào khớp với từ khóa "<strong>${escapeHtml(q)}</strong>".</p>
                </div>`;
            renderEmptyDetailPane();
            updateSearchPaginationUI(0);
            return;
        }

        container.innerHTML = AppState.searchResults.map((item, idx) => {
            const isSelected = (idx === AppState.selectedResultIndex || (idx === 0 && AppState.selectedResultIndex === -1));
            const status = item.trang_thai_tra_luong?.ket_qua || 'CHUA_XAC_DINH';
            const badgeHtml = renderStatusBadge(status);
            const subTitle = item.loai_doi_tuong === 'NHAN_VIEN'
                ? `MSNV: ${item.doi_tuong?.ma_nhan_vien || '—'} | Đơn vị: ${item.doi_tuong?.don_vi || item.doi_tuong?.ten_don_vi || '—'}`
                : `Mã ĐV: ${item.doi_tuong?.ma_don_vi || '—'} | Loại: ${item.doi_tuong?.loai_don_vi || 'Phòng ban'}`;

            return `
                <div class="result-card ${isSelected ? 'selected' : ''}" onclick="selectSearchResult(${idx})">
                    <div class="result-card-header">
                        <span class="result-name">${escapeHtml(item.ten_hien_thi)}</span>
                        ${badgeHtml}
                    </div>
                    <div class="result-meta">${escapeHtml(subTitle)}</div>
                    <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:11.5px;color:var(--slate-400);">
                        <span>Khớp: <strong>${Math.round(item.do_khop || 100)}%</strong> (${escapeHtml(item.loai_khop || 'EXACT')})</span>
                        <span>Rule: <code>${escapeHtml(item.trang_thai_tra_luong?.ma_quy_tac || 'N/A')}</code></span>
                    </div>
                </div>`;
        }).join('');

        updateSearchPaginationUI(data.tong_ket_qua || items.length);

        if (items.length > 0 && AppState.selectedResultIndex === -1) {
            selectSearchResult(0);
        }
    } catch (e) {
        showAlert('Lỗi kết nối máy chủ khi tra cứu: ' + e.message, 'error');
    }
}

async function selectSearchResult(index) {
    AppState.selectedResultIndex = index;

    document.querySelectorAll('.result-card').forEach((card, idx) => {
        card.classList.toggle(
            'selected',
            idx === index
        );
    });

    const item = AppState.searchResults[index];

    if (!item) {
        return;
    }

    // Hiển thị dữ liệu tóm tắt trước.
    renderDetailPane(item);

    const isEmployee =
        item.loai_doi_tuong === 'NHAN_VIEN';

    const kind =
        isEmployee
            ? 'employee'
            : 'unit';

    const identifier =
        isEmployee
            ? (
                item.doi_tuong?.ma_nhan_vien ||
                item.ma_nhan_vien ||
                item.id_doi_tuong
            )
            : (
                item.doi_tuong?.ma_don_vi ||
                item.ma_don_vi ||
                item.id_doi_tuong
            );

    if (!identifier) {
        return;
    }

    try {
        const res = await fetch(
            `/details/${kind}/${encodeURIComponent(identifier)}`
        );

        if (!res.ok) {
            return;
        }

        const detail = await res.json();

        const fullData =
            detail.data || {};

        const fullItem = {
            ...item,

            doi_tuong: {
                ...(item.doi_tuong || {}),
                ...fullData,

                ten_don_vi:
                    fullData.ten_don_vi_thuc ||
                    fullData.ten_don_vi ||
                    item.doi_tuong?.ten_don_vi ||
                    '',

                don_vi:
                    fullData.ten_don_vi_thuc ||
                    fullData.ten_don_vi ||
                    item.doi_tuong?.don_vi ||
                    ''
            },

            trang_thai_tra_luong:
                detail.business_status ||
                item.trang_thai_tra_luong
        };

        AppState.searchResults[index] =
            fullItem;

        renderDetailPane(
            fullItem
        );

    } catch (err) {
        console.warn(
            'Không thể tải hồ sơ chi tiết:',
            err
        );
    }
}

function renderDetailPane(item) {
    const pane = document.getElementById('detail-pane-container');
    if (!pane) return;

    const statusObj = item.trang_thai_tra_luong || {};
    const status = statusObj.ket_qua || 'CHUA_XAC_DINH';
    const isEmployee = item.loai_doi_tuong === 'NHAN_VIEN';
    const d = item.doi_tuong || {};

    let statusHeaderHtml = '';
    if (status === 'YES') {
        statusHeaderHtml = `
            <div style="background:var(--yes-green-bg);border:1px solid var(--yes-green-border);border-radius:var(--radius-md);padding:18px;margin-bottom:18px;">
                <div style="font-size:18px;font-weight:800;color:var(--yes-green-dark);display:flex;align-items:center;gap:8px;">
                    THUỘC DIỆN ĐƯỢC TRẢ LƯƠNG (YES)
                </div>
                <div style="font-size:13px;color:var(--slate-600);margin-top:4px;">
                    Đối tượng đủ điều kiện chi trả lương theo quy tắc nghiệp vụ có hiệu lực.
                </div>
            </div>`;
    } else if (status === 'NO') {
        statusHeaderHtml = `
            <div style="background:var(--no-red-bg);border:1px solid var(--no-red-border);border-radius:var(--radius-md);padding:18px;margin-bottom:18px;">
                <div style="font-size:18px;font-weight:800;color:var(--no-red-dark);display:flex;align-items:center;gap:8px;">
                    KHÔNG THUỘC DIỆN ĐƯỢC TRẢ LƯƠNG (NO)
                </div>
                <div style="font-size:13px;color:var(--slate-600);margin-top:4px;">
                    Đối tượng không thuộc diện chi trả theo quy tắc hoặc nằm trong diện tạm hoãn/loại trừ.
                </div>
            </div>`;
    } else {
        statusHeaderHtml = `
            <div style="background:var(--undef-amber-bg);border:1px solid var(--undef-amber-border);border-radius:var(--radius-md);padding:18px;margin-bottom:18px;">
                <div style="font-size:18px;font-weight:800;color:var(--undef-amber-dark);display:flex;align-items:center;gap:8px;">
                    CHƯA XÁC ĐỊNH (CHUA_XAC_DINH)
                </div>
                <div style="font-size:13px;color:var(--slate-600);margin-top:4px;">
                    Chưa có quy tắc phù hợp hoặc thiếu thông tin định danh. Cần kiểm tra bổ sung.
                </div>
            </div>`;
    }

    const infoRowsHtml = isEmployee ? `
        <div class="summary-line"><span class="s-label">MSNV:</span> <code>${escapeHtml(d.ma_nhan_vien)}</code></div>
        <div class="summary-line"><span class="s-label">Họ và tên:</span> <strong>${escapeHtml(d.ho_ten)}</strong></div>
        <div class="summary-line"><span class="s-label">Đơn vị công tác:</span> ${escapeHtml(d.don_vi || d.ten_don_vi || '—')}</div>
        <div class="summary-line"><span class="s-label">Chức vụ:</span> ${escapeHtml(d.chuc_vu || '—')}</div>
        <div class="summary-line"><span class="s-label">Email:</span> ${escapeHtml(d.email || '—')}</div>
    ` : `
        <div class="summary-line"><span class="s-label">Mã đơn vị:</span> <code>${escapeHtml(d.ma_don_vi)}</code></div>
        <div class="summary-line"><span class="s-label">Tên đơn vị:</span> <strong>${escapeHtml(d.ten_don_vi)}</strong></div>
        <div class="summary-line"><span class="s-label">Loại đơn vị:</span> ${escapeHtml(d.loai_don_vi || 'Phòng ban')}</div>
    `;

    const isMockBadge = statusObj.la_mock ? '<span class="badge-role user" style="background:#fef3c7;color:#b45309;">MOCK RULE</span>' : '';

    pane.innerHTML = `
        <div class="card" style="padding:20px;">
            <div class="card-header-flex" style="margin-bottom:16px;">
                <h3>Hồ sơ Đối tượng Chi tiết</h3>
                ${isMockBadge}
            </div>
            ${statusHeaderHtml}
            <div class="commit-summary-box" style="margin-bottom:18px;">
                ${infoRowsHtml}
            </div>
            <div style="background:var(--slate-50);border:1px solid var(--slate-200);border-radius:var(--radius-sm);padding:14px;">
                <h4 style="font-size:13.5px;color:var(--slate-700);margin-bottom:8px;">Căn cứ Nghiệp vụ / Pháp lý (Rule Engine)</h4>
                <div style="font-size:13px;line-height:1.5;color:var(--slate-800);">
                    <strong>Căn cứ:</strong> ${escapeHtml(statusObj.can_cu || 'Không tìm thấy quy tắc phù hợp')}
                </div>
                <div style="margin-top:6px;font-size:12px;color:var(--slate-500);">
                    Mã quy tắc: <code>${escapeHtml(statusObj.ma_quy_tac || 'N/A')}</code> | Nguồn: <span class="meta-tag">${escapeHtml(statusObj.nguon_quy_tac || 'SYSTEM')}</span>
                </div>
            </div>
        </div>`;
}

function renderEmptyDetailPane() {
    const pane = document.getElementById('detail-pane-container');
    if (pane) {
        pane.innerHTML = `
            <div class="empty-state-card">
                <h3>Chi tiết đối tượng & Trạng thái</h3>
                <p>Chọn một kết quả bên danh sách để xem hồ sơ, quy tắc áp dụng và căn cứ chi trả lương.</p>
            </div>`;
    }
}

function renderStatusBadge(status) {
    if (status === 'YES') {
        return '<span class="result-badge badge-yes">ĐƯỢC TRẢ LƯƠNG (YES)</span>';
    } else if (status === 'NO') {
        return '<span class="result-badge badge-no">KHÔNG ĐƯỢC TRẢ (NO)</span>';
    } else {
        return '<span class="result-badge badge-undef">? CHƯA XÁC ĐỊNH</span>';
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

    if (AppState.searchScope === 'ALL') {
        showAlert(
            'Hãy chọn Nhân viên hoặc Đơn vị trước khi export.',
            'warning'
        );
        return;
    }

    const kind =
        AppState.searchScope === 'DON_VI'
            ? 'unit'
            : 'employee';

    window.location.href = `/export?q=${encodeURIComponent(q)}`
        + `&kind=${encodeURIComponent(kind)}`
        + `&format=${encodeURIComponent(format)}`;
}

// ==========================================================================
// 8. EMPLOYEES & UNITS DIRECTORIES
// ==========================================================================
async function loadEmployeesTable(page = 1, search = '') {
    const tbody = document.getElementById('employees-table-body');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4">Đang tải dữ liệu nhân sự...</td></tr>`;

    try {
        const query = search ? `&search=${encodeURIComponent(search)}` : '';
        const res = await fetch(`/api/employees?page=${page}&limit=20${query}`);
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể tải danh sách nhân sự.'));
        const emps = data.employees || [];

        if (emps.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Không có nhân sự nào phù hợp.</td></tr>`;
            return;
        }

        tbody.innerHTML = emps.map(e => {
            const st = e.trang_thai_tra_luong?.ket_qua || 'CHUA_XAC_DINH';
            const active = e.is_active !== 0 && e.is_active !== false;
            const codeArg = encodeURIComponent(e.ma_nhan_vien || '');
            return `
                <tr>
                    <td><code>${escapeHtml(e.ma_nhan_vien)}</code></td>
                    <td><strong>${escapeHtml(e.ho_ten)}</strong></td>
                    <td>${escapeHtml(e.don_vi || '—')}</td>
                    <td>${escapeHtml(e.chuc_vu || '—')}</td>
                    <td><small>${escapeHtml(e.email || '—')}</small></td>
                    <td><span class="status-chip ${active ? 'active' : 'inactive'}">${active ? 'Đang hoạt động' : 'Ngừng hoạt động'}</span></td>
                    <td>${renderStatusBadge(st)}</td>
                    <td>
                        <div class="table-actions">
                            <button class="btn btn-sm btn-outline" onclick="quickFillAndSearch(decodeURIComponent('${codeArg}'))">Tra cứu</button>
                            <button class="btn btn-sm btn-outline" onclick="openEmployeeEditModal('${codeArg}')">Chỉnh sửa</button>
                            <button class="btn btn-sm btn-outline" onclick="setEmployeeActive('${codeArg}', ${active ? 'false' : 'true'})">${active ? 'Ngừng hoạt động' : 'Kích hoạt'}</button>
                            <button class="btn btn-sm btn-outline btn-danger-outline" onclick="deleteEmployee('${codeArg}')">Xóa</button>
                        </div>
                    </td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">${escapeHtml(e.message || 'Lỗi khi nạp danh sách nhân sự.')}</td></tr>`;
    }
}

async function openEmployeeEditModal(encodedCode) {
    const ma = decodeURIComponent(encodedCode || '');
    try {
        const [empRes, unitRes] = await Promise.all([
            fetch(`/api/employees/${encodeURIComponent(ma)}`),
            fetch('/api/units')
        ]);
        const empData = await empRes.json();
        const unitData = await unitRes.json();
        if (!empRes.ok) throw new Error(authErrorMessage(empData, 'Không thể đọc hồ sơ nhân viên.'));
        if (!unitRes.ok) throw new Error(authErrorMessage(unitData, 'Không thể đọc danh mục đơn vị.'));

        const emp = empData.employee || {};
        document.getElementById('employee-edit-code').value = emp.ma_nhan_vien || ma;
        document.getElementById('employee-edit-name').value = emp.ho_ten || '';
        document.getElementById('employee-edit-title').value = emp.chuc_vu || '';
        document.getElementById('employee-edit-email').value = emp.email || '';

        const select = document.getElementById('employee-edit-unit');
        const units = unitData.units || [];
        select.innerHTML = units.map(u => {
            const selected = (u.ten_don_vi || '') === (emp.don_vi || emp.ten_don_vi || '') ? ' selected' : '';
            return `<option value="${escapeHtml(u.ten_don_vi || '')}"${selected}>${escapeHtml(u.ten_don_vi || '')}</option>`;
        }).join('');

        document.getElementById('modal-employee-edit').classList.remove('hidden');
    } catch (e) {
        showAlert(e.message || 'Không thể mở hồ sơ nhân viên.', 'error');
    }
}

function closeEmployeeEditModal() {
    document.getElementById('modal-employee-edit')?.classList.add('hidden');
}

async function saveEmployeeChanges() {
    const ma = document.getElementById('employee-edit-code')?.value?.trim() || '';
    const payload = {
        ho_ten: document.getElementById('employee-edit-name')?.value?.trim() || '',
        ten_don_vi: document.getElementById('employee-edit-unit')?.value || '',
        chuc_vu: document.getElementById('employee-edit-title')?.value?.trim() || '',
        email: document.getElementById('employee-edit-email')?.value?.trim() || ''
    };
    const button = document.getElementById('btn-save-employee');
    if (button) button.disabled = true;
    try {
        const res = await fetch(`/api/employees/${encodeURIComponent(ma)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể cập nhật nhân viên.'));
        closeEmployeeEditModal();
        showAlert(data.message || 'Đã cập nhật nhân viên.', 'success');
        const filter = document.getElementById('filter-emp-input')?.value || '';
        loadEmployeesTable(1, filter);
    } catch (e) {
        showAlert(e.message || 'Không thể cập nhật nhân viên.', 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

async function setEmployeeActive(encodedCode, isActive) {
    const ma = decodeURIComponent(encodedCode || '');
    const action = isActive ? 'kích hoạt lại' : 'ngừng hoạt động';
    if (!window.confirm(`Xác nhận ${action} nhân viên ${ma}?${isActive ? '' : '\nTài khoản USER liên kết sẽ không thể đăng nhập.'}`)) return;
    try {
        const res = await fetch(`/api/employees/${encodeURIComponent(ma)}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: Boolean(isActive) })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, `Không thể ${action} nhân viên.`));
        showAlert(data.message || `Đã ${action} nhân viên.`, 'success');
        const filter = document.getElementById('filter-emp-input')?.value || '';
        loadEmployeesTable(1, filter);
    } catch (e) {
        showAlert(e.message || `Không thể ${action} nhân viên.`, 'error');
    }
}

async function deleteEmployee(encodedCode) {
    const ma = decodeURIComponent(encodedCode || '');
    const confirmed = window.confirm(
        `Xóa vĩnh viễn nhân viên ${ma}?\n\nThao tác này sẽ xóa hồ sơ nhân viên, tài khoản USER và các ngoại lệ cá nhân liên quan. Không thể hoàn tác.`
    );
    if (!confirmed) return;
    try {
        const res = await fetch(`/api/employees/${encodeURIComponent(ma)}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể xóa nhân viên.'));
        showAlert(data.message || 'Đã xóa nhân viên.', 'success');
        const filter = document.getElementById('filter-emp-input')?.value || '';
        loadEmployeesTable(1, filter);
        loadExceptionsTable();
    } catch (e) {
        showAlert(e.message || 'Không thể xóa nhân viên.', 'error');
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

    tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4">Đang tải danh mục đơn vị...</td></tr>`;

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
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">Không tìm thấy đơn vị nào.</td></tr>`;
            return;
        }

        tbody.innerHTML = units.map(u => {
            const st = u.trang_thai_tra_luong?.ket_qua || 'CHUA_XAC_DINH';
            const rule = u.trang_thai_tra_luong?.ma_quy_tac || 'N/A';
            return `
                <tr>
                    <td><strong>${escapeHtml(u.ten_don_vi)}</strong></td>
                    <td><strong>${u.employee_count || 0}</strong> nhân viên</td>
                    <td>${renderStatusBadge(st)}</td>
                    <td><code>${escapeHtml(rule)}</code></td>
                    <td>
                        <button class="btn btn-sm btn-outline" onclick="quickFillAndSearch('${escapeHtml(u.ten_don_vi)}', 'DON_VI')">Xem chi tiết</button>
                    </td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">Lỗi khi tải danh mục đơn vị.</td></tr>`;
    }
}

let _debounceUnitTimer = null;
function debounceUnitFilter(val) {
    clearTimeout(_debounceUnitTimer);
    _debounceUnitTimer = setTimeout(() => loadUnitsTable(val), 350);
}

// ==========================================================================
// 9. RULES, EXCEPTIONS & AUDIT HISTORY
// ==========================================================================
function ruleStatusLabel(code) {
    const labels = {
        DANG_AP_DUNG: 'Đang áp dụng',
        NGUNG_AP_DUNG: 'Ngừng áp dụng',
        CHUA_HIEU_LUC: 'Chưa hiệu lực',
        HET_HIEU_LUC: 'Hết hiệu lực'
    };
    return labels[code] || 'Đang áp dụng';
}

async function loadRulesTable() {
    const tbody = document.getElementById('rules-table-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/rules');
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể tải quy tắc nghiệp vụ.'));
        const rules = data.rules || [];
        AppState.rules = rules;

        if (rules.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">Chưa có quy tắc nghiệp vụ nào.</td></tr>`;
            return;
        }

        tbody.innerHTML = rules.map(r => {
            const active = Number(r.dang_ap_dung) === 1;
            const statusCode = r.trang_thai || (active ? 'DANG_AP_DUNG' : 'NGUNG_AP_DUNG');
            const statusClass = statusCode === 'DANG_AP_DUNG' ? 'active' : 'inactive';
            return `
                <tr>
                    <td><code>${escapeHtml(r.ma_quy_tac || '')}</code></td>
                    <td><strong>${escapeHtml(r.ten_quy_tac || r.ma_quy_tac || '')}</strong></td>
                    <td>${escapeHtml(r.ten_don_vi || '—')}</td>
                    <td>${renderStatusBadge(r.ket_qua)}</td>
                    <td><small>${escapeHtml(r.can_cu || '—')}</small></td>
                    <td><span class="status-chip ${statusClass}">${escapeHtml(ruleStatusLabel(statusCode))}</span></td>
                    <td>
                        <div class="table-actions">
                            <button class="btn btn-sm btn-outline" onclick="openRuleModal(${Number(r.id)})">Chỉnh sửa</button>
                            <button class="btn btn-sm btn-outline" onclick="setRuleActive(${Number(r.id)}, ${active ? 'false' : 'true'})">${active ? 'Ngừng áp dụng' : 'Kích hoạt'}</button>
                            <button class="btn btn-sm btn-outline btn-danger-outline" onclick="deleteRule(${Number(r.id)})">Xóa</button>
                        </div>
                    </td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">${escapeHtml(e.message || 'Không thể tải quy tắc nghiệp vụ.')}</td></tr>`;
    }
}

async function openRuleModal(ruleId = null) {
    try {
        const unitRes = await fetch('/api/units');
        const unitData = await unitRes.json();
        if (!unitRes.ok) throw new Error(authErrorMessage(unitData, 'Không thể đọc danh mục đơn vị.'));
        const units = unitData.units || [];
        if (!units.length) throw new Error('Chưa có đơn vị. Hãy nhập đơn vị trước khi tạo quy tắc.');

        const rule = ruleId == null ? null : (AppState.rules || []).find(r => Number(r.id) === Number(ruleId));
        document.getElementById('rule-edit-id').value = rule ? String(rule.id) : '';
        document.getElementById('rule-modal-title').textContent = rule ? 'Chỉnh sửa quy tắc' : 'Thêm quy tắc';
        const code = document.getElementById('rule-code');
        code.value = rule?.ma_quy_tac || '';
        code.readOnly = Boolean(rule);
        document.getElementById('rule-name').value = rule?.ten_quy_tac || '';
        document.getElementById('rule-result').value = rule?.ket_qua || 'YES';
        document.getElementById('rule-basis').value = rule?.can_cu || '';

        const unitSelect = document.getElementById('rule-unit');
        unitSelect.innerHTML = units.map(u => {
            const name = u.ten_don_vi || '';
            const selected = rule && name === (rule.ten_don_vi || '') ? ' selected' : '';
            return `<option value="${escapeHtml(name)}"${selected}>${escapeHtml(name)}</option>`;
        }).join('');
        document.getElementById('modal-rule-edit').classList.remove('hidden');
    } catch (e) {
        showAlert(e.message || 'Không thể mở form quy tắc.', 'error');
    }
}

function closeRuleModal() {
    document.getElementById('modal-rule-edit')?.classList.add('hidden');
}

async function saveRule() {
    const id = document.getElementById('rule-edit-id')?.value || '';
    const payload = {
        ma_quy_tac: document.getElementById('rule-code')?.value?.trim() || '',
        ten_quy_tac: document.getElementById('rule-name')?.value?.trim() || '',
        ten_don_vi: document.getElementById('rule-unit')?.value || '',
        ket_qua: document.getElementById('rule-result')?.value || 'YES',
        can_cu: document.getElementById('rule-basis')?.value?.trim() || ''
    };
    const button = document.getElementById('btn-save-rule');
    if (button) button.disabled = true;
    try {
        const res = await fetch(id ? `/api/rules/${encodeURIComponent(id)}` : '/api/rules', {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể lưu quy tắc.'));
        closeRuleModal();
        showAlert(data.message || 'Đã lưu quy tắc.', 'success');
        loadRulesTable();
    } catch (e) {
        showAlert(e.message || 'Không thể lưu quy tắc.', 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

async function setRuleActive(ruleId, isActive) {
    const action = isActive ? 'kích hoạt' : 'ngừng áp dụng';
    if (!window.confirm(`Xác nhận ${action} quy tắc này?`)) return;
    try {
        const res = await fetch(`/api/rules/${encodeURIComponent(ruleId)}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: Boolean(isActive) })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, `Không thể ${action} quy tắc.`));
        showAlert(data.message || `Đã ${action} quy tắc.`, 'success');
        loadRulesTable();
    } catch (e) {
        showAlert(e.message || `Không thể ${action} quy tắc.`, 'error');
    }
}

async function deleteRule(ruleId) {
    if (!window.confirm('Xóa vĩnh viễn quy tắc này? Thao tác không thể hoàn tác.')) return;
    try {
        const res = await fetch(`/api/rules/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể xóa quy tắc.'));
        showAlert(data.message || 'Đã xóa quy tắc.', 'success');
        loadRulesTable();
    } catch (e) {
        showAlert(e.message || 'Không thể xóa quy tắc.', 'error');
    }
}

async function loadExceptionsTable() {
    const tbody = document.getElementById('exceptions-table-body');
    if (!tbody) return;

    try {
        const res = await fetch('/api/exceptions');
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể tải danh sách ngoại lệ.'));
        const exList = data.exceptions || [];
        AppState.exceptions = exList;

        if (exList.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-muted">Chưa có bản ghi ngoại lệ cá nhân nào trong hệ thống.</td></tr>`;
            return;
        }

        tbody.innerHTML = exList.map(ex => {
            const active = Number(ex.dang_ap_dung) === 1;
            const dateText = ex.ngay_hieu_luc || 'Áp dụng ngay';
            return `
                <tr>
                    <td><code>${escapeHtml(ex.ma_nhan_vien)}</code></td>
                    <td><strong>${escapeHtml(ex.ho_ten || 'Cá nhân ngoại lệ')}</strong></td>
                    <td>${escapeHtml(ex.don_vi || '—')}</td>
                    <td>${renderStatusBadge(ex.ket_qua)}</td>
                    <td><strong>${escapeHtml(ex.can_cu)}</strong></td>
                    <td><span class="meta-tag">${ex.muc_uu_tien ?? 100}</span></td>
                    <td>${escapeHtml(dateText)}</td>
                    <td><span class="status-chip ${active ? 'active' : 'inactive'}">${active ? 'Đang áp dụng' : 'Ngừng áp dụng'}</span></td>
                    <td>
                        <div class="table-actions">
                            <button class="btn btn-sm btn-outline" onclick="openExceptionModal(${Number(ex.id)})">Chỉnh sửa</button>
                            <button class="btn btn-sm btn-outline" onclick="setExceptionActive(${Number(ex.id)}, ${active ? 'false' : 'true'})">${active ? 'Ngừng áp dụng' : 'Kích hoạt'}</button>
                            <button class="btn btn-sm btn-outline btn-danger-outline" onclick="deleteException(${Number(ex.id)})">Xóa</button>
                        </div>
                    </td>
                </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-muted">${escapeHtml(e.message || 'Lỗi khi tải danh sách ngoại lệ.')}</td></tr>`;
    }
}

function openExceptionModal(exceptionId = null) {
    const modal = document.getElementById('modal-exception-edit');
    const existing = exceptionId == null
        ? null
        : (AppState.exceptions || []).find(item => Number(item.id) === Number(exceptionId));

    document.getElementById('exception-edit-id').value = existing?.id || '';
    document.getElementById('exception-modal-title').textContent = existing ? 'Chỉnh sửa ngoại lệ cá nhân' : 'Thêm ngoại lệ cá nhân';
    document.getElementById('exception-employee-code').value = existing?.ma_nhan_vien || '';
    document.getElementById('exception-result').value = existing?.ket_qua || 'YES';
    document.getElementById('exception-priority').value = existing?.muc_uu_tien ?? 100;
    document.getElementById('exception-basis').value = existing?.can_cu || '';
    document.getElementById('exception-start-date').value = existing?.ngay_hieu_luc || '';
    document.getElementById('exception-end-date').value = existing?.ngay_het_hieu_luc || '';
    document.getElementById('exception-note').value = existing?.ghi_chu || '';
    const info = document.getElementById('exception-employee-info');
    if (existing) {
        info.textContent = `${existing.ho_ten || existing.ma_nhan_vien} — ${existing.don_vi || 'Chưa có đơn vị'}`;
    } else {
        info.textContent = 'Nhập mã nhân viên đã tồn tại trong hệ thống.';
    }
    modal?.classList.remove('hidden');
}

function closeExceptionModal() {
    document.getElementById('modal-exception-edit')?.classList.add('hidden');
}

async function checkExceptionEmployee() {
    const ma = document.getElementById('exception-employee-code')?.value?.trim() || '';
    const info = document.getElementById('exception-employee-info');
    if (!ma) {
        info.textContent = 'Hãy nhập mã nhân viên.';
        return false;
    }
    try {
        const res = await fetch(`/api/employees/${encodeURIComponent(ma)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không tìm thấy nhân viên.'));
        const emp = data.employee || {};
        info.textContent = `${emp.ho_ten || ma} — ${emp.don_vi || emp.ten_don_vi || 'Chưa có đơn vị'}`;
        return true;
    } catch (e) {
        info.textContent = e.message || 'Không tìm thấy nhân viên.';
        return false;
    }
}

async function saveException() {
    const id = document.getElementById('exception-edit-id')?.value?.trim() || '';
    const payload = {
        ma_nhan_vien: document.getElementById('exception-employee-code')?.value?.trim() || '',
        ket_qua: document.getElementById('exception-result')?.value || 'YES',
        can_cu: document.getElementById('exception-basis')?.value?.trim() || '',
        muc_uu_tien: Number(document.getElementById('exception-priority')?.value || 100),
        ngay_hieu_luc: document.getElementById('exception-start-date')?.value || '',
        ngay_het_hieu_luc: document.getElementById('exception-end-date')?.value || '',
        ghi_chu: document.getElementById('exception-note')?.value?.trim() || ''
    };
    if (!payload.ma_nhan_vien || !payload.can_cu) {
        showAlert('Mã nhân viên và căn cứ ngoại lệ là bắt buộc.', 'warning');
        return;
    }

    const button = document.getElementById('btn-save-exception');
    if (button) button.disabled = true;
    try {
        const res = await fetch(id ? `/api/exceptions/${encodeURIComponent(id)}` : '/api/exceptions', {
            method: id ? 'PUT' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể lưu ngoại lệ.'));
        closeExceptionModal();
        showAlert(data.message || 'Đã lưu ngoại lệ cá nhân.', 'success');
        loadExceptionsTable();
        loadDashboardStats();
    } catch (e) {
        showAlert(e.message || 'Không thể lưu ngoại lệ.', 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

async function setExceptionActive(exceptionId, isActive) {
    const action = isActive ? 'kích hoạt lại' : 'ngừng áp dụng';
    if (!window.confirm(`Xác nhận ${action} ngoại lệ này?`)) return;
    try {
        const res = await fetch(`/api/exceptions/${exceptionId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: Boolean(isActive) })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, `Không thể ${action} ngoại lệ.`));
        showAlert(data.message || `Đã ${action} ngoại lệ.`, 'success');
        loadExceptionsTable();
        loadDashboardStats();
    } catch (e) {
        showAlert(e.message || `Không thể ${action} ngoại lệ.`, 'error');
    }
}

async function deleteException(exceptionId) {
    if (!window.confirm('Xóa vĩnh viễn ngoại lệ này? Thao tác không thể hoàn tác.')) return;
    try {
        const res = await fetch(`/api/exceptions/${exceptionId}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(authErrorMessage(data, 'Không thể xóa ngoại lệ.'));
        showAlert(data.message || 'Đã xóa ngoại lệ.', 'success');
        loadExceptionsTable();
        loadDashboardStats();
    } catch (e) {
        showAlert(e.message || 'Không thể xóa ngoại lệ.', 'error');
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
                <td><code>${escapeHtml(item.rule || 'N/A')}</code></td>
                <td><small>${escapeHtml(item.timestamp)}</small></td>
            </tr>`).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">Lỗi tải nhật ký kiểm tra.</td></tr>`;
    }
}

async function loadDbEmployeesPage(page = 1) {
    const container = document.getElementById('db-tab-content');
    if (!container) return;

    const limit = 10;
    const res = await fetch(`/api/employees?page=${page}&limit=${limit}`);
    const data = await res.json();
    if (!res.ok) {
        container.innerHTML = `<p class="text-muted">Không thể tải bảng nhân viên.</p>`;
        return;
    }

    const currentPage = Number(data.page || page || 1);
    const totalPages = Number(data.total_pages || 1);
    const startIndex = (currentPage - 1) * limit;

    container.innerHTML = `
        <h4>Bảng nhân viên (Tổng ${data.total} bản ghi)</h4>
        <div class="table-responsive" style="margin-top:10px;">
            <table class="saas-table">
                <thead><tr><th>STT</th><th>MSNV</th><th>Họ tên</th><th>Đơn vị</th><th>Chức vụ</th><th>Email</th></tr></thead>
                <tbody>${(data.employees || []).map((r, index) => `<tr><td>${startIndex + index + 1}</td><td><code>${escapeHtml(r.ma_nhan_vien)}</code></td><td>${escapeHtml(r.ho_ten)}</td><td>${escapeHtml(r.don_vi || '')}</td><td>${escapeHtml(r.chuc_vu || '')}</td><td>${escapeHtml(r.email || '')}</td></tr>`).join('')}</tbody>
            </table>
        </div>
        <div class="pagination-bar">
            <button class="btn btn-sm btn-outline" type="button" onclick="loadDbEmployeesPage(${currentPage - 1})" ${currentPage <= 1 ? 'disabled' : ''}>Trang trước</button>
            <span class="pagination-text">Trang ${currentPage} / ${totalPages}</span>
            <button class="btn btn-sm btn-outline" type="button" onclick="loadDbEmployeesPage(${currentPage + 1})" ${currentPage >= totalPages ? 'disabled' : ''}>Trang sau</button>
        </div>`;
}

async function switchDbTab(tableName) {
    document.querySelectorAll('.db-tab-btn').forEach(b => b.classList.remove('active'));
    event?.target?.classList.add('active');

    const container = document.getElementById('db-tab-content');
    container.innerHTML = `<p class="text-muted">Đang truy vấn bảng <code>${tableName}</code>...</p>`;

    if (tableName === 'nhan_vien') {
        await loadDbEmployeesPage(1);
    } else if (tableName === 'business_rule') {
        const res = await fetch('/api/rules');
        const data = await res.json();
        container.innerHTML = `
            <h4>Bảng business rule (Tổng ${data.rules.length} bản ghi)</h4>
            <div class="table-responsive" style="margin-top:10px;">
                <table class="saas-table">
                    <thead><tr><th>Mã rule</th><th>Tên quy tắc</th><th>Đơn vị</th><th>Kết quả</th><th>Căn cứ</th><th>Trạng thái</th></tr></thead>
                    <tbody>${(data.rules || []).map(r => `<tr><td><code>${escapeHtml(r.ma_quy_tac)}</code></td><td>${escapeHtml(r.ten_quy_tac || '')}</td><td>${escapeHtml(r.ten_don_vi || '')}</td><td>${renderStatusBadge(r.ket_qua)}</td><td>${escapeHtml(r.can_cu)}</td><td>${escapeHtml(ruleStatusLabel(r.trang_thai))}</td></tr>`).join('')}</tbody>
                </table>
            </div>`;
    } else if (tableName === 'ngoai_le_ca_nhan') {
        const res = await fetch('/api/exceptions');
        const data = await res.json();
        container.innerHTML = `
            <h4>Bảng ngoại lệ cá nhân (Tổng ${data.exceptions.length} bản ghi)</h4>
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
            <h4>Bảng đơn vị nguồn (Tổng ${data.units.length} bản ghi)</h4>
            <div class="table-responsive" style="margin-top:10px;">
                <table class="saas-table">
                    <thead><tr><th>ID</th><th>Tên đơn vị</th></tr></thead>
                    <tbody>${(data.units || []).map(r => `<tr><td>${r.id}</td><td>${escapeHtml(r.ten_don_vi)}</td></tr>`).join('')}</tbody>
                </table>
            </div>`;
    }
}

async function loadSystemSettings() {
    try {
        const res = await fetch('/api/system');
        if (!res.ok) return;
        const data = await res.json();
        AppState.systemInfo = data;

        document.getElementById('lan-full-url').textContent = `http://${data.host_name || 'localhost'}:8000`;
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

// Helper to set up explicit UI states for automated snapshot verification
// Initialization
document.addEventListener('DOMContentLoaded', () => {
    refreshDataTypeOptions();
    onCommitModeChange();
    bootstrapAuth();
});
