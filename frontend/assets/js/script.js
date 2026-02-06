// Funções utilitárias globais

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('pt-BR');
}

function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = '<p class="text-muted">Carregando...</p>';
    }
}

function showError(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `<p class="text-danger">${message}</p>`;
    }
}

// Verifica se está autenticado
function checkAuth() {
    const token = localStorage.getItem('token');
    const publicPages = ['index.html', 'login.html', 'register.html', ''];
    const currentPage = window.location.pathname.split('/').pop();

    if (!token && !publicPages.includes(currentPage)) {
        window.location.href = 'login.html';
    }

    if (token && publicPages.includes(currentPage) && currentPage !== '') {
        window.location.href = 'dashboard.html';
    }
}

// Executa verificação ao carregar
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
});
