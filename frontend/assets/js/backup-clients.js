const BACKUP_HEADER_ALIASES = {
    name: ['name', 'nome', 'cliente', 'client'],
    login: ['login', 'usuario', 'usuário', 'username', 'user'],
    server_name: ['server_name', 'servidor', 'server', 'painel'],
    whatsapp: ['whatsapp', 'telefone', 'celular', 'phone', 'numero', 'número'],
    expiration_date: ['expiration_date', 'vencimento', 'validade', 'data_vencimento', 'expiracao', 'expiração'],
    notes: ['notes', 'observacoes', 'observações', 'obs', 'anotacoes', 'anotações'],
    m3u8_url: ['m3u8_url', 'm3u8', 'playlist', 'url_m3u8'],
    notification_channel: ['notification_channel', 'canal', 'canal_notificacao', 'canal_notificação'],
    reminder_days_before: ['reminder_days_before', 'dias_aviso', 'dias_antes', 'aviso', 'lembrete'],
    notify_downtime: ['notify_downtime', 'alerta_queda', 'queda'],
    reminder_enabled: ['reminder_enabled', 'cobranca_automatica', 'cobrança_automática', 'cobranca'],
    notify_after_expiration: ['notify_after_expiration', 'avisar_vencidos', 'avisar_apos_vencer']
};

const BACKUP_EXPORT_COLUMNS = [
    'name',
    'login',
    'server_name',
    'whatsapp',
    'expiration_date',
    'notification_channel',
    'reminder_days_before',
    'notify_downtime',
    'reminder_enabled',
    'notify_after_expiration',
    'm3u8_url',
    'notes',
    'custom_fields'
];

let currentClients = [];
let restorePreviewRows = [];

document.addEventListener('DOMContentLoaded', () => {
    bindBackupEvents();
    loadCurrentClients();
});

function bindBackupEvents() {
    document.getElementById('btnExportJson').addEventListener('click', exportBackupJson);
    document.getElementById('btnExportCsv').addEventListener('click', exportBackupCsv);
    document.getElementById('btnDownloadExample').addEventListener('click', downloadExampleBackup);
    document.getElementById('btnPreviewRestore').addEventListener('click', previewRestore);
    document.getElementById('btnApplyRestore').addEventListener('click', applyRestore);
    document.getElementById('searchCurrentClients').addEventListener('input', renderCurrentClientsTable);
}

async function loadCurrentClients() {
    try {
        const data = await fetchAPI('/clients/');
        currentClients = Array.isArray(data) ? data.slice() : [];
        currentClients.sort((left, right) => String(left.name || '').localeCompare(String(right.name || ''), 'pt-BR'));
        updateCurrentSummary();
        renderCurrentClientsTable();
    } catch (error) {
        console.error(error);
        document.getElementById('currentClientsTableBody').innerHTML = '<tr><td colspan="6" class="text-center text-danger">Erro ao carregar clientes.</td></tr>';
        showResult('restoreResult', 'danger', error.message || 'Falha ao carregar clientes.');
    }
}

function updateCurrentSummary() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const expiredCount = currentClients.filter((client) => {
        const clientDate = parseDateValue(client.expiration_date);
        return clientDate && clientDate < today;
    }).length;

    const whatsappCount = currentClients.filter((client) => (client.notification_channel || 'whatsapp') === 'whatsapp').length;
    const telegramCount = currentClients.filter((client) => client.notification_channel === 'telegram').length;

    document.getElementById('summaryTotal').textContent = currentClients.length;
    document.getElementById('summaryExpired').textContent = expiredCount;
    document.getElementById('summaryWhatsapp').textContent = whatsappCount;
    document.getElementById('summaryTelegram').textContent = telegramCount;
}

function renderCurrentClientsTable() {
    const searchValue = normalizeText(document.getElementById('searchCurrentClients').value).toLowerCase();
    const tbody = document.getElementById('currentClientsTableBody');

    const filteredClients = currentClients.filter((client) => {
        if (!searchValue) return true;
        const haystack = [
            client.name,
            client.login,
            client.server_name,
            client.whatsapp
        ].map((value) => normalizeText(value).toLowerCase()).join(' ');
        return haystack.includes(searchValue);
    });

    if (!filteredClients.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Nenhum cliente encontrado.</td></tr>';
        return;
    }

    tbody.innerHTML = filteredClients.map((client) => `
        <tr>
            <td>${escapeHtml(client.name || '-')}</td>
            <td>${escapeHtml(client.login || '-')}</td>
            <td>${escapeHtml(client.server_name || '-')}</td>
            <td>${escapeHtml(client.whatsapp || '-')}</td>
            <td>${escapeHtml(formatDisplayDate(client.expiration_date) || '-')}</td>
            <td>${escapeHtml(formatChannelLabel(client.notification_channel || 'whatsapp'))}</td>
        </tr>
    `).join('');
}

function buildBackupSnapshot() {
    return {
        exported_at: new Date().toISOString(),
        source: 'gestor_nexus',
        version: 1,
        total_clients: currentClients.length,
        clients: currentClients.map((client) => ({
            name: normalizeText(client.name),
            login: normalizeText(client.login),
            server_name: normalizeText(client.server_name),
            whatsapp: normalizePhone(client.whatsapp),
            expiration_date: normalizeDateOutput(client.expiration_date),
            notes: normalizeText(client.notes),
            m3u8_url: normalizeText(client.m3u8_url),
            custom_fields: client.custom_fields || null,
            notify_downtime: Boolean(client.notify_downtime),
            reminder_enabled: Boolean(client.reminder_enabled),
            reminder_days_before: normalizeText(client.reminder_days_before || '3'),
            notify_after_expiration: Boolean(client.notify_after_expiration),
            notification_channel: normalizeText(client.notification_channel || 'whatsapp') || 'whatsapp'
        }))
    };
}

function exportBackupJson() {
    const snapshot = buildBackupSnapshot();
    downloadTextFile(
        `backup-clientes-${buildDateStamp()}.json`,
        JSON.stringify(snapshot, null, 2),
        'application/json;charset=utf-8'
    );
}

function exportBackupCsv() {
    const snapshot = buildBackupSnapshot();
    const csvLines = [
        BACKUP_EXPORT_COLUMNS.join(';'),
        ...snapshot.clients.map((client) => BACKUP_EXPORT_COLUMNS.map((column) => {
            const value = column === 'custom_fields'
                ? JSON.stringify(client[column] || {})
                : client[column];
            return escapeCsvCell(value);
        }).join(';'))
    ];

    downloadTextFile(
        `backup-clientes-${buildDateStamp()}.csv`,
        csvLines.join('\r\n'),
        'text/csv;charset=utf-8'
    );
}

function downloadExampleBackup() {
    const example = {
        exported_at: new Date().toISOString(),
        source: 'gestor_nexus_example',
        version: 1,
        total_clients: 1,
        clients: [{
            name: 'Cliente Exemplo',
            login: 'cliente.demo',
            server_name: 'Servidor Principal',
            whatsapp: '5511999999999',
            expiration_date: '2026-12-31',
            notes: 'Backup de demonstração',
            m3u8_url: '',
            custom_fields: { pacote: 'Premium' },
            notify_downtime: true,
            reminder_enabled: true,
            reminder_days_before: '3',
            notify_after_expiration: true,
            notification_channel: 'whatsapp'
        }]
    };

    downloadTextFile(
        'exemplo-backup-clientes.json',
        JSON.stringify(example, null, 2),
        'application/json;charset=utf-8'
    );
}

async function previewRestore() {
    try {
        const source = await readRestoreSource();
        const rows = parseRestoreSource(source.content, source.fileName);

        if (!rows.length) {
            throw new Error('Nenhum registro válido foi encontrado no backup informado.');
        }

        restorePreviewRows = buildRestorePreview(rows);
        renderRestorePreview();
    } catch (error) {
        console.error(error);
        restorePreviewRows = [];
        renderRestorePreview();
        showResult('restoreResult', 'danger', error.message || 'Falha ao gerar prévia.');
    }
}

async function applyRestore() {
    const actionableRows = restorePreviewRows.filter((row) => row.action === 'create' || row.action === 'update');
    if (!actionableRows.length) {
        showResult('restoreResult', 'warning', 'Não há registros prontos para aplicar.');
        return;
    }

    const button = document.getElementById('btnApplyRestore');
    button.disabled = true;
    button.textContent = 'Aplicando...';

    let created = 0;
    let updated = 0;
    let failed = 0;

    for (const row of actionableRows) {
        try {
            if (row.action === 'create') {
                await fetchAPI('/clients/', {
                    method: 'POST',
                    body: JSON.stringify(row.payload)
                });
                created += 1;
            } else if (row.action === 'update' && row.targetId) {
                await fetchAPI(`/clients/${row.targetId}`, {
                    method: 'PUT',
                    body: JSON.stringify(row.payload)
                });
                updated += 1;
            }
        } catch (error) {
            failed += 1;
            row.status = 'error';
            row.statusLabel = error.message || 'Falha ao aplicar';
        }
    }

    button.textContent = 'Aplicar restauração';
    await loadCurrentClients();
    renderRestorePreview();

    showResult(
        'restoreResult',
        failed ? 'warning' : 'success',
        `Restauração concluída: ${created} criado(s), ${updated} atualizado(s), ${failed} falha(s).`
    );
}

async function readRestoreSource() {
    const fileInput = document.getElementById('backupFile');
    const rawInput = document.getElementById('rawBackupInput');

    if (fileInput.files && fileInput.files[0]) {
        const file = fileInput.files[0];
        const content = await file.text();
        return { content, fileName: file.name };
    }

    const content = normalizeText(rawInput.value);
    if (content) {
        return { content, fileName: 'backup-manual.txt' };
    }

    throw new Error('Selecione um arquivo de backup ou cole o conteúdo para continuar.');
}

function parseRestoreSource(content, fileName) {
    const trimmed = normalizeText(content);
    if (!trimmed) return [];

    const lowerFileName = String(fileName || '').toLowerCase();
    if (trimmed.startsWith('{') || trimmed.startsWith('[') || lowerFileName.endsWith('.json')) {
        return parseJsonBackup(trimmed);
    }

    return parseCsvBackup(trimmed);
}

function parseJsonBackup(content) {
    const parsed = JSON.parse(content);
    if (Array.isArray(parsed)) return parsed;
    if (parsed && Array.isArray(parsed.clients)) return parsed.clients;
    throw new Error('O JSON informado não possui uma lista de clientes válida.');
}

function parseCsvBackup(text) {
    const separator = detectSeparator(text);
    const lines = String(text || '')
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);

    if (lines.length < 2) {
        return [];
    }

    const rawHeaders = splitCsvLine(lines[0], separator);
    const normalizedHeaders = rawHeaders.map(normalizeHeader);

    return lines.slice(1).map((line, index) => {
        const columns = splitCsvLine(line, separator);
        const row = { __line: index + 2 };
        normalizedHeaders.forEach((header, headerIndex) => {
            row[header || `coluna_${headerIndex + 1}`] = columns[headerIndex] || '';
        });
        return row;
    });
}

function buildRestorePreview(rawRows) {
    const updateExisting = document.getElementById('allowUpdateExisting').checked;
    const batchKeys = new Set();

    return rawRows.map((rawRow, index) => {
        const payload = buildClientPayload(rawRow);
        const errors = validatePayload(payload);

        const batchKey = `${payload.login.toLowerCase()}::${payload.whatsapp}`;
        if (payload.login || payload.whatsapp) {
            if (batchKeys.has(batchKey)) {
                errors.push('Duplicado no próprio backup');
            } else {
                batchKeys.add(batchKey);
            }
        }

        const existingClient = findExistingClient(payload);
        let status = 'ready';
        let statusLabel = 'Novo cliente';
        let action = 'create';
        let targetId = null;

        if (errors.length) {
            status = 'error';
            statusLabel = errors.join(' • ');
            action = 'error';
        } else if (existingClient) {
            if (updateExisting) {
                status = 'update';
                statusLabel = `Atualizar: ${existingClient.name || existingClient.login}`;
                action = 'update';
                targetId = existingClient.id;
            } else {
                status = 'duplicate';
                statusLabel = `Já existe: ${existingClient.name || existingClient.login}`;
                action = 'skip';
                targetId = existingClient.id;
            }
        }

        return {
            line: rawRow.__line || index + 1,
            payload,
            status,
            statusLabel,
            action,
            targetId
        };
    });
}

function renderRestorePreview() {
    const emptyState = document.getElementById('restoreEmptyState');
    const wrapper = document.getElementById('restorePreviewWrapper');
    const tbody = document.getElementById('restorePreviewTableBody');
    const applyButton = document.getElementById('btnApplyRestore');

    if (!restorePreviewRows.length) {
        emptyState.style.display = '';
        wrapper.style.display = 'none';
        tbody.innerHTML = '';
        applyButton.disabled = true;
        return;
    }

    emptyState.style.display = 'none';
    wrapper.style.display = '';
    applyButton.disabled = !restorePreviewRows.some((row) => row.action === 'create' || row.action === 'update');

    tbody.innerHTML = restorePreviewRows.map((row) => `
        <tr>
            <td>${escapeHtml(row.line)}</td>
            <td><span class="${statusClassName(row.status)}">${escapeHtml(statusLabelForDisplay(row.status, row.statusLabel))}</span></td>
            <td>${escapeHtml(row.payload.name || '-')}</td>
            <td>${escapeHtml(row.payload.login || '-')}</td>
            <td>${escapeHtml(row.payload.server_name || '-')}</td>
            <td>${escapeHtml(row.payload.whatsapp || '-')}</td>
            <td>${escapeHtml(formatDisplayDate(row.payload.expiration_date) || '-')}</td>
            <td class="notes-cell">${escapeHtml(row.payload.notes || '-')}</td>
        </tr>
    `).join('');
}

function buildClientPayload(rawRow) {
    const source = normalizeBackupObject(rawRow);

    let customFields = source.custom_fields;
    if (typeof customFields === 'string') {
        try {
            customFields = JSON.parse(customFields);
        } catch (error) {
            customFields = { raw_custom_fields: customFields };
        }
    }

    const payload = {
        name: normalizeText(source.name),
        login: normalizeText(source.login),
        server_name: normalizeText(source.server_name),
        whatsapp: normalizePhone(source.whatsapp),
        expiration_date: normalizeDateOutput(source.expiration_date),
        notes: normalizeText(source.notes),
        m3u8_url: normalizeText(source.m3u8_url),
        custom_fields: customFields && typeof customFields === 'object' ? customFields : undefined,
        notify_downtime: parseBoolean(source.notify_downtime, document.getElementById('restoreDefaultNotifyDowntime').checked),
        reminder_enabled: parseBoolean(source.reminder_enabled, document.getElementById('restoreDefaultReminderEnabled').checked),
        reminder_days_before: normalizeText(source.reminder_days_before || document.getElementById('restoreDefaultReminderDays').value || '3'),
        notify_after_expiration: parseBoolean(source.notify_after_expiration, document.getElementById('restoreDefaultNotifyAfterExpiration').checked),
        notification_channel: normalizeText(source.notification_channel || document.getElementById('restoreDefaultChannel').value || 'whatsapp')
    };

    if (!payload.custom_fields || !Object.keys(payload.custom_fields).length) {
        delete payload.custom_fields;
    }

    return payload;
}

function normalizeBackupObject(rawRow) {
    const output = {};
    const entries = Object.entries(rawRow || {}).filter(([key]) => !key.startsWith('__'));

    Object.keys(BACKUP_HEADER_ALIASES).forEach((canonicalKey) => {
        const aliasList = BACKUP_HEADER_ALIASES[canonicalKey];
        const match = entries.find(([key]) => aliasList.includes(normalizeHeader(key)));
        output[canonicalKey] = match ? match[1] : rawRow[canonicalKey];
    });

    if (rawRow.custom_fields !== undefined) {
        output.custom_fields = rawRow.custom_fields;
    }

    return output;
}

function validatePayload(payload) {
    const errors = [];

    if (!payload.name) errors.push('Nome ausente');
    if (!payload.login) errors.push('Login ausente');
    if (!payload.server_name) errors.push('Servidor ausente');
    if (!payload.whatsapp) errors.push('WhatsApp ausente');
    if (!payload.expiration_date) errors.push('Vencimento inválido');

    return errors;
}

function findExistingClient(payload) {
    return currentClients.find((client) => {
        const sameLogin = normalizeText(client.login).toLowerCase() && normalizeText(client.login).toLowerCase() === payload.login.toLowerCase();
        const sameWhatsapp = normalizePhone(client.whatsapp) && normalizePhone(client.whatsapp) === payload.whatsapp;
        return sameLogin || sameWhatsapp;
    }) || null;
}

function normalizeHeader(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');
}

function normalizeText(value) {
    return String(value || '').trim();
}

function normalizePhone(value) {
    return String(value || '').replace(/\D/g, '');
}

function parseBoolean(value, fallback) {
    if (value === undefined || value === null || value === '') return fallback;
    const normalized = normalizeHeader(value);
    if (['1', 'true', 'sim', 'yes', 'ativo', 'enabled'].includes(normalized)) return true;
    if (['0', 'false', 'nao', 'não', 'no', 'inativo', 'disabled'].includes(normalized)) return false;
    return Boolean(value);
}

function normalizeDateOutput(value) {
    const parsed = parseDateValue(value);
    if (!parsed) return '';

    const year = parsed.getFullYear();
    const month = String(parsed.getMonth() + 1).padStart(2, '0');
    const day = String(parsed.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function parseDateValue(value) {
    const raw = normalizeText(value);
    if (!raw) return null;

    if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
        const parsedIso = new Date(`${raw}T00:00:00`);
        return Number.isNaN(parsedIso.getTime()) ? null : parsedIso;
    }

    const dateParts = raw.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
    if (dateParts) {
        const day = dateParts[1].padStart(2, '0');
        const month = dateParts[2].padStart(2, '0');
        const year = dateParts[3].length === 2 ? `20${dateParts[3]}` : dateParts[3];
        const parsedLocal = new Date(`${year}-${month}-${day}T00:00:00`);
        return Number.isNaN(parsedLocal.getTime()) ? null : parsedLocal;
    }

    if (/^\d{5}$/.test(raw)) {
        const excelEpoch = new Date(Date.UTC(1899, 11, 30));
        excelEpoch.setUTCDate(excelEpoch.getUTCDate() + Number(raw));
        return new Date(`${excelEpoch.toISOString().slice(0, 10)}T00:00:00`);
    }

    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDisplayDate(value) {
    const normalized = normalizeDateOutput(value);
    if (!normalized) return '';
    const parts = normalized.split('-');
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

function detectSeparator(text) {
    const firstLine = String(text || '').split(/\r?\n/).find((line) => line.trim());
    if (!firstLine) return ';';

    const candidates = [';', ',', '\t'];
    return candidates
        .map((separator) => ({ separator, count: firstLine.split(separator).length }))
        .sort((left, right) => right.count - left.count)[0].separator;
}

function splitCsvLine(line, separator) {
    const values = [];
    let current = '';
    let inQuotes = false;

    for (let index = 0; index < line.length; index += 1) {
        const char = line[index];
        const next = line[index + 1];

        if (char === '"') {
            if (inQuotes && next === '"') {
                current += '"';
                index += 1;
            } else {
                inQuotes = !inQuotes;
            }
        } else if (char === separator && !inQuotes) {
            values.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }

    values.push(current.trim());
    return values;
}

function downloadTextFile(fileName, content, mimeType) {
    const blob = new Blob(['\ufeff', content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
}

function escapeCsvCell(value) {
    const normalized = String(value === undefined || value === null ? '' : value);
    return `"${normalized.replace(/"/g, '""')}"`;
}

function buildDateStamp() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    return `${year}${month}${day}-${hours}${minutes}`;
}

function formatChannelLabel(channel) {
    return channel === 'telegram' ? 'Telegram' : 'WhatsApp';
}

function statusClassName(status) {
    switch (status) {
        case 'ready':
            return 'status-badge status-ok';
        case 'update':
            return 'status-badge status-info';
        case 'duplicate':
            return 'status-badge status-warn';
        default:
            return 'status-badge status-error';
    }
}

function statusLabelForDisplay(status, label) {
    if (status === 'ready') return `Novo • ${label}`;
    if (status === 'update') return `Atualizar • ${label}`;
    if (status === 'duplicate') return `Ignorado • ${label}`;
    return label;
}

function showResult(targetId, type, message) {
    const target = document.getElementById(targetId);
    target.style.display = '';
    target.innerHTML = `<div class="alert alert-${type}" role="alert">${escapeHtml(message)}</div>`;
}
