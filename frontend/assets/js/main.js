// frontend/assets/js/main.js

const API_URL = 'http://127.0.0.1:8000';

/**
 * Função genérica para chamadas à API.
 * Gerencia automaticamente o token e erros padrão.
 */
async function fetchAPI(endpoint, options = {}) {
    const token = localStorage.getItem('token');

    const defaultOptions = {
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    };

    const mergedOptions = {
        ...defaultOptions,
        ...options,
        headers: {...defaultOptions.headers, ...options.headers}
    };

    const response = await fetch(`${API_URL}${endpoint}`, mergedOptions);

    if (!response.ok) {
         const errorData = await response.json().catch(() => ({ detail: `Erro ${response.status}` }));
         throw new Error(errorData.detail);
    }

    if (response.status === 204) {
        return null;
    }
    return response.json();
}

/**
 * Carrega as informações do usuário na Sidebar (Nome, Role, Limite).
 */
async function loadSidebarInfo() {
    const token = localStorage.getItem('token');
    if (!token) return null;

    try {
        const response = await fetch(`${API_URL}/users/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.ok) {
            const user = await response.json();

            const nameEl = document.getElementById('userName');
            const roleEl = document.getElementById('userRole');
            const creditsEl = document.getElementById('userCredits');

            if (nameEl) nameEl.textContent = user.name;
            if (roleEl) roleEl.textContent = user.role;

            // Lógica de exibição do limite
            if (creditsEl) {
                if (user.role === 'super_admin') {
                    creditsEl.textContent = "Limite: Ilimitado";
                    creditsEl.classList.add('unlimited'); // Adiciona classe para estilizar via CSS
                    creditsEl.style.backgroundColor = "#dcfce7"; // Fallback
                    creditsEl.style.color = "#166534"; // Fallback
                } else {
                    creditsEl.textContent = `Limite: ${user.client_limit}`;
                    creditsEl.classList.remove('unlimited');
                    creditsEl.style.backgroundColor = "#e0f2fe"; // Fallback
                    creditsEl.style.color = "#0369a1"; // Fallback
                }
            }
            return user;
        }
    } catch (error) {
        console.error("Erro ao carregar sidebar:", error);
    }
    return null;
}

function logout() {
    if(confirm("Deseja sair?")) {
        localStorage.removeItem('token');
        window.location.href = 'login.html';
    }
}

// --- NOVO: Executa automaticamente ao carregar a página ---
document.addEventListener('DOMContentLoaded', () => {
    // Verifica se não é a página de login para evitar erros
    if (!window.location.pathname.includes('login.html')) {
        loadSidebarInfo();
    }
});