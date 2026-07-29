const MAIN_API_URL = (typeof API_URL !== 'undefined' && API_URL)
    ? API_URL
    : ((window.location.protocol === 'file:' || ['localhost', '127.0.0.1'].includes(window.location.hostname)) ? 'http://127.0.0.1:8000' : window.location.origin);

function clearSessionAndRedirect() {
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_feature_flags');
    window.location.href = 'login.html';
}

if (typeof window.logout !== 'function') {
    window.logout = function logout() {
        clearSessionAndRedirect();
    };
}

async function fetchAPI(path, options = {}) {
    const token = localStorage.getItem('token');
    const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetch(`${MAIN_API_URL}${path}`, Object.assign({}, options, { headers }));

    if (response.status === 401) {
        clearSessionAndRedirect();
        throw new Error('Sessão expirada. Faça login novamente.');
    }

    const text = await response.text();
    let data = null;

    if (text) {
        try {
            data = JSON.parse(text);
        } catch (error) {
            data = text;
        }
    }

    if (!response.ok) {
        const message = data && data.detail ? data.detail : `Erro ${response.status}`;
        throw new Error(message);
    }

    return data;
}

function setText(selector, value) {
    document.querySelectorAll(selector).forEach((element) => {
        element.textContent = value;
    });
}

function formatRoleLabel(role) {
    switch (role) {
        case 'super_admin':
            return 'Super Administrador';
        case 'reseller':
            return 'Revendedor';
        case 'admin':
            return 'Administrador';
        default:
            return 'Usuário';
    }
}

function setSidebarOpen(sidebar, overlay, shouldOpen) {
    if (!sidebar) return;
    sidebar.classList.toggle('active', shouldOpen);
    document.body.classList.toggle('sidebar-open', shouldOpen);
    if (overlay) overlay.classList.toggle('active', shouldOpen);
}

function ensureSidebarShell() {
    const sidebar = document.getElementById('sidebar');
    const dashboardContainer = document.querySelector('.dashboard-container');
    if (!sidebar || !dashboardContainer) return null;

    let mobileHeader = document.querySelector('.navbar-mobile');
    if (!mobileHeader) {
        mobileHeader = document.createElement('div');
        mobileHeader.className = 'navbar-mobile';
        mobileHeader.innerHTML = `
            <div class="brand-logo">GESTOR<span>NEXUS</span></div>
            <button class="mobile-toggle" id="btnToggleSidebar" type="button" aria-label="Abrir menu">☰</button>
        `;
        dashboardContainer.parentNode.insertBefore(mobileHeader, dashboardContainer);
    }

    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        overlay.setAttribute('aria-hidden', 'true');
        document.body.appendChild(overlay);
    }

    return { sidebar, overlay };
}

async function loadSidebarInfo() {
    const token = localStorage.getItem('token');
    if (!token) {
        clearSessionAndRedirect();
        return null;
    }

    const user = await fetchAPI('/users/me');
    const name = user.name || 'Usuário';
    const role = user.role || 'user';
    const roleLabel = formatRoleLabel(role);

    localStorage.setItem('user_role', role);

    setText('#userName', name);
    setText('#userRole', roleLabel);

    document.querySelectorAll('.user-role').forEach((element) => {
        if (!element.id || element.id === 'userRole') {
            element.textContent = roleLabel;
        }
    });

    const creditValue = typeof user.client_limit === 'number'
        ? user.client_limit
        : (typeof user.remaining_client_limit === 'number' ? user.remaining_client_limit : null);

    if (creditValue !== null) {
        setText('#userCredits', `Limite: ${creditValue}`);
    }

    return user;
}

function bindSidebarShell() {
    const shell = ensureSidebarShell();
    if (!shell) return;

    const { sidebar, overlay } = shell;
    const mobileButton = document.getElementById('btnToggleSidebar');
    const desktopButton = document.getElementById('btnToggleSidebarDesktop');

    if (mobileButton && sidebar) {
        mobileButton.addEventListener('click', () => {
            const shouldOpen = !sidebar.classList.contains('active');
            setSidebarOpen(sidebar, overlay, shouldOpen);
        });
    }

    if (desktopButton && sidebar) {
        desktopButton.addEventListener('click', () => {
            const shouldOpen = !sidebar.classList.contains('active');
            setSidebarOpen(sidebar, overlay, shouldOpen);
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => setSidebarOpen(sidebar, overlay, false));
    }

    document.querySelectorAll('.sidebar a').forEach((element) => {
        element.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                setSidebarOpen(sidebar, overlay, false);
            }
        });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            setSidebarOpen(sidebar, overlay, false);
        }
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            setSidebarOpen(sidebar, overlay, false);
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    bindSidebarShell();
    if (localStorage.getItem('token')) {
        loadSidebarInfo().catch(() => {});
    }
});

window.fetchAPI = fetchAPI;
window.loadSidebarInfo = loadSidebarInfo;
