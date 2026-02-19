// frontend/assets/js/sidebar.js

const DEFAULT_FEATURE_FLAGS = {
    super_admin: {
        dashboard: true,
        clients: true,
        products: true,
        whatsapp: true,
        telegram: true,
        settings: true,
        resell: true,
        admin: true,
    },
    reseller: {
        dashboard: true,
        clients: true,
        products: true,
        whatsapp: true,
        telegram: true,
        settings: true,
        resell: true,
        admin: false,
    },
    user: {
        dashboard: true,
        clients: true,
        products: true,
        whatsapp: true,
        telegram: true,
        settings: true,
        resell: true,
        admin: false,
    },
};

const USER_FEATURE_KEY = 'user_feature_flags';
const USER_ROLE_KEY = 'user_role';

// Prefer global API_URL when disponível para evitar 404 em ambientes com proxy
const SIDEBAR_API_BASE = (typeof API_URL !== 'undefined' && API_URL) ? API_URL : '';

async function fetchCurrentUserContext() {
    const token = localStorage.getItem('token');
    if (!token) return null;
    const url = SIDEBAR_API_BASE ? `${SIDEBAR_API_BASE}/users/me` : '/users/me';
    try {
        const resp = await fetch(url, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) return null;
        const user = await resp.json();
        if (user.role) localStorage.setItem(USER_ROLE_KEY, user.role);
        if (user.id) localStorage.setItem('user_id', user.id);
        const flags = user.effective_feature_flags || user.feature_flags;
        if (flags) localStorage.setItem(USER_FEATURE_KEY, JSON.stringify(flags));
        if (user.reseller_feature_flags) localStorage.setItem('reseller_feature_flags', JSON.stringify(user.reseller_feature_flags));
        return user;
    } catch (e) {
        console.warn('Falha ao carregar contexto do usuário', e);
        return null;
    }
}

function loadFeatureFlags() {
    try {
        const storedPerRole = JSON.parse(localStorage.getItem('featureFlags') || '{}');
        const userFlags = JSON.parse(localStorage.getItem(USER_FEATURE_KEY) || 'null');
        const role = localStorage.getItem(USER_ROLE_KEY) || 'user';
        const roleDefaults = {
            super_admin: { ...DEFAULT_FEATURE_FLAGS.super_admin, ...(storedPerRole.super_admin || {}) },
            reseller: { ...DEFAULT_FEATURE_FLAGS.reseller, ...(storedPerRole.reseller || {}) },
            user: { ...DEFAULT_FEATURE_FLAGS.user, ...(storedPerRole.user || {}) },
        };
        return userFlags || roleDefaults[role] || DEFAULT_FEATURE_FLAGS.user;
    } catch (e) {
        return DEFAULT_FEATURE_FLAGS.user;
    }
}

function applyFeatureFlags() {
    const flags = loadFeatureFlags();

    // Aplica visibilidade item a item
    document.querySelectorAll('[data-feature-key]').forEach((el) => {
        const key = el.getAttribute('data-feature-key');
        // Dashboard e Produtos sempre visíveis para evitar desaparecimento do menu
        const alwaysVisible = key === 'dashboard' || key === 'products';
        const allowed = alwaysVisible ? true : flags[key] !== false; // padrão é true
        el.style.display = allowed ? '' : 'none';
    });

    // Ajusta grupos com submenus
    document.querySelectorAll('.sidebar-group').forEach((group) => {
        const submenu = group.querySelector('.sidebar-submenu');
        const toggle = group.querySelector('.sidebar-toggle');
        if (!submenu) return;
        const hasVisible = Array.from(submenu.querySelectorAll('[data-feature-key]')).some((link) => link.style.display !== 'none');
        group.style.display = hasVisible ? '' : 'none';
        if (toggle) {
            const isOpen = submenu.classList.contains('is-open');
            // Mantém aberto apenas se ainda houver itens visíveis
            submenu.classList.toggle('is-open', hasVisible && isOpen);
            toggle.setAttribute('aria-expanded', submenu.classList.contains('is-open'));
        }
    });

    // Se a página atual estiver bloqueada, redireciona para a próxima disponível
    const currentPage = window.location.pathname.split('/').pop() || 'dashboard.html';
    const menuAnchors = document.querySelectorAll('.sidebar-menu a.sidebar-link, .sidebar-menu a.submenu-link, .sidebar-menu a.sidebar-sublink');
    const visibleLinks = Array.from(menuAnchors).filter((link) => {
        if (link.style.display === 'none') return false;
        const href = link.getAttribute('href') || '';
        const key = link.getAttribute('data-feature-key');
        // Tratar links SPA (href="#") como válidos usando o feature-key
        const resolvedHref = href && href !== '#' ? href : (key ? `${key}.html` : '');
        return resolvedHref !== '';
    });
    const isCurrentVisible = visibleLinks.some((link) => {
        const href = link.getAttribute('href') || '';
        const key = link.getAttribute('data-feature-key');
        const resolvedHref = href && href !== '#' ? href : (key ? `${key}.html` : '');
        return resolvedHref.split('/').pop() === currentPage;
    });
    if (!isCurrentVisible && visibleLinks.length) {
        const href = visibleLinks[0].getAttribute('href') || '';
        const key = visibleLinks[0].getAttribute('data-feature-key');
        const resolvedHref = href && href !== '#' ? href : (key ? `${key}.html` : '#');
        window.location.href = resolvedHref;
    }
}

function normalizePageName(href) {
    if (!href) return '';
    try {
        const clean = href.split('#')[0].split('?')[0];
        return clean.split('/').pop();
    } catch (e) {
        return href;
    }
}

function ensureProductsGroup() {
    const menu = document.querySelector('.sidebar-menu');
    if (!menu) return;

    const productItems = [
        { href: 'produtos.html', icon: '🛒', label: 'Produtos/Servicos' },
        { href: 'categorias.html', icon: '🏷️', label: 'Categorias' },
        { href: 'planos.html', icon: '📄', label: 'Planos' },
        { href: 'recursos.html', icon: '🧩', label: 'Recursos' },
    ];

    let group = menu.querySelector('.sidebar-group[data-feature-key="products"]') || menu.querySelector('.sidebar-group');
    if (!group) {
        group = document.createElement('div');
        group.className = 'sidebar-group';
        group.dataset.featureKey = 'products';
        menu.insertBefore(group, menu.querySelector('[data-feature-key="whatsapp"]') || null);
    } else {
        group.dataset.featureKey = 'products';
    }

    let toggle = group.querySelector('.sidebar-toggle');
    if (!toggle) {
        toggle = document.createElement('button');
        group.prepend(toggle);
    }
    toggle.classList.add('sidebar-link', 'sidebar-group-title', 'sidebar-toggle');
    toggle.type = 'button';
    toggle.setAttribute('aria-controls', 'productsSubmenu');
    if (!toggle.innerHTML.trim()) toggle.innerHTML = '<span class="sidebar-icon">📦</span> Produtos';

    let submenu = group.querySelector('.sidebar-submenu');
    if (!submenu) {
        submenu = document.createElement('div');
        submenu.className = 'sidebar-submenu';
        group.appendChild(submenu);
    }
    submenu.id = 'productsSubmenu';

    productItems.forEach(({ href, icon, label }) => {
        const pageName = normalizePageName(href);
        let link = Array.from(submenu.querySelectorAll('a')).find((a) => normalizePageName(a.getAttribute('href')) === pageName);
        if (!link) {
            link = document.createElement('a');
            submenu.appendChild(link);
        }
        link.href = href;
        link.className = 'sidebar-link sidebar-sublink';
        link.dataset.featureKey = 'products';
        link.innerHTML = `<span class="sidebar-icon">${icon}</span> ${label}`;
    });
}

function markActiveLink() {
    const currentPage = normalizePageName(window.location.pathname);
    const menuAnchors = document.querySelectorAll('.sidebar-menu a');
    let activeLink = null;
    menuAnchors.forEach((link) => {
        const hrefPage = normalizePageName(link.getAttribute('href'));
        if (hrefPage && hrefPage === currentPage) {
            activeLink = link;
        }
        link.classList.remove('active');
    });
    if (activeLink) {
        activeLink.classList.add('active');
        const submenu = activeLink.closest('.sidebar-submenu');
        const toggle = submenu?.previousElementSibling;
        if (submenu && toggle && toggle.classList.contains('sidebar-toggle')) {
            submenu.classList.add('is-open');
            toggle.setAttribute('aria-expanded', 'true');
        }
    }
}

function setupSidebarAccordion() {
    const toggles = document.querySelectorAll('.sidebar-toggle');
    if (!toggles.length) return;

    const currentPage = normalizePageName(window.location.pathname);

    toggles.forEach(toggle => {
        const targetId = toggle.getAttribute('aria-controls');
        const submenu = targetId ? document.getElementById(targetId) : null;
        if (!submenu) return;

        const hasActiveLink = Array.from(submenu.querySelectorAll('a')).some(link => {
            const href = normalizePageName(link.getAttribute('href'));
            return href === currentPage;
        });

        submenu.classList.toggle('is-open', hasActiveLink);
        toggle.setAttribute('aria-expanded', hasActiveLink ? 'true' : 'false');

        toggle.addEventListener('click', () => {
            const isOpen = submenu.classList.toggle('is-open');
            toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        });
    });
}

function ensureSuperAdminLink() {
    const menu = document.querySelector('.sidebar-menu');
    if (!menu) return;
    if (menu.querySelector('[data-feature-key="admin"]')) return;
    const link = document.createElement('a');
    link.href = 'admin.html';
    link.className = 'sidebar-link';
    link.dataset.featureKey = 'admin';
    link.dataset.roleRequired = 'super_admin';
    link.innerHTML = '<span class="sidebar-icon">👑</span> Super Admin';
    menu.appendChild(link);
}

async function initSidebar() {
    await fetchCurrentUserContext();
    ensureProductsGroup();
    setupSidebarAccordion();
    ensureSuperAdminLink();
    applyFeatureFlags();
    markActiveLink();
}

document.addEventListener('DOMContentLoaded', initSidebar);

// Disponibiliza para reuso após alterações no Admin
window.applyFeatureFlags = applyFeatureFlags;
