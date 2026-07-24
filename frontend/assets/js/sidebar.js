const DEFAULT_FEATURE_FLAGS = {
    super_admin: { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: true, admin: true },
    reseller: { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: true, admin: false },
    user: { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: true, admin: false },
};

const USER_FEATURE_KEY = 'user_feature_flags';
const USER_ROLE_KEY = 'user_role';
const SIDEBAR_API_BASE = (typeof API_URL !== 'undefined' && API_URL)
    ? API_URL
    : ((window.location.protocol === 'file:' || ['localhost', '127.0.0.1'].includes(window.location.hostname)) ? 'http://127.0.0.1:8000' : window.location.origin);

const SIDEBAR_MENU_TEMPLATE = `
    <a href="dashboard.html" class="sidebar-link" data-feature-key="dashboard"><span class="sidebar-icon">📊</span> Dashboard</a>
    <div class="sidebar-group" data-feature-key="clients">
        <button class="sidebar-link sidebar-group-title sidebar-toggle" type="button" aria-expanded="false" aria-controls="clientsSubmenu">
            <span class="sidebar-icon">👥</span> Clientes
        </button>
        <div class="sidebar-submenu" id="clientsSubmenu">
            <a href="clients.html" class="sidebar-link sidebar-sublink" data-feature-key="clients"><span class="sidebar-icon">👥</span> Clientes</a>
            <a href="import_clients.html" class="sidebar-link sidebar-sublink" data-feature-key="clients"><span class="sidebar-icon">📂</span> Importar / Padronizar</a>
            <a href="backup_clients.html" class="sidebar-link sidebar-sublink" data-feature-key="clients"><span class="sidebar-icon">💾</span> Backup / Exportar</a>
            <a href="messages.html" class="sidebar-link sidebar-sublink" data-feature-key="clients"><span class="sidebar-icon">✉️</span> Mensagens Pré-Prontas</a>
        </div>
    </div>
    <div class="sidebar-group" data-feature-key="products">
        <button class="sidebar-link sidebar-group-title sidebar-toggle" type="button" aria-expanded="false" aria-controls="productsSubmenu">
            <span class="sidebar-icon">📦</span> Produtos
        </button>
        <div class="sidebar-submenu" id="productsSubmenu">
            <a href="produtos.html" class="sidebar-link sidebar-sublink" data-feature-key="products"><span class="sidebar-icon">🛒</span> Produtos/Serviços</a>
            <a href="categorias.html" class="sidebar-link sidebar-sublink" data-feature-key="products"><span class="sidebar-icon">🏷️</span> Categorias</a>
            <a href="planos.html" class="sidebar-link sidebar-sublink" data-feature-key="products"><span class="sidebar-icon">📄</span> Planos</a>
            <a href="api-pagamentos.html" class="sidebar-link sidebar-sublink" data-feature-key="products"><span class="sidebar-icon">💳</span> API de Pagamentos</a>
        </div>
    </div>
    <a href="whatsapp.html" class="sidebar-link" data-feature-key="whatsapp"><span class="sidebar-icon">📱</span> Integração WhatsApp</a>
    <a href="dashboard.html#telegram" class="sidebar-link" data-feature-key="telegram"><span class="sidebar-icon">✈️</span> Integração Telegram</a>
    <a href="dashboard.html#settings" class="sidebar-link" data-feature-key="settings"><span class="sidebar-icon">⚙️</span> Configurações</a>
    <a href="resell.html" class="sidebar-link" data-role-required="reseller" data-feature-key="resell"><span class="sidebar-icon">💼</span> Revendedores</a>
    <a href="admin.html" class="sidebar-link" data-feature-key="admin"><span class="sidebar-icon">👑</span> Super Admin</a>
`;

function renderSidebarMenu() {
    const menu = document.querySelector('.sidebar-menu');
    if (!menu) return;

    menu.innerHTML = SIDEBAR_MENU_TEMPLATE;
}

function ensureAdminLink() {
    const menu = document.querySelector('.sidebar-menu');
    if (!menu || menu.querySelector('a[href="admin.html"]')) return;

    const link = document.createElement('a');
    link.href = 'admin.html';
    link.className = 'sidebar-link';
    link.setAttribute('data-feature-key', 'admin');
    link.innerHTML = '<span class="sidebar-icon">👑</span> Super Admin';

    const resellLink = menu.querySelector('a[href="resell.html"]');
    if (resellLink) {
        menu.insertBefore(link, resellLink.nextSibling);
    } else {
        menu.appendChild(link);
    }
}

function getCurrentRole() {
    return localStorage.getItem(USER_ROLE_KEY) || 'user';
}

function roleAllowsAccess(requiredRole, currentRole) {
    if (!requiredRole) return true;
    if (currentRole === 'super_admin') return true;
    if (requiredRole === 'reseller') return currentRole === 'reseller';
    return currentRole === requiredRole;
}

async function fetchCurrentUserContext() {
    const token = localStorage.getItem('token');
    if (!token) return null;

    try {
        const response = await fetch(`${SIDEBAR_API_BASE}/users/me`, {
            headers: { Authorization: `Bearer ${token}` }
        });

        if (!response.ok) return null;

        const user = await response.json();
        if (user.role) localStorage.setItem(USER_ROLE_KEY, user.role);
        if (user.id) localStorage.setItem('user_id', user.id);

        const flags = user.effective_feature_flags || user.feature_flags;
        if (flags) localStorage.setItem(USER_FEATURE_KEY, JSON.stringify(flags));
        if (user.reseller_feature_flags) {
            localStorage.setItem('reseller_feature_flags', JSON.stringify(user.reseller_feature_flags));
        }

        return user;
    } catch (error) {
        console.warn('Falha ao carregar contexto do usuário', error);
        return null;
    }
}

function loadFeatureFlags() {
    try {
        const storedPerRole = JSON.parse(localStorage.getItem('featureFlags') || '{}');
        const userFlags = JSON.parse(localStorage.getItem(USER_FEATURE_KEY) || 'null');
        const role = localStorage.getItem(USER_ROLE_KEY) || 'user';
        const roleDefaults = {
            super_admin: Object.assign({}, DEFAULT_FEATURE_FLAGS.super_admin, storedPerRole.super_admin || {}),
            reseller: Object.assign({}, DEFAULT_FEATURE_FLAGS.reseller, storedPerRole.reseller || {}),
            user: Object.assign({}, DEFAULT_FEATURE_FLAGS.user, storedPerRole.user || {})
        };
        return userFlags || roleDefaults[role] || DEFAULT_FEATURE_FLAGS.user;
    } catch (error) {
        return DEFAULT_FEATURE_FLAGS.user;
    }
}

function redirectIfPageHidden() {
    const currentPage = window.location.pathname.split('/').pop() || 'dashboard.html';
    const allLinks = Array.from(document.querySelectorAll('.sidebar-menu a.sidebar-link, .sidebar-menu a.sidebar-sublink, .sidebar-menu a.submenu-link'));
    const isCurrentVisible = allLinks.some((link) => {
        if (link.style.display === 'none') return false;
        const href = (link.getAttribute('href') || '').split('?')[0].split('#')[0];
        return href.split('/').pop() === currentPage;
    });

    if (!isCurrentVisible) {
        const firstVisible = allLinks.find((link) => {
            if (link.style.display === 'none') return false;
            const href = link.getAttribute('href') || '';
            return href && href !== '#';
        });

        if (firstVisible) {
            window.location.href = firstVisible.getAttribute('href');
        }
    }
}

function applyFeatureFlags() {
    const flags = loadFeatureFlags();
    const alwaysVisibleKeys = new Set(['resell', 'super_admin']);
    const currentRole = getCurrentRole();

    document.querySelectorAll('[data-feature-key]').forEach((element) => {
        const key = element.getAttribute('data-feature-key');
        const allowed = alwaysVisibleKeys.has(key) || flags[key] !== false;
        element.style.display = allowed ? '' : 'none';
    });

    document.querySelectorAll('[data-role-required]').forEach((element) => {
        const requiredRole = element.getAttribute('data-role-required');
        element.style.display = roleAllowsAccess(requiredRole, currentRole) ? '' : 'none';
    });

    document.querySelectorAll('a[href="resell.html"]').forEach((link) => {
        link.style.display = flags.resell === false ? 'none' : '';
    });

    document.querySelectorAll('.sidebar-group').forEach((group) => {
        const groupKey = group.getAttribute('data-feature-key');
        if (groupKey && flags[groupKey] === false && !alwaysVisibleKeys.has(groupKey)) {
            group.style.display = 'none';
            return;
        }

        const submenu = group.querySelector('.sidebar-submenu');
        if (!submenu) return;

        const hasVisible = Array.from(submenu.querySelectorAll('a')).some((link) => link.style.display !== 'none');
        group.style.display = hasVisible ? '' : 'none';
    });

    redirectIfPageHidden();
}

function closeOtherSubmenus(exceptSubmenu) {
    document.querySelectorAll('.sidebar-submenu').forEach((menu) => {
        if (menu === exceptSubmenu) return;
        menu.classList.remove('is-open');
        const group = menu.closest('.sidebar-group');
        const toggle = group ? group.querySelector('.sidebar-toggle') : menu.previousElementSibling;
        if (toggle && toggle.classList.contains('sidebar-toggle')) {
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
}

function setupSidebarAccordion() {
    const toggles = document.querySelectorAll('.sidebar-toggle');
    if (!toggles.length) return;

    toggles.forEach((toggle) => {
        const targetId = toggle.getAttribute('aria-controls');
        const submenu = targetId ? document.getElementById(targetId) : null;
        if (!submenu) return;

        submenu.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');

        toggle.addEventListener('click', (event) => {
            event.stopPropagation();
            const isOpen = submenu.classList.contains('is-open');
            closeOtherSubmenus(null);

            if (!isOpen) {
                submenu.classList.add('is-open');
                toggle.setAttribute('aria-expanded', 'true');
            }
        });
    });

    document.querySelectorAll('.sidebar-menu > .sidebar-link:not(.sidebar-toggle)').forEach((link) => {
        link.addEventListener('click', () => closeOtherSubmenus(null));
    });

    document.querySelectorAll('.sidebar-submenu a').forEach((link) => {
        link.addEventListener('click', (event) => event.stopPropagation());
    });
}

function normalizePageName(href) {
    if (!href) return '';
    try {
        return href.split('#')[0].split('?')[0].split('/').pop();
    } catch (error) {
        return href;
    }
}

function getCurrentRouteState() {
    const page = normalizePageName(window.location.pathname) || 'dashboard.html';
    const hash = (window.location.hash || '').replace(/^#/, '');
    return { page, hash };
}

function markActiveLink() {
    const route = getCurrentRouteState();

    document.querySelectorAll('.sidebar-menu a').forEach((link) => link.classList.remove('active'));

    let activeLink = null;
    document.querySelectorAll('.sidebar-menu a').forEach((link) => {
        const href = link.getAttribute('href') || '';
        const page = normalizePageName(href);
        const hash = href.includes('#') ? href.split('#')[1] : '';

        if (route.page === 'dashboard.html' && route.hash && page === 'dashboard.html' && hash === route.hash) {
            activeLink = link;
            return;
        }

        if (!route.hash && page && page === route.page) {
            activeLink = link;
        }
    });

    if (activeLink) {
        activeLink.classList.add('active');

        const submenu = activeLink.closest('.sidebar-submenu');
        if (submenu) {
            const group = submenu.closest('.sidebar-group');
            const toggle = group ? group.querySelector('.sidebar-toggle') : null;
            submenu.classList.add('is-open');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
        }
    }
}

renderSidebarMenu();

async function initSidebar() {
    await fetchCurrentUserContext();
    ensureAdminLink();
    setupSidebarAccordion();
    applyFeatureFlags();
    markActiveLink();
}

document.addEventListener('DOMContentLoaded', initSidebar);

window.applyFeatureFlags = applyFeatureFlags;
window.markSidebarActiveLink = markActiveLink;
