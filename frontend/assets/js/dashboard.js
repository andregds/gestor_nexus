/**
 * @file dashboard.js
 * @description Lógica do painel de controle, incluindo autenticação,
 * carregamento de dados, navegação e interação com a API de monitoramento, WhatsApp e Telegram.
 * @version 2.7
 */
// ============================
// CONFIGURAÇÃO GLOBAL
// ============================
const API_URL = (['localhost', '127.0.0.1'].includes(window.location.hostname))
    ? 'http://localhost:8000'
    : window.location.origin; // usa o host atual em produção

let whatsappPollingInterval = null;
let pollingAttempts = 0;
const MAX_POLLING_ATTEMPTS = 40; // 40 tentativas * 3s = 2 minutos

// --- ATUALIZAÇÃO: Variável para guardar dados do usuário logado ---
let currentUser = null;

// ============================
// INICIALIZAÇÃO
// ============================
document.addEventListener('DOMContentLoaded', () => {
    // Verifica se o token existe no localStorage
    const token = localStorage.getItem('token');
    if (!token) {
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
    loadUserInfo(); // Esta função agora também cuida das permissões da UI
    loadURLs();
    loadWhatsAppStatus();
    loadSettings();
    loadTelegramSettings();
    setInterval(loadURLs, 30000); // Atualiza os monitores a cada 30 segundos
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
    }, 10);

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
            // Retornar a resposta aqui é importante para que a cadeia de promessas não quebre
            return response;
        }

        return response;
    } catch (error) {
        console.error('Erro na requisição API:', error);
        showNotification('Erro de conexão com o servidor.', 'error');
        throw error;
    }
}

/**
 * Redireciona para a página de login e limpa o token.
 */
function redirectToLogin() {
    localStorage.removeItem('token');
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

// =================================================
// CONTROLE DE ACESSO E PERMISSÕES (LÓGICA CENTRAL)
// =================================================

/**
 * Carrega as informações do usuário, guarda em currentUser e aplica as permissões na UI.
 */
async function loadUserInfo() {
    try {
        const response = await apiFetch('/users/me');
        if (response.ok) {
            currentUser = await response.json(); // Armazena os dados do usuário

            // Persiste dados de role e feature flags para uso no sidebar.js
            if (currentUser.role) localStorage.setItem('user_role', currentUser.role);
            if (currentUser.feature_flags) localStorage.setItem('user_feature_flags', JSON.stringify(currentUser.feature_flags));

            const el = document.getElementById('userName');
            if (el) el.textContent = currentUser.name;

            // Exibe o "cargo" do usuário de forma mais amigável
            const roleEl = document.querySelector('.user-role');
            if (roleEl) {
                // Ex: 'super_admin' vira 'Super Admin'
                const friendlyRole = currentUser.role.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                roleEl.textContent = friendlyRole;
            }

            // ✅ APLICA AS REGRAS DE VISIBILIDADE NA INTERFACE
            applyUIPermissions();
            window.applyFeatureFlags && window.applyFeatureFlags();
        }
    } catch (error) {
        console.error('Erro ao carregar informações do usuário:', error);
    }
}

/**
 * Mostra ou esconde elementos da UI com base no role e permissões do usuário.
 * Esta é a função que faz a mágica de exibir os links corretos.
 */
function applyUIPermissions() {
    if (!currentUser) return;

    const { role, permissions } = currentUser;
    // Garantimos defaults liberando tudo quando as permissões não vierem do backend
    const safePermissions = {
        can_view_clients: permissions?.can_view_clients !== false,
        can_view_integrations: permissions?.can_view_integrations !== false,
        can_view_settings: permissions?.can_view_settings !== false,
    };

    const setElementVisibility = (selector, isVisible) => {
        const element = document.querySelector(selector);
        if (element) {
            element.style.display = isVisible ? '' : 'none';
        }
    };

    // Menus controlados por permissão (Dashboard sempre liberado)
    setElementVisibility('[data-permission-key="dashboard"]', true);
    setElementVisibility('[data-permission-key="clients"]', safePermissions.can_view_clients);
    setElementVisibility('[data-permission-key="integrations"]', safePermissions.can_view_integrations);
    setElementVisibility('[data-permission-key="settings"]', safePermissions.can_view_settings);

    // Menus por role
    setElementVisibility('[data-role-required="reseller"]', role === 'reseller' || role === 'super_admin');
    setElementVisibility('[data-role-required="super_admin"]', role === 'super_admin');
}


// ============================
// NAVEGAÇÃO (SPA)
// ============================
/**
 * Configura a navegação da barra lateral para alternar entre as seções de conteúdo.
 */
function setupSidebarNavigation() {
    const links = document.querySelectorAll('.sidebar-link');
    const sections = document.querySelectorAll('.content-section');
    const sidebar = document.getElementById('sidebar');
    const btnToggle = document.getElementById('btnToggleSidebar');

    links.forEach(link => {
        link.addEventListener('click', (e) => {
            const targetId = link.getAttribute('data-section');

            // Se o link não for para uma seão interna (ex: clients.html), deixa o navegador seguir
            if (!targetId) {
                return;
            }

            e.preventDefault(); // Previne a navegação apenas para links de seção

            links.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            sections.forEach(s => {
                s.style.display = (s.id === `section-${targetId}`) ? 'block' : 'none';
            });

            // Fecha a sidebar no mobile após clicar
            if (window.innerWidth <= 768 && sidebar) {
                sidebar.classList.remove('active');
            }
        });
    });

    if (btnToggle && sidebar) {
        btnToggle.addEventListener('click', () => sidebar.classList.toggle('active'));
    }
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
        // A notificação de erro já é mostrada pelo apiFetch
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
    const ping = url.response_time != null ? `${(url.response_time).toFixed(0)}ms` : '--'; // Corrigido para não multiplicar por 1000 se o backend já manda em ms
    const lastCheck = url.last_check ? new Date(url.last_check).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '--:--';

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
        // Erro já notificado pelo apiFetch
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
        // Erro já notificado pelo apiFetch
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
                <div id="connectedActions" style="display:none; margin-top: 1.5rem; gap: 1rem; flex-wrap: wrap;">
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
    const qrContainer = document.getElementById('qrCodeContainer');
    const qrWrapper = document.getElementById('qrCodeImageWrapper');
    qrContainer.style.display = 'block';
    qrWrapper.innerHTML = `<div class="spinner"></div><p style="margin-top:10px">Iniciando instância...</p>`;
    try {
        const response = await apiFetch('/whatsapp/connect', {
            method: 'POST',
            body: JSON.stringify({ number: "" }) // O número pode ser opcional dependendo da sua API
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
        // Erro já notificado pelo apiFetch
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
            loadWhatsAppStatus();
        } else {
            const data = await response.json();
            showNotification(data.detail || "Falha ao desconectar.", 'error');
        }
    } catch (e) {
        // Erro já notificado pelo apiFetch
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
        // Erro já notificado pelo apiFetch
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
        // Reutiliza o currentUser se já estiver carregado
        if (currentUser) {
            const tokenInput = document.getElementById('telegramToken');
            if (tokenInput) tokenInput.value = currentUser.telegram_token || '';
            const chatInput = document.getElementById('telegramChatId');
            if (chatInput) chatInput.value = currentUser.telegram_chat_id || '';
            return;
        }
        // Fallback caso seja chamado antes
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
        // Erro já notificado pelo apiFetch
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
        // Erro já notificado pelo apiFetch
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
        // Reutiliza o currentUser se já estiver carregado
        if (currentUser) {
            const phoneInput = document.getElementById('settingsPhone');
            if (phoneInput) phoneInput.value = currentUser.whatsapp_number || '';
            const checkDown = document.getElementById('checkNotifyDown');
            if (checkDown) checkDown.checked = currentUser.notify_when_down;
            const checkUp = document.getElementById('checkNotifyUp');
            if (checkUp) checkUp.checked = currentUser.notify_when_up;
            const checkSlow = document.getElementById('checkNotifySlow');
            if (checkSlow) checkSlow.checked = currentUser.notify_when_slow;
            return;
        }
        // Fallback
        const response = await apiFetch('/users/me');
        if (response.ok) {
            const user = await response.json();
            const phoneInput = document.getElementById('settingsPhone');
            if (phoneInput) phoneInput.value = user.whatsapp_number || '';
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
    const phone = document.getElementById('settingsPhone')?.value.replace(/\D/g, '') || '';
    const notifyDown = document.getElementById('checkNotifyDown')?.checked ?? true;
    const notifyUp = document.getElementById('checkNotifyUp')?.checked ?? true;
    const notifySlow = document.getElementById('checkNotifySlow')?.checked ?? false;

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
            loadUserInfo(); // Recarrega os dados do usuário para garantir consistência
        } else {
            showNotification("Erro ao salvar configurações.", 'error');
        }
    } catch (error) {
        // Erro já notificado pelo apiFetch
    }
}

// ==================================================
// ZONA DE PERIGO (BACKUP/IMPORT PAGE)
// ==================================================

/**
 * Abre o modal de confirmação para apagar todos os clientes.
 */
function openDeleteAllClientsModal() {
    const modal = document.getElementById('deleteAllClientsModal');
    if (modal) {
        modal.style.display = 'flex'; // Usar flex para centralizar
    }
}

/**
 * Fecha o modal de confirmação para apagar todos os clientes.
 */
function closeDeleteAllClientsModal() {
    const modal = document.getElementById('deleteAllClientsModal');
    if (modal) {
        modal.style.display = 'none';
        const passwordInput = document.getElementById('passwordConfirmation');
        if (passwordInput) {
            passwordInput.value = ''; // Limpa a senha ao fechar
        }
    }
}

/**
 * Confirma e executa a exclusão de todos os clientes.
 */
async function confirmDeleteAllClients() {
    const passwordInput = document.getElementById('passwordConfirmation');
    const password = passwordInput.value;

    if (!password) {
        showNotification("Por favor, digite sua senha para confirmar.", 'error');
        return;
    }

    try {
        const response = await apiFetch('/clients/delete-all', {
            method: 'DELETE',
            body: JSON.stringify({ password: password })
        });

        if (response.ok) {
            showNotification("Limpeza de banco de dados concluída com sucesso!", 'success');
            closeDeleteAllClientsModal();
            setTimeout(() => {
                window.location.href = 'clients.html';
            }, 3000);
        } else {
            const error = await response.json();
            showNotification(error.detail || "Senha incorreta ou falha ao apagar.", 'error');
        }
    } catch (error) {
        console.error('Erro ao apagar todos os clientes:', error);
        showNotification("Ocorreu um erro de comunicação.", 'error');
    }
}


/**
 * Abre o modal de confirmação para o reset de fábrica.
 */
function openFactoryResetModal() {
    const modal = document.getElementById('factoryResetModal');
    if (modal) {
        modal.style.display = 'flex';
    }
}

/**
 * Fecha o modal de confirmação para o reset de fábrica.
 */
function closeFactoryResetModal() {
    const modal = document.getElementById('factoryResetModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Confirma e executa o reset de fábrica.
 */
async function confirmFactoryReset() {
    // Lógica para o reset de fábrica
    showNotification("Função de reset de fábrica ainda não implementada.", 'info');
    closeFactoryResetModal();
}
