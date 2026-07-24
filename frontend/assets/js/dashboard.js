/**
 * @file dashboard.js
 * @description Lógica do painel de controle, incluindo autenticação,
 * carregamento de dados, navegação e interação com a API de monitoramento, WhatsApp e Telegram.
 * @version 2.6
 */
// ============================
// CONFIGURAÇÃO GLOBAL
// ============================
const API_URL = (() => {
    if (window.location.protocol === 'file:') {
        return 'http://127.0.0.1:8000';
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

    if (['localhost', '127.0.0.1'].includes(window.location.hostname)) {
        return 'http://127.0.0.1:8000';
    }

    return window.location.origin;
})();
let whatsappPollingInterval = null;
let pollingAttempts = 0;
const MAX_POLLING_ATTEMPTS = 40; // 40 tentativas * 3s = 2 minutos
const DASHBOARD_SECTIONS = new Set(['dashboard', 'whatsapp', 'telegram', 'settings']);

// ============================
// INICIALIZAÇÃO
// ============================
document.addEventListener('DOMContentLoaded', () => {
    // A verificação de auth agora é feita pelo apiFetch,
    // mas mantemos uma inicial para o primeiro carregamento.
    if (!localStorage.getItem('token')) {
        redirectToLogin();
        return;
    }
    loadPage();
});

/**
 * Função principal para carregar todos os componentes da página.
 */
function loadPage() {
    setupSidebarNavigation();
    loadUserInfo();
    loadURLs();
    loadWhatsAppStatus();
    loadSettings();
    loadTelegramSettings();
    setInterval(loadURLs, 30000);
}

// ============================
// UTILITÁRIOS GERAIS
// ============================
/**
 * Exibe uma notificação temporária na tela.
 * @param {string} message A mensagem a ser exibida.
 * @param {'success'|'error'|'info'} type O tipo da notificação.
 */
function showNotification(message, type = 'info') {
    const notificationContainer = document.getElementById('notificationContainer') || (() => {
        const div = document.createElement('div');
        div.id = 'notificationContainer';
        Object.assign(div.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            zIndex: '1000',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px'
        });
        document.body.appendChild(div);
        return div;
    })();

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    Object.assign(notification.style, {
        padding: '10px 20px',
        borderRadius: '5px',
        color: 'white',
        fontWeight: 'bold',
        boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
        opacity: '0',
        transition: 'opacity 0.3s ease-in-out, transform 0.3s ease-in-out',
        transform: 'translateY(-20px)'
    });

    if (type === 'success') notification.style.backgroundColor = '#4CAF50';
    if (type === 'error') notification.style.backgroundColor = '#f44336';
    if (type === 'info') notification.style.backgroundColor = '#2196F3';

    notificationContainer.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateY(0)';
    }, 10); // Pequeno delay para a transição funcionar

    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateY(-20px)';
        notification.addEventListener('transitionend', () => notification.remove());
    }, 5000);
}

/**
 * Wrapper para fetch API que inclui o token de autenticação e lida com erros.
 * @param {string} path O caminho da API.
 * @param {object} options Opções para a requisição fetch.
 * @returns {Promise<Response>} A resposta da requisição.
 */
async function apiFetch(path, options = {}) {
    const token = localStorage.getItem('token');
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(`${API_URL}${path}`, {
            ...options,
            headers: headers
        });

        if (response.status === 401) {
            showNotification("Sessão expirada ou não autorizada. Faça login novamente.", 'error');
            redirectToLogin();
            return response; // Retorna a resposta 401 para que o chamador possa lidar com ela se necessário
        }

        return response;
    } catch (error) {
        console.error('Erro na requisição API:', error);
        throw error; // Re-lança o erro para ser tratado pela função chamadora
    }
}

/**
 * Redireciona para a página de login e limpa o token.
 */
function redirectToLogin() {
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_feature_flags');
    window.location.href = 'login.html';
}

/**
 * Desloga o usuário e redireciona para a página de login.
 */
function logout() {
    if (confirm("Tem certeza que deseja sair?")) {
        redirectToLogin();
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

    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        overlay.setAttribute('aria-hidden', 'true');
        document.body.appendChild(overlay);
    }

    return { sidebar, overlay };
}

/**
 * Carrega as informações do usuário logado e atualiza o nome no cabeçalho.
 */
async function loadUserInfo() {
    try {
        const response = await apiFetch('/users/me');
        if (response.ok) {
            const user = await response.json();
            const role = user.role || 'user';
            const roleLabel = formatRoleLabel(role);
            const name = user.name || 'Usuário';

            localStorage.setItem('user_role', role);

            document.querySelectorAll('#userName').forEach((element) => {
                element.textContent = name;
            });

            document.querySelectorAll('.user-role').forEach((element) => {
                element.textContent = roleLabel;
            });
        }
    } catch (error) {
        console.error('Erro ao carregar informações do usuário:', error);
    }
}

// ============================
// NAVEGAÇÃO (CORRIGIDA)
// ============================
/**
 * Configura a navegação da barra lateral para alternar entre as seções de conteúdo.
 */
function getDashboardSectionFromLocation() {
    const hash = (window.location.hash || '').replace(/^#/, '');
    return DASHBOARD_SECTIONS.has(hash) ? hash : 'dashboard';
}

function syncDashboardUrl(targetId) {
    const nextUrl = `${window.location.pathname}${window.location.search}${targetId === 'dashboard' ? '' : `#${targetId}`}`;
    window.history.replaceState(null, '', nextUrl);
}

function activateDashboardSection(targetId, sections) {
    const nextSection = DASHBOARD_SECTIONS.has(targetId) ? targetId : 'dashboard';
    const sectionList = sections || document.querySelectorAll('.content-section');

    sectionList.forEach((section) => {
        section.style.display = section.id === `section-${nextSection}` ? 'block' : 'none';
    });

    if (typeof window.markSidebarActiveLink === 'function') {
        window.markSidebarActiveLink();
    }
}

function setupSidebarNavigation() {
    const links = document.querySelectorAll('.sidebar-link');
    const sections = document.querySelectorAll('.content-section');
    const shell = ensureSidebarShell();
    const sidebar = shell ? shell.sidebar : null;
    const overlay = shell ? shell.overlay : null;
    const btnToggle = document.getElementById('btnToggleSidebar');
    const btnToggleDesktop = document.getElementById('btnToggleSidebarDesktop');
    const currentPage = window.location.pathname.split('/').pop() || 'dashboard.html';

    links.forEach(link => {
        link.addEventListener('click', (e) => {
            const targetId = link.getAttribute('data-section');
            const href = link.getAttribute('href') || '';
            const hrefPage = href.split('#')[0].split('/').pop();
            const hrefHash = href.includes('#') ? href.split('#')[1] : '';

            if (targetId || (currentPage === 'dashboard.html' && hrefPage === 'dashboard.html')) {
                e.preventDefault();
                const nextSection = targetId || hrefHash || 'dashboard';
                syncDashboardUrl(nextSection);
                activateDashboardSection(nextSection, sections);

                if (window.innerWidth <= 768 && sidebar) {
                    setSidebarOpen(sidebar, overlay, false);
                }
            }
        });
    });

    if (currentPage === 'dashboard.html') {
        activateDashboardSection(getDashboardSectionFromLocation(), sections);
        window.addEventListener('hashchange', () => activateDashboardSection(getDashboardSectionFromLocation(), sections));
    }

    if (btnToggle && sidebar) {
        btnToggle.addEventListener('click', () => {
            const shouldOpen = !sidebar.classList.contains('active');
            setSidebarOpen(sidebar, overlay, shouldOpen);
        });
    }

    if (btnToggleDesktop && sidebar) {
        btnToggleDesktop.addEventListener('click', () => {
            const shouldOpen = !sidebar.classList.contains('active');
            setSidebarOpen(sidebar, overlay, shouldOpen);
        });
    }

    if (overlay && sidebar) {
        overlay.addEventListener('click', () => setSidebarOpen(sidebar, overlay, false));
    }

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && sidebar) {
            setSidebarOpen(sidebar, overlay, false);
        }
    });

    window.addEventListener('resize', () => {
        if (window.innerWidth > 768 && sidebar) {
            setSidebarOpen(sidebar, overlay, false);
        }
    });
}

// ============================
// MONITORAMENTO (DASHBOARD)
// ============================
/**
 * Carrega e renderiza a lista de URLs monitoradas.
 */
async function loadURLs() {
    const urlsList = document.getElementById('urlsList');
    if (!urlsList) return;
    try {
        const response = await apiFetch('/urls');
        if (!response.ok) throw new Error('Falha ao buscar URLs');
        const urls = await response.json();
        updateStats(urls);
        if (urls.length === 0) {
            urlsList.innerHTML = `<div class="empty-state">
                <p>Nenhum monitoramento ativo. Adicione uma URL acima.</p>
            </div>`;
            return;
        }
        urlsList.innerHTML = urls.map(url => renderURLCard(url)).join('');
    } catch (error) {
        console.error('Erro ao carregar URLs:', error);
        showNotification('Não foi possível atualizar as URLs.', 'error');
    }
}

/**
 * Gera o HTML para um único card de URL.
 * @param {object} url O objeto da URL vindo da API.
 * @returns {string} O template HTML do card.
 */
function renderURLCard(url) {
    const statusClass = url.status === 'UP' ? 'status-up' : (url.status === 'DOWN' ? 'status-down' : 'status-warning');
    const statusLabel = url.status === 'UP' ? 'ONLINE' : (url.status === 'DOWN' ? 'OFFLINE' : 'ALERTA');
    const ping = url.response_time ? `${(url.response_time * 1000).toFixed(0)}ms` : '--';
    const lastCheck = url.last_check ? new Date(url.last_check).toLocaleTimeString() : '--:--';
    return `
    <article class="url-card ${statusClass}">
        <div class="url-header">
            <div>
                <div class="url-title" title="${url.nickname || ''}">${url.nickname || 'Servidor'}</div>
                <a href="${url.url}" target="_blank" class="url-link">${url.url}</a>
            </div>
            <span class="status-badge">${statusLabel}</span>
        </div>
        <div class="url-metrics">
            <div class="metric"><span class="metric-label">Latência</span><span class="metric-value">${ping}</span></div>
            <div class="metric"><span class="metric-label">HTTP Code</span><span class="metric-value">${url.http_code || '---'}</span></div>
            <div class="metric"><span class="metric-label">Última Checagem</span><span class="metric-value">${lastCheck}</span></div>
            <div class="metric"><span class="metric-label">IP</span><span class="metric-value">${url.ip_address || '---'}</span></div>
        </div>
        <div class="url-actions">
            <button class="btn-icon" onclick="deleteURL(${url.id})" title="Remover Monitoramento">🗑️</button>
        </div>
    </article>`;
}

/**
 * Atualiza as estatísticas gerais (Online, Offline, etc.).
 * @param {Array} urls A lista de URLs.
 */
function updateStats(urls) {
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };
    setVal('statsOnline', urls.filter(u => u.status === 'UP').length);
    setVal('statsOffline', urls.filter(u => u.status === 'DOWN').length);
    setVal('statsWarning', urls.filter(u => u.status === 'WARNING').length);
    setVal('statsTotal', urls.length);
}

/**
 * Adiciona uma nova URL para monitoramento.
 */
async function addURL() {
    const urlInput = document.getElementById('newUrl');
    const nameInput = document.getElementById('newName');
    if (!urlInput.value || !urlInput.checkValidity()) {
        showNotification("Por favor, insira uma URL válida.", 'error');
        return;
    }
    try {
        const response = await apiFetch('/urls', {
            method: 'POST',
            body: JSON.stringify({
                url: urlInput.value,
                nickname: nameInput.value || '',
            })
        });
        if (response.ok) {
            showNotification("URL adicionada com sucesso!", 'success');
            urlInput.value = '';
            nameInput.value = '';
            loadURLs();
        } else {
            const err = await response.json();
            showNotification(`Erro: ${err.detail}`, 'error');
        }
    } catch (e) {
        showNotification("Erro de conexão ao adicionar URL.", 'error');
    }
}

/**
 * Deleta uma URL monitorada.
 * @param {number} id O ID da URL a ser deletada.
 */
async function deleteURL(id) {
    if (!confirm("Tem certeza que deseja remover este monitoramento?")) return;
    try {
        const response = await apiFetch(`/urls/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showNotification("Monitoramento removido.", 'info');
            loadURLs();
        } else {
            showNotification("Falha ao remover monitoramento.", 'error');
        }
    } catch (e) {
        showNotification("Erro de conexão ao remover URL.", 'error');
    }
}

// ============================
// WHATSAPP (EVOLUTION API)
// ============================
/**
 * Gera o template HTML inicial para a seção do WhatsApp.
 * @returns {string}
 */
function whatsappTemplate() {
    return `
        <div class="page-header">
            <div class="page-title">
                <h2>Integração WhatsApp</h2>
                <p>Gateway de notificações via Evolution API.</p>
            </div>
        </div>
        <div class="card">
            <h3 style="margin-bottom: 1.5rem; color: var(--primary);">Status da Conexão</h3>
            <div id="connectionStateArea">
                <div id="whatsappStatusContainer" class="whatsapp-status-box">
                    <div class="spinner"></div>
                    <div>Verificando status do gateway...</div>
                </div>
                <div id="connectForm" style="display:none; margin-top: 2rem; text-align: center;">
                    <p style="color: var(--text-muted); margin-bottom: 1rem;">Clique abaixo para gerar um novo QR Code e conectar sua instância.</p>
                    <button class="btn btn-primary" onclick="connectWhatsApp()">🔗 Gerar QR Code</button>
                </div>
                <div id="connectedActions" style="display:none; margin-top: 1.5rem; gap: 1rem;">
                    <button class="btn btn-secondary" onclick="testWhatsAppNotification()">🔔 Enviar Teste</button>
                    <button class="btn btn-danger" onclick="disconnectWhatsApp()">🔴 Desconectar Instância</button>
                </div>
            </div>
            <div id="qrCodeContainer" class="qr-container" style="display: none;">
                <h4 style="color: var(--primary); margin-bottom: 1rem;">Escaneie para Conectar</h4>
                <div id="qrCodeImageWrapper" style="min-height: 260px; display: flex; align-items: center; justify-content: center;">
                    <div class="spinner"></div>
                </div>
                <p style="margin-top: 1rem; color: var(--text-muted);">Abra o WhatsApp > Aparelhos Conectados > Conectar Aparelho</p>
            </div>
        </div>
    `;
}

/**
 * Carrega o status da conexão do WhatsApp e atualiza a UI.
 */
async function loadWhatsAppStatus() {
    const section = document.getElementById('section-whatsapp');
    if (!section) return;
    if (!document.getElementById('whatsappStatusContainer')) {
        section.innerHTML = whatsappTemplate();
    }
    try {
        const response = await apiFetch('/whatsapp/status');
        const data = await response.json();
        updateWhatsAppUI(data);
    } catch (error) {
        console.error("Erro ao verificar status do WhatsApp:", error);
        const statusContainer = document.getElementById('whatsappStatusContainer');
        if (statusContainer) statusContainer.innerHTML = `<div style="color: var(--danger);">Erro de comunicação com a API.</div>`;
    }
}

/**
 * Atualiza a interface do WhatsApp com base nos dados recebidos.
 * @param {object} data Os dados de status da API.
 */
function updateWhatsAppUI(data) {
    const statusContainer = document.getElementById('whatsappStatusContainer');
    const connectForm = document.getElementById('connectForm');
    const connectedActions = document.getElementById('connectedActions');
    const qrContainer = document.getElementById('qrCodeContainer');
    if (data.connected) {
        statusContainer.innerHTML = `
            <div class="status-indicator success">
                <span style="font-size: 1.5rem;">✅</span>
                <div>
                    <div style="color: var(--primary);">Gateway Online</div>
                    <div style="font-size: 0.8rem; color: var(--text-muted);">Instância: ${data.instance_name || 'Ativa'}</div>
                </div>
            </div>`;
        connectForm.style.display = 'none';
        connectedActions.style.display = 'flex';
        qrContainer.style.display = 'none';
        stopWhatsAppPolling();
    } else {
        statusContainer.innerHTML = `
            <div class="status-indicator error">
                <span style="font-size: 1.5rem;">🔴</span>
                <div>Gateway Offline</div>
            </div>`;
        connectForm.style.display = 'block';
        connectedActions.style.display = 'none';
        if (data.qr_code) {
            showQRCode(data.qr_code);
            startWhatsAppPolling();
        }
    }
}

/**
 * Inicia o processo de conexão, solicitando um QR Code ao backend.
 */
async function connectWhatsApp() {
    // REMOVIDO: O prompt que pedia o número
    const qrContainer = document.getElementById('qrCodeContainer');
    const qrWrapper = document.getElementById('qrCodeImageWrapper');
    qrContainer.style.display = 'block';
    qrWrapper.innerHTML = `<div class="spinner"></div><p style="margin-top:10px">Iniciando instância...</p>`;
    try {
        const response = await apiFetch('/whatsapp/connect', {
            method: 'POST',
            // Enviamos um objeto vazio ou com número nulo, já que o backend agora aceita
            body: JSON.stringify({ number: "" })
        });
        const data = await response.json();
        if (response.ok) {
            if (data.qr_code) {
                showQRCode(data.qr_code);
            } else {
                qrWrapper.innerHTML = `<div class="spinner"></div><p style="margin-top:10px">Aguardando QR Code...</p>`;
            }
            startWhatsAppPolling();
        } else {
            qrContainer.style.display = 'none';
            showNotification(`Erro: ${data.detail || "Falha ao criar instância"}`, 'error');
        }
    } catch (error) {
        qrContainer.style.display = 'none';
        showNotification("Erro de conexão ao tentar conectar.", 'error');
    }
}

/**
 * Exibe a imagem do QR Code na tela.
 * @param {string} base64Code O código base64 da imagem do QR Code.
 */
function showQRCode(base64Code) {
    const qrContainer = document.getElementById('qrCodeContainer');
    const qrWrapper = document.getElementById('qrCodeImageWrapper');
    if (!qrContainer || !qrWrapper) return;
    qrContainer.style.display = 'block';
    const src = base64Code.startsWith('data:') ? base64Code : `data:image/png;base64,${base64Code}`;
    qrWrapper.innerHTML = `<img src="${src}" alt="QR Code para conexão com WhatsApp" class="qrcode-image">`;
}

/**
 * Inicia a verificação periódica (polling) do status da conexão do WhatsApp.
 */
function startWhatsAppPolling() {
    if (whatsappPollingInterval) clearInterval(whatsappPollingInterval);
    pollingAttempts = 0;
    console.log("Iniciando Polling do status do WhatsApp...");
    whatsappPollingInterval = setInterval(async () => {
        pollingAttempts++;
        if (pollingAttempts > MAX_POLLING_ATTEMPTS) {
            stopWhatsAppPolling();
            const qrWrapper = document.getElementById('qrCodeImageWrapper');
            if (qrWrapper) qrWrapper.innerHTML = `<p style="color: var(--danger)">Tempo limite excedido. Tente gerar um novo QR Code.</p>`;
            return;
        }
        try {
            const response = await apiFetch('/whatsapp/status');
            if (!response.ok) return;
            const data = await response.json();
            console.log(`Polling #${pollingAttempts}:`, data);
            if (data.connected) {
                stopWhatsAppPolling();
                document.getElementById('qrCodeContainer').style.display = 'none';
                loadWhatsAppStatus();
                showNotification("WhatsApp conectado com sucesso!", 'success');
            } else if (data.qr_code) {
                showQRCode(data.qr_code);
            }
        } catch (e) {
            console.error("Erro no polling:", e);
        }
    }, 3000);
}

/**
 * Para a verificação periódica do status do WhatsApp.
 */
function stopWhatsAppPolling() {
    if (whatsappPollingInterval) {
        clearInterval(whatsappPollingInterval);
        whatsappPollingInterval = null;
        console.log("Polling do WhatsApp interrompido.");
    }
}

/**
 * Desconecta a instância do WhatsApp.
 */
async function disconnectWhatsApp() {
    if (!confirm("Deseja realmente desconectar a instância do WhatsApp? Isso parará o envio de notificações.")) {
        return;
    }
    try {
        const response = await apiFetch('/whatsapp/disconnect', { method: 'POST' });
        if (response.ok) {
            showNotification("Instância desconectada com sucesso.", 'info');
            // Recarrega o status para mostrar o botão de conectar novamente
            loadWhatsAppStatus();
        } else {
            const data = await response.json();
            showNotification(data.detail || "Falha ao desconectar.", 'error');
        }
    } catch (e) {
        console.error(e);
        showNotification("Erro de conexão ao desconectar.", 'error');
    }
}

/**
 * Envia uma notificação de teste para um número informado na hora.
 */
async function testWhatsAppNotification() {
    const number = prompt("Digite o número para receber o teste (DDI+DDD+Número):\nEx: 5511999999999");
    if (!number) return;
    try {
        const response = await apiFetch('/whatsapp/test-notification', {
            method: 'POST',
            body: JSON.stringify({ number: number })
        });
        const data = await response.json();
        if (response.ok) {
            showNotification(data.message || "Teste enviado!", 'success');
        } else {
            showNotification(data.detail || 'Falha no envio.', 'error');
        }
    } catch (error) {
        console.error(error);
        showNotification('Erro de conexão ao enviar teste.', 'error');
    }
}

// ============================
// TELEGRAM
// ============================
/**
 * Carrega as configurações do Telegram.
 */
async function loadTelegramSettings() {
    try {
        const response = await apiFetch('/users/me');
        if (response.ok) {
            const user = await response.json();
            const tokenInput = document.getElementById('telegramToken');
            if (tokenInput) tokenInput.value = user.telegram_token || '';
            const chatInput = document.getElementById('telegramChatId');
            if (chatInput) chatInput.value = user.telegram_chat_id || '';
        }
    } catch (error) {
        console.error("Erro ao carregar Telegram:", error);
    }
}

/**
 * Salva as configurações do Telegram.
 */
async function saveTelegramSettings() {
    const token = document.getElementById('telegramToken').value.trim();
    const chatId = document.getElementById('telegramChatId').value.trim();

    // Validação: Ou preenche tudo, ou limpa tudo. Não pode deixar um só preenchido.
    if ((token && !chatId) || (!token && chatId)) {
        showNotification("Para ativar, preencha tanto o Token quanto o Chat ID.", 'error');
        return;
    }

    try {
        const response = await apiFetch('/users/me/settings', {
            method: 'PATCH',
            body: JSON.stringify({
                telegram_token: token,
                telegram_chat_id: chatId
            })
        });
        if (response.ok) {
            showNotification("Telegram configurado com sucesso!", 'success');
        } else {
            showNotification("Erro ao salvar Telegram.", 'error');
        }
    } catch (error) {
        console.error(error);
        showNotification("Erro de conexão.", 'error');
    }
}

/**
 * Envia uma mensagem de teste para o Telegram.
 */
async function testTelegram() {
    showNotification("Enviando teste...", 'info');

    try {
        const response = await apiFetch('/users/me/telegram/test', {
            method: 'POST'
        });

        if (response.ok) {
            showNotification("Teste enviado! Verifique seu Telegram.", 'success');
        } else {
            const err = await response.json();
            showNotification(`Erro: ${err.detail}`, 'error');
        }

    } catch (error) {
        console.error(error);
        showNotification("Erro de conexão ao enviar teste.", 'error');
    }
}

// ============================
// CONFIGURAÇÕES (SETTINGS)
// ============================
/**
 * Carrega as configurações atuais do usuário e preenche o formulário.
 */
async function loadSettings() {
    try {
        const response = await apiFetch('/users/me'); // Reutiliza a rota /me que agora traz os flags
        if (response.ok) {
            const user = await response.json();
            // Preenche telefone
            const phoneInput = document.getElementById('settingsPhone');
            if (phoneInput) phoneInput.value = user.whatsapp_number || '';
            // Preenche checkboxes
            const checkDown = document.getElementById('checkNotifyDown');
            if (checkDown) checkDown.checked = user.notify_when_down;
            const checkUp = document.getElementById('checkNotifyUp');
            if (checkUp) checkUp.checked = user.notify_when_up;
            const checkSlow = document.getElementById('checkNotifySlow');
            if (checkSlow) checkSlow.checked = user.notify_when_slow;
        }
    } catch (error) {
        console.error("Erro ao carregar configurações:", error);
    }
}

/**
 * Envia as novas configurações para o backend.
 */
async function saveSettings() {
    const phoneInput = document.getElementById('settingsPhone');
    const phone = phoneInput ? phoneInput.value.replace(/\D/g, '') : ''; // Remove não-números
    const checkDown = document.getElementById('checkNotifyDown');
    const notifyDown = checkDown ? checkDown.checked : true;
    const checkUp = document.getElementById('checkNotifyUp');
    const notifyUp = checkUp ? checkUp.checked : true;
    const checkSlow = document.getElementById('checkNotifySlow');
    const notifySlow = checkSlow ? checkSlow.checked : false;
    // Validação básica de telefone se preenchido
    if (phone && phone.length < 10) {
        showNotification("Número de telefone parece inválido.", 'error');
        return;
    }
    try {
        const response = await apiFetch('/users/me/settings', {
            method: 'PATCH',
            body: JSON.stringify({
                whatsapp_number: phone,
                notify_when_down: notifyDown,
                notify_when_up: notifyUp,
                notify_when_slow: notifySlow
            })
        });
        if (response.ok) {
            showNotification("Configurações salvas com sucesso!", 'success');
            // Atualiza info do usuário globalmente se necessário
            loadUserInfo();
        } else {
            showNotification("Erro ao salvar configurações.", 'error');
        }
    } catch (error) {
        console.error(error);
        showNotification("Erro de conexão ao salvar.", 'error');
    }
}