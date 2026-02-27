// frontend/assets/js/sidebar.js
// v2.4 - Carregamento rápido: usa cache local primeiro, depois atualiza do servidor

const DEFAULT_FEATURE_FLAGS = {
    super_admin: { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: true,  admin: true  },
    reseller:    { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: false, admin: false },
    user:        { dashboard: true, clients: true, products: true, whatsapp: true, telegram: true, settings: true, resell: false, admin: false },
};

const USER_FEATURE_KEY = 'user_feature_flags';
const USER_ROLE_KEY    = 'user_role';
const SIDEBAR_API_BASE = (typeof API_URL !== 'undefined' && API_URL) ? API_URL : 'http://127.0.0.1:8000';

// ---------------------------------------------------------------------------
// 1. FEATURE FLAGS - Carregamento rápido do cache
// ---------------------------------------------------------------------------
function loadFeatureFlags() {
    try {
        const userFlags = JSON.parse(localStorage.getItem(USER_FEATURE_KEY) || 'null');
        const role = localStorage.getItem(USER_ROLE_KEY) || 'user';
        if (userFlags && typeof userFlags === 'object') return userFlags;
        return { ...(DEFAULT_FEATURE_FLAGS[role] || DEFAULT_FEATURE_FLAGS.user) };
    } catch (e) {
        return { ...DEFAULT_FEATURE_FLAGS.user };
    }
}

function applyFeatureFlags() {
    const flags = loadFeatureFlags();

    document.querySelectorAll('[data-feature-key]').forEach((el) => {
        const key = el.getAttribute('data-feature-key');
        const allowed = flags[key] === true;

        if (allowed) {
            el.style.display = '';
            el.style.visibility = 'visible';
        } else {
            el.style.display = 'none';
        }
    });

    // Oculta grupos cujos sub-itens estejam todos ocultos
    document.querySelectorAll('.sidebar-group[data-feature-key]').forEach((group) => {
        const submenu = group.querySelector('.sidebar-submenu');
        if (!submenu) return;
        const hasVisible = Array.from(submenu.querySelectorAll('a')).some(
            (link) => link.style.display !== 'none'
        );
        group.style.display = hasVisible ? '' : 'none';
    });

    // Remove o CSS de preload
    const preloadStyle = document.getElementById('sidebar-preload-hide');
    if (preloadStyle) preloadStyle.remove();

    // Redireciona se a página atual estiver oculta
    redirectIfPageHidden(flags);
}

// ---------------------------------------------------------------------------
// 2. CONTEXTO DO USUÁRIO - Busca em background (não bloqueia renderização)
// ---------------------------------------------------------------------------
async function fetchCurrentUserContext() {
    const token = localStorage.getItem('token');
    if (!token) return null;

    try {
        const resp = await fetch(`${SIDEBAR_API_BASE}/users/me`, {
            headers: { Authorization: `Bearer ${token}` },
            cache: 'no-store'
        });
        if (!resp.ok) return null;

        const user = await resp.json();
        if (user.role) localStorage.setItem(USER_ROLE_KEY, user.role);
        if (user.id) localStorage.setItem('user_id', user.id);

        const flags = user.effective_feature_flags || user.feature_flags;
        if (flags) {
            const oldFlags = localStorage.getItem(USER_FEATURE_KEY);
            const newFlags = JSON.stringify(flags);
            localStorage.setItem(USER_FEATURE_KEY, newFlags);

            // Se as flags mudaram, reaplicar
            if (oldFlags !== newFlags) {
                applyFeatureFlags();
            }
        }
        return user;
    } catch (e) {
        console.warn('Falha ao carregar contexto do usuário', e);
        return null;
    }
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

            // Se for o submenu de Clientes, SEMPRE navega para clients.html (se não estiver lá)
            if (targetId === 'clientsSubmenu') {
                const currentPage = normalizePageName(window.location.pathname);
                const clientPages = ['clients.html', 'import_clients.html', 'backup_clients.html', 'messages.html'];
                if (!clientPages.includes(currentPage)) {
                    // Navega para clients.html
                    window.location.href = 'clients.html';
                    return; // Para a execução aqui pois vai navegar
                }
            }

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
    document.querySelectorAll('.sidebar-menu .sidebar-toggle').forEach((btn) => btn.classList.remove('active'));

    // Encontra o link correspondente à página atual
    let activeLink = null;
    document.querySelectorAll('.sidebar-menu a').forEach((link) => {
        const page = normalizePageName(link.getAttribute('href'));
        if (page && page === currentPage) activeLink = link;
    });

    // Caso especial: clients.html - marca o botão Clientes como ativo e abre o submenu
    const clientPages = ['clients.html', 'import_clients.html', 'backup_clients.html', 'messages.html'];
    if (clientPages.includes(currentPage)) {
        const clientsSubmenu = document.getElementById('clientsSubmenu');
        if (clientsSubmenu) {
            const group = clientsSubmenu.closest('.sidebar-group');
            const toggle = group ? group.querySelector('.sidebar-toggle') : null;
            clientsSubmenu.classList.add('is-open');
            if (toggle) {
                toggle.setAttribute('aria-expanded', 'true');
                // Marca o botão Clientes como ativo se estamos em clients.html
                if (currentPage === 'clients.html') {
                    toggle.classList.add('active');
                }
            }
        }
    }

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
    if (menu.querySelector('[data-feature-key="admin"]')) return;
    const link = document.createElement('a');
    link.href              = 'admin.html';
    link.className         = 'sidebar-link';
    link.dataset.featureKey = 'admin';
    link.dataset.roleRequired = 'super_admin';
    link.innerHTML         = '<span class="sidebar-icon">👑</span> Super Admin';
    menu.appendChild(link);
}

// ---------------------------------------------------------------------------
// 6. INICIALIZAÇÃO OTIMIZADA
// ---------------------------------------------------------------------------
function initSidebar() {
    // 1. Aplica flags IMEDIATAMENTE do cache local (muito rápido)
    setupSidebarAccordion();
    ensureSuperAdminLink();
    applyFeatureFlags();  // Usa cache do localStorage
    markActiveLink();

    // 2. Busca flags atualizadas do servidor em BACKGROUND (não bloqueia)
    fetchCurrentUserContext();  // Sem await - executa em paralelo
}

document.addEventListener('DOMContentLoaded', initSidebar);

// Disponibiliza para reuso após alterações no Admin
window.applyFeatureFlags = applyFeatureFlags;
