// frontend/assets/js/clients.js

document.addEventListener('DOMContentLoaded', () => {
    loadClients();
});

function openTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    event.currentTarget.classList.add('active');
}

async function addClient(event) {
    event.preventDefault();

    const clientData = {
        name: document.getElementById('cName').value,
        login: document.getElementById('cLogin').value,
        server_name: document.getElementById('cServer').value,
        email: document.getElementById('cEmail') ? document.getElementById('cEmail').value.trim() : '',
        whatsapp: document.getElementById('cWhatsapp').value.replace(/\D/g, ''),
        expiration_date: document.getElementById('cDate').value,
        notes: document.getElementById('cNotes').value,
        m3u8_url: document.getElementById('cM3u8').value,
        notify_downtime: document.getElementById('cNotifyDowntime').checked,
        reminder_enabled: document.getElementById('cReminderEnabled').checked,
        reminder_days_before: document.getElementById('cReminderDays').value,
        notify_after_expiration: document.getElementById('cNotifyAfter').checked
    };

    try {
        const response = await apiFetch('/clients/', {
            method: 'POST',
            body: JSON.stringify(clientData)
        });

        if (response.ok) {
            showNotification('Cliente cadastrado com sucesso!', 'success');
            document.getElementById('clientForm').reset();
            loadClients();
        } else {
            const err = await response.json();
            showNotification('Erro: ' + (err.detail || 'Falha ao salvar'), 'error');
        }
    } catch (error) {
        console.error(error);
        showNotification('Erro de conexão.', 'error');
    }
}

async function loadClients() {
    const tbody = document.getElementById('clientsList');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center">Carregando...</td></tr>';

    try {
        const response = await apiFetch('/clients/');
        const clients = await response.json();

        if (clients.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: #999;">Nenhum cliente cadastrado.</td></tr>';
            return;
        }

        tbody.innerHTML = clients.map(c => {
            // Formata data
            const dateObj = new Date(c.expiration_date);
            const dateStr = dateObj.toLocaleDateString('pt-BR');

            // Verifica se está vencido para mudar a cor
            const today = new Date();
            const isExpired = dateObj < today;
            const badgeClass = isExpired ? 'badge-expiring' : 'badge-date';

            return `
                <tr>
                    <td>
                        <div style="font-weight:600">${c.name}</div>
                        <div style="font-size:0.8rem; color:#666">👤 ${c.login}</div>
                    </td>
                    <td>${c.whatsapp}</td>
                    <td><span class="${badgeClass}">${dateStr}</span></td>
                    <td>${c.server_name || '-'}</td>
                    <td>
                        ${c.notify_downtime ? '✅ Quedas' : '❌ Quedas'}<br>
                        ${c.reminder_enabled ? '✅ Cobrança' : '❌ Cobrança'}
                    </td>
                    <td>
                        <button class="btn-icon" onclick="sendMsg(${c.id})" title="Enviar Mensagem">💬</button>
                        <button class="btn-icon" onclick="deleteClient(${c.id})" title="Excluir">🗑️</button>
                    </td>
                </tr>
            `;
        }).join('');

    } catch (error) {
        console.error(error);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color: red;">Erro ao carregar clientes.</td></tr>';
    }
}

async function deleteClient(id) {
    if(!confirm("Tem certeza que deseja excluir este cliente?")) return;

    try {
        const response = await apiFetch(`/clients/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showNotification('Cliente removido.', 'success');
            loadClients();
        } else {
            showNotification('Erro ao remover.', 'error');
        }
    } catch (e) {
        showNotification('Erro de conexão.', 'error');
    }
}

function sendMsg(id) {
    // Aqui você pode abrir um modal futuramente para escolher qual mensagem enviar
    const msg = prompt("Digite a mensagem personalizada para enviar agora:");
    if (msg) {
        // Lógica futura para enviar mensagem via endpoint do WhatsApp
        showNotification("Funcionalidade de envio direto em desenvolvimento.", "info");
    }
}