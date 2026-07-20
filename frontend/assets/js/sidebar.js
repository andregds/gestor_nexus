// frontend/assets/js/sidebar.js
// v2.0 - Reescrito para corrigir isolamento entre menus Clientes e Produtos

const DEFAULT_FEATURE_FLAGS = {
    super_admin: { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: true, admin: true },
    reseller:    { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: true, admin: false },
    user:        { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: true, admin: false },
};

const USER_FEATURE_KEY = 'user_feature_flags';
const USER_ROLE_KEY    = 'user_role';
const SIDEBAR_API_BASE = (typeof API_URL !== 'undefined' && API_URL) ? API_URL : '';

// ---------------------------------------------------------------------------
// 1. CONTEXTO DO USUÁRIO
// ---------------------------------------------------------------------------
async function fetchCurrentUserContext() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    const url = SIDEBAR_API_BASE ? `${SIDEBAR_API_BASE}/users/me` : '/users/me';
    try {
        const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        if (!resp.ok) return null;
        const user = await resp.json();
        if (user.role)  localStorage.setItem(USER_ROLE_KEY, user.role);
        if (user.id)    localStorage.setItem('user_id', user.id);
        const flags = user.effective_feature_flags || user.feature_flags;
        if (flags) localStorage.setItem(USER_FEATURE_KEY, JSON.stringify(flags));
        if (user.reseller_feature_flags)
            localStorage.setItem('reseller_feature_flags', JSON.stringify(user.reseller_feature_flags));
        return user;
    } catch (e) {
        console.warn('Falha ao carregar contexto do usuário', e);
        return null;
    }
}

// ---------------------------------------------------------------------------
// 2. FEATURE FLAGS
// ---------------------------------------------------------------------------
function loadFeatureFlags() {
    try {
        const storedPerRole = JSON.parse(localStorage.getItem('featureFlags') || '{}');
        const userFlags     = JSON.parse(localStorage.getItem(USER_FEATURE_KEY) || 'null');
        const role          = localStorage.getItem(USER_ROLE_KEY) || 'user';
        const roleDefaults  = {
            super_admin: { ...DEFAULT_FEATURE_FLAGS.super_admin, ...(storedPerRole.super_admin || {}) },
            reseller:    { ...DEFAULT_FEATURE_FLAGS.reseller,    ...(storedPerRole.reseller    || {}) },
            user:        { ...DEFAULT_FEATURE_FLAGS.user,        ...(storedPerRole.user        || {}) },
        };
        return userFlags || roleDefaults[role] || DEFAULT_FEATURE_FLAGS.user;
    } catch (e) {
        return DEFAULT_FEATURE_FLAGS.user;
    }
}

function applyFeatureFlags() {
    const flags = loadFeatureFlags();
    const alwaysVisibleKeys = new Set(['resell', 'super_admin']);

    document.querySelectorAll('[data-feature-key]').forEach((el) => {
        const key = el.getAttribute('data-feature-key');
        // Respeita o flag definido pelo super_admin; default true se não definido
        const allowed = alwaysVisibleKeys.has(key) || flags[key] !== false;
        el.style.display = allowed ? '' : 'none';
    });

    document.querySelectorAll('a[href="resell.html"]').forEach((link) => {
        link.style.display = flags.resell === false ? 'none' : '';
    });

    // Oculta grupos cujo próprio flag esteja desligado
    document.querySelectorAll('.sidebar-group').forEach((group) => {
        const groupKey = group.getAttribute('data-feature-key');
        if (groupKey && flags[groupKey] === false && !alwaysVisibleKeys.has(groupKey)) {
            group.style.display = 'none';
            return;
        }

        const submenu = group.querySelector('.sidebar-submenu');
        if (!submenu) return;
        const hasVisible = Array.from(submenu.querySelectorAll('a')).some(
            (link) => link.style.display !== 'none'
        );
        group.style.display = hasVisible ? '' : 'none';
    });

    // Redireciona se a página atual estiver oculta para o usuário
    redirectIfPageHidden(flags);
}

function redirectIfPageHidden(flags) {
    const currentPage = window.location.pathname.split('/').pop() || 'dashboard.html';
    const allLinks = Array.from(document.querySelectorAll(
        '.sidebar-menu a.sidebar-link, .sidebar-menu a.sidebar-sublink, .sidebar-menu a.submenu-link'
    ));
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
        if (firstVisible) window.location.href = firstVisible.getAttribute('href');
    }
}

// ---------------------------------------------------------------------------
// 3. ACCORDION DO MENU
// ---------------------------------------------------------------------------

/**
 * Fecha todos os submenus EXCETO o informado.
 * Passando null fecha todos.
 */
function closeOtherSubmenus(exceptSubmenu) {
    document.querySelectorAll('.sidebar-submenu').forEach((menu) => {
        if (menu === exceptSubmenu) return;
        menu.classList.remove('is-open');
        // Atualiza o toggle pai
        const group  = menu.closest('.sidebar-group');
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
        const submenu  = targetId ? document.getElementById(targetId) : null;
        if (!submenu) return;

        // Garante início fechado (markActiveLink abrirá o correto)
        submenu.classList.remove('is-open');
        toggle.setAttribute('aria-expanded', 'false');

        toggle.addEventListener('click', (ev) => {
            ev.stopPropagation();
            const isOpen = submenu.classList.contains('is-open');
            // Fecha todos os outros
            closeOtherSubmenus(null);
            if (!isOpen) {
                submenu.classList.add('is-open');
                toggle.setAttribute('aria-expanded', 'true');
            }
        });
    });

    // Links simples (não-toggle) fecham todos os submenus ao serem clicados
    document.querySelectorAll('.sidebar-menu > .sidebar-link:not(.sidebar-toggle)').forEach((link) => {
        link.addEventListener('click', () => closeOtherSubmenus(null));
    });

    // Links dentro de submenus: apenas stopPropagation para não acionar toggles pais
    document.querySelectorAll('.sidebar-submenu a').forEach((link) => {
        link.addEventListener('click', (ev) => ev.stopPropagation());
    });
}

// ---------------------------------------------------------------------------
// 4. MARCAÇÃO DO LINK ATIVO
// ---------------------------------------------------------------------------
function normalizePageName(href) {
    if (!href) return '';
    try { return href.split('#')[0].split('?')[0].split('/').pop(); } catch { return href; }
}

function markActiveLink() {
    const currentPage = normalizePageName(window.location.pathname);

    // Remove todas as marcações ativas
    document.querySelectorAll('.sidebar-menu a').forEach((link) => link.classList.remove('active'));

    // Encontra o link correspondente à página atual
    let activeLink = null;
    document.querySelectorAll('.sidebar-menu a').forEach((link) => {
        const page = normalizePageName(link.getAttribute('href'));
        if (page && page === currentPage) activeLink = link;
    });

    if (activeLink) {
        activeLink.classList.add('active');

        // Se o link está dentro de um submenu, abre APENAS esse submenu
        const submenu = activeLink.closest('.sidebar-submenu');
        if (submenu) {
            const group  = submenu.closest('.sidebar-group');
            const toggle = group ? group.querySelector('.sidebar-toggle') : null;
            submenu.classList.add('is-open');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
        }
    }
}

// ---------------------------------------------------------------------------
// 5. SUPER ADMIN LINK (garante existência se ausente no HTML)
// ---------------------------------------------------------------------------
function ensureSuperAdminLink() {
    const menu = document.querySelector('.sidebar-menu');
    if (!menu) return;
    if (menu.querySelector('[data-feature-key="super_admin"]')) return;

    const link = document.createElement('a');
    link.href                 = 'admin.html';
    link.className            = 'sidebar-link';
    link.dataset.featureKey   = 'super_admin';
    link.dataset.roleRequired = 'super_admin';
    link.innerHTML            = '<span class="sidebar-icon">👑</span> Super Admin';

    const adminLink = menu.querySelector('[data-feature-key="admin"]');
    if (adminLink && adminLink.parentNode === menu) {
        adminLink.insertAdjacentElement('afterend', link);
    } else {
        menu.appendChild(link);
    }
}

// ---------------------------------------------------------------------------
// 6. INICIALIZAÇÃO
// ---------------------------------------------------------------------------
async function initSidebar() {
    await fetchCurrentUserContext();
    // NÃO manipula o DOM dos produtos (já está no HTML de cada página)
    setupSidebarAccordion();   // 1º configura os toggles (fecha tudo)
    ensureSuperAdminLink();
    applyFeatureFlags();
    markActiveLink();          // 2º abre apenas o submenu da página atual
}

document.addEventListener('DOMContentLoaded', initSidebar);

// Disponibiliza para reuso após alterações no Admin
window.applyFeatureFlags = applyFeatureFlags;
