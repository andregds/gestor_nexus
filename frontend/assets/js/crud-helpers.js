function apiFetch(path, options = {}) {
    const token = localStorage.getItem('token');
    const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(`${API_URL}${path}`, Object.assign({}, options, { headers }));
}

function notify(message, type) {
    if (typeof showNotification === 'function') {
        showNotification(message, type);
    } else {
        alert(message);
    }
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function encodeItem(item) {
    return btoa(unescape(encodeURIComponent(JSON.stringify(item))));
}

function decodeItem(encoded) {
    return JSON.parse(decodeURIComponent(escape(atob(encoded))));
}

function money(value) {
    const numeric = Number(value || 0);
    return numeric.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_feature_flags');
    window.location.href = 'login.html';
}
