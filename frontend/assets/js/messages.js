const DEFAULT_REMINDER_TEMPLATES = {
    upcoming: 'Olá {nome_cliente}! 📅 Sua assinatura vence em {dias_restantes} dias, no dia {data_vencimento}. Evite bloqueios e garanta a renovação a tempo.',
    tomorrow: 'Olá {nome_cliente}! ⏰ Sua assinatura vence amanhã ({data_vencimento}). Se precisar renovar, responda esta mensagem.',
    today: 'Olá {nome_cliente}! 🚨 Sua assinatura vence hoje ({data_vencimento}). Renove agora para continuar com o acesso ativo.',
    overdue: 'Olá {nome_cliente}. ❌ Sua assinatura venceu há {dias_atraso} dias, em {data_vencimento}. Entre em contato para reativar o acesso.',
    fallback: 'Olá {nome_cliente}! 📌 Lembrete: sua assinatura está ativa e vence no dia {data_vencimento}.',
};

const EMPTY_REMINDER_MEDIA = {
    data_url: '',
    file_name: '',
    mime_type: '',
};

const SYSTEM_SCENARIOS = [
    {
        key: 'upcoming',
        fieldId: 'template-upcoming',
        label: 'Antes do vencimento',
        description: 'Usada quando faltam 2 ou mais dias dentro da janela configurada para o cliente.',
    },
    {
        key: 'tomorrow',
        fieldId: 'template-tomorrow',
        label: 'Vence amanhã',
        description: 'Usada automaticamente quando falta 1 dia para o vencimento.',
    },
    {
        key: 'today',
        fieldId: 'template-today',
        label: 'Vence hoje',
        description: 'Usada no próprio dia do vencimento.',
    },
    {
        key: 'overdue',
        fieldId: 'template-overdue',
        label: 'Assinatura vencida',
        description: 'Usada quando o cliente já está vencido e a opção de continuar avisando está ativa.',
    },
    {
        key: 'fallback',
        fieldId: 'template-fallback',
        label: 'Mensagem padrão',
        description: 'Fallback para lembretes manuais fora da regra principal.',
    },
];

const TEMPLATE_IDS = SYSTEM_SCENARIOS.reduce((accumulator, scenario) => {
    accumulator[scenario.key] = scenario.fieldId;
    return accumulator;
}, {});

const SYSTEM_SCENARIO_KEYS = new Set(SYSTEM_SCENARIOS.map((scenario) => scenario.key));

const PLACEHOLDER_ALIASES = {
    nome_cliente: ['nome_cliente', 'client_name'],
    data_vencimento: ['data_vencimento', 'expiration_date'],
    dias_restantes: ['dias_restantes', 'days_left'],
    dias_atraso: ['dias_atraso', 'days_overdue'],
    login_cliente: ['login_cliente', 'login'],
    nome_servidor: ['nome_servidor', 'server_name'],
    whatsapp_cliente: ['whatsapp_cliente', 'whatsapp'],
    nome_responsavel: ['nome_responsavel', 'owner_name'],
};

const PREVIEW_CONTEXTS = {
    upcoming: {
        nome_cliente: 'Maria Souza',
        data_vencimento: '30/07/2026',
        dias_restantes: '3',
        dias_atraso: '0',
        login_cliente: 'maria.souza',
        nome_servidor: 'Servidor Premium 01',
        whatsapp_cliente: '5511999999999',
        nome_responsavel: 'André',
    },
    tomorrow: {
        nome_cliente: 'Carlos Lima',
        data_vencimento: '28/07/2026',
        dias_restantes: '1',
        dias_atraso: '0',
        login_cliente: 'carlos.lima',
        nome_servidor: 'Servidor Family',
        whatsapp_cliente: '5511988888888',
        nome_responsavel: 'André',
    },
    today: {
        nome_cliente: 'Joana Dias',
        data_vencimento: '27/07/2026',
        dias_restantes: '0',
        dias_atraso: '0',
        login_cliente: 'joana.dias',
        nome_servidor: 'Servidor Ultra',
        whatsapp_cliente: '5511977777777',
        nome_responsavel: 'André',
    },
    overdue: {
        nome_cliente: 'Pedro Silva',
        data_vencimento: '20/07/2026',
        dias_restantes: '0',
        dias_atraso: '7',
        login_cliente: 'pedro.silva',
        nome_servidor: 'Servidor HD',
        whatsapp_cliente: '5511966666666',
        nome_responsavel: 'André',
    },
    fallback: {
        nome_cliente: 'Luciana Castro',
        data_vencimento: '12/08/2026',
        dias_restantes: '16',
        dias_atraso: '0',
        login_cliente: 'luciana.castro',
        nome_servidor: 'Servidor Master',
        whatsapp_cliente: '5511955555555',
        nome_responsavel: 'André',
    },
};

const reminderState = {
    reminder_templates: {},
    custom_scenarios: [],
};

document.addEventListener('DOMContentLoaded', () => {
    bindMessagesPage();
    initializeMessagesPage();
    closeSystemTemplatePanels();
});

function bindMessagesPage() {
    const form = document.getElementById('messagesForm');
    const previewScenario = document.getElementById('previewScenario');
    const addScenarioButton = document.getElementById('btnAddScenario');
    const newScenarioName = document.getElementById('newScenarioName');
    const customScenarioList = document.getElementById('customScenarioList');

    if (form) {
        form.addEventListener('submit', saveReminderSettings);
    }

    if (previewScenario) {
        previewScenario.addEventListener('change', renderPreview);
    }

    if (addScenarioButton) {
        addScenarioButton.addEventListener('click', addCustomScenario);
    }

    if (newScenarioName) {
        newScenarioName.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                addCustomScenario();
            }
        });
    }

    if (customScenarioList) {
        customScenarioList.addEventListener('input', handleCustomScenarioInput);
        customScenarioList.addEventListener('click', handleCustomScenarioClick);
    }

    if (form) {
        form.addEventListener('input', handleTemplateInput);
        form.addEventListener('change', handleMessageMediaChange);
        form.addEventListener('click', handleMessageMediaClick);
        form.addEventListener('toggle', handleTemplateCardToggle, true);
    }
}

function closeSystemTemplatePanels() {
    document.querySelectorAll('.system-template-card').forEach((card) => {
        card.open = false;
    });
}

async function initializeMessagesPage() {
    setSavingState(true);

    try {
        await loadSidebarInfo();
        const user = await fetchAPI('/users/me');
        fillTemplates(user.reminder_templates || DEFAULT_REMINDER_TEMPLATES);
        fillCustomScenarios(user.reminder_scenarios || []);
        renderPreviewScenarioOptions();
        updateScenarioSummary();
        renderPreview();
        closeSystemTemplatePanels();
    } catch (error) {
        showMessagesResult('danger', error.message || 'Falha ao carregar as mensagens.');
    } finally {
        setSavingState(false);
    }
}

function fillTemplates(templates) {
    const normalized = normalizeReminderTemplates(templates);
    reminderState.reminder_templates = normalized;
    Object.entries(TEMPLATE_IDS).forEach(([key, fieldId]) => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.value = normalized[key].template;
        }
        renderTemplateMediaPreview(key);
    });
}

function fillCustomScenarios(scenarios) {
    reminderState.custom_scenarios = normalizeCustomScenarios(scenarios);
    renderCustomScenarios();
}

function collectTemplates() {
    const collected = {};
    Object.entries(TEMPLATE_IDS).forEach(([key, fieldId]) => {
        const field = document.getElementById(fieldId);
        const stateEntry = reminderState.reminder_templates[key] || normalizeReminderTemplateEntry(DEFAULT_REMINDER_TEMPLATES[key]);
        collected[key] = {
            template: field && field.value.trim() ? field.value.trim() : stateEntry.template,
            media: normalizeReminderMedia(stateEntry.media),
        };
    });
    return collected;
}

function collectCustomScenarios() {
    return normalizeCustomScenarios(reminderState.custom_scenarios);
}

function normalizeReminderTemplates(templates) {
    const normalized = {};
    if (!templates || typeof templates !== 'object') {
        Object.keys(DEFAULT_REMINDER_TEMPLATES).forEach((key) => {
            normalized[key] = normalizeReminderTemplateEntry(DEFAULT_REMINDER_TEMPLATES[key]);
        });
        return normalized;
    }

    Object.keys(DEFAULT_REMINDER_TEMPLATES).forEach((key) => {
        normalized[key] = normalizeReminderTemplateEntry(templates[key], DEFAULT_REMINDER_TEMPLATES[key]);
    });

    return normalized;
}

function normalizeReminderTemplateEntry(value, fallbackTemplate) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return {
            template: typeof value.template === 'string' && value.template.trim() ? value.template.trim() : (fallbackTemplate || ''),
            media: normalizeReminderMedia(value.media),
        };
    }

    return {
        template: typeof value === 'string' && value.trim() ? value.trim() : (fallbackTemplate || ''),
        media: Object.assign({}, EMPTY_REMINDER_MEDIA),
    };
}

function normalizeCustomScenarios(scenarios) {
    if (!Array.isArray(scenarios)) {
        return [];
    }

    const normalized = [];
    const usedIds = new Set(SYSTEM_SCENARIOS.map((scenario) => scenario.key));

    scenarios.forEach((scenario, index) => {
        const source = scenario && typeof scenario === 'object' ? scenario : {};
        const template = typeof source.template === 'string' ? source.template.trim() : '';
        const media = normalizeReminderMedia(source.media);
        const rawName = typeof source.name === 'string' ? source.name.trim() : '';

        if (!rawName && !template) {
            return;
        }

        const name = rawName || `Mensagem ${index + 1}`;
        let scenarioId = sanitizeScenarioId(source.id);
        if (!scenarioId) {
            scenarioId = `custom-${slugifyScenarioName(name) || 'cenario'}`;
        }

        const uniqueId = ensureUniqueScenarioId(scenarioId, usedIds);
        usedIds.add(uniqueId);
        normalized.push({
            id: uniqueId,
            name,
            template,
            media,
        });
    });

    return normalized;
}

function normalizeReminderMedia(media) {
    const normalized = Object.assign({}, EMPTY_REMINDER_MEDIA);
    if (!media || typeof media !== 'object') {
        return normalized;
    }

    normalized.data_url = typeof media.data_url === 'string' ? media.data_url : '';
    normalized.file_name = typeof media.file_name === 'string' ? media.file_name : '';
    normalized.mime_type = typeof media.mime_type === 'string' ? media.mime_type : '';
    return normalized;
}

function renderPreview() {
    const previewScenario = document.getElementById('previewScenario');
    const preview = document.getElementById('messagePreview');
    if (!previewScenario || !preview) {
        return;
    }

    const scenario = previewScenario.value;
    const templates = collectTemplates();
    const customScenario = reminderState.custom_scenarios.find((item) => item.id === scenario);
    const context = buildPreviewContext(PREVIEW_CONTEXTS[scenario] || PREVIEW_CONTEXTS.upcoming || PREVIEW_CONTEXTS.fallback);
    const template = customScenario
        ? customScenario.template
        : ((templates[scenario] && templates[scenario].template) || DEFAULT_REMINDER_TEMPLATES[scenario]);

    preview.textContent = template
        ? applyTemplate(template, context)
        : 'Escreva a mensagem para visualizar a prévia aqui.';
}

function handleTemplateInput(event) {
    const target = event.target;
    if (!target || !target.closest || target.tagName !== 'TEXTAREA') {
        return;
    }

    const card = target.closest('[data-template-key]');
    if (!card) {
        return;
    }

    const key = card.dataset.templateKey;
    if (reminderState.reminder_templates[key]) {
        reminderState.reminder_templates[key].template = target.value;
    }

    renderPreview();
}

async function handleMessageMediaChange(event) {
    const target = event.target;
    if (!target || !target.hasAttribute || !target.hasAttribute('data-media-input')) {
        return;
    }

    const file = target.files ? target.files[0] : null;
    if (!file) {
        return;
    }

    if (!file.type || !file.type.startsWith('image/')) {
        showMessagesResult('danger', 'Selecione um arquivo de imagem válido.');
        target.value = '';
        return;
    }

    if (file.size > 2 * 1024 * 1024) {
        showMessagesResult('danger', 'A imagem excede o limite recomendado de 2 MB.');
        target.value = '';
        return;
    }

    try {
        const dataUrl = await readFileAsDataUrl(file);
        const media = {
            data_url: dataUrl,
            file_name: file.name,
            mime_type: file.type,
        };

        if (target.dataset.scope === 'template') {
            const key = target.dataset.templateKey;
            if (reminderState.reminder_templates[key]) {
                reminderState.reminder_templates[key].media = media;
                console.debug('handleMessageMediaChange: template', key, { fileName: media.file_name, mime: media.mime_type, len: media.data_url ? media.data_url.length : 0 });
                renderTemplateMediaPreview(key);
            }
        } else if (target.dataset.scope === 'scenario') {
            const scenarioId = target.dataset.scenarioId;
            const scenario = reminderState.custom_scenarios.find((item) => item.id === scenarioId);
            if (scenario) {
                scenario.media = media;
                console.debug('handleMessageMediaChange: scenario', scenarioId, { fileName: media.file_name, mime: media.mime_type, len: media.data_url ? media.data_url.length : 0 });
                renderScenarioMediaPreview(scenarioId);
            }
        }

        showMessagesResult('info', 'Imagem carregada. Salve para aplicar nos lembretes.');
    } catch (error) {
        showMessagesResult('danger', 'Não foi possível ler a imagem selecionada.');
    }
}

function handleMessageMediaClick(event) {
    const target = event.target;
    if (!target || !target.dataset || target.dataset.action !== 'remove-media') {
        return;
    }

    if (target.dataset.scope === 'template') {
        const key = target.dataset.templateKey;
        if (reminderState.reminder_templates[key]) {
            reminderState.reminder_templates[key].media = Object.assign({}, EMPTY_REMINDER_MEDIA);
            const input = document.getElementById(`template-media-${key}`);
            if (input) {
                input.value = '';
            }
            renderTemplateMediaPreview(key);
        }
        return;
    }

    if (target.dataset.scope === 'scenario') {
        const scenarioId = target.dataset.scenarioId;
        const scenario = reminderState.custom_scenarios.find((item) => item.id === scenarioId);
        if (scenario) {
            scenario.media = Object.assign({}, EMPTY_REMINDER_MEDIA);
            const input = document.getElementById(`scenario-media-${scenarioId}`);
            if (input) {
                input.value = '';
            }
            renderScenarioMediaPreview(scenarioId);
        }
    }
}

function buildPreviewContext(baseContext) {
    const context = {};

    Object.entries(PLACEHOLDER_ALIASES).forEach(([canonicalKey, aliases]) => {
        const value = baseContext && baseContext[canonicalKey] ? baseContext[canonicalKey] : '';
        aliases.forEach((alias) => {
            context[alias] = value;
        });
    });

    return context;
}

function renderTemplateMediaPreview(key) {
    const preview = document.getElementById(`template-media-preview-${key}`);
    const entry = reminderState.reminder_templates[key] || normalizeReminderTemplateEntry(DEFAULT_REMINDER_TEMPLATES[key]);
    renderMediaPreview(preview, entry.media, `template-thumb-${key}`);
}

function renderScenarioMediaPreview(scenarioId) {
    const preview = document.getElementById(`scenario-media-preview-${scenarioId}`);
    const scenario = reminderState.custom_scenarios.find((item) => item.id === scenarioId);
    renderMediaPreview(preview, scenario ? scenario.media : null, `template-thumb-${scenarioId}`);
}

function formatMimeType(value) {
    if (typeof value !== 'string' || !value.trim()) {
        return 'imagem';
    }

    const mimeType = value.trim().toLowerCase();
    const knownTypes = {
        'image/jpeg': 'JPG',
        'image/jpg': 'JPG',
        'image/png': 'PNG',
        'image/webp': 'WEBP',
        'image/gif': 'GIF',
        'image/svg+xml': 'SVG',
    };

    if (knownTypes[mimeType]) {
        return knownTypes[mimeType];
    }

    const parts = mimeType.split('/');
    return (parts[1] || parts[0] || 'imagem').toUpperCase();
}

function renderMediaPreview(preview, media, thumbId) {
    if (!preview) {
        return;
    }

    const normalized = normalizeReminderMedia(media);
    try {
        console.debug('renderMediaPreview', { previewId: preview.id || null, thumbId: thumbId || null, hasData: !!normalized.data_url, dataLen: normalized.data_url ? normalized.data_url.length : 0 });
    } catch (e) {
        // ignore logging errors
    }

    if (!normalized.data_url) {
        preview.classList.add('empty');
        preview.innerHTML = 'Nenhuma imagem configurada.';
    } else {
        preview.classList.remove('empty');
        preview.innerHTML = `
            <img src="${normalized.data_url}" alt="Imagem anexada">
            <div class="upload-meta">${escapeHtml(normalized.file_name || 'imagem')} • ${escapeHtml(formatMimeType(normalized.mime_type))}</div>
        `;
    }

    // Atualiza miniatura no summary (se existir)
    if (thumbId) {
        try {
            const thumb = document.getElementById(thumbId);
            if (thumb) {
                if (normalized.data_url) {
                    thumb.style.backgroundImage = `url('${normalized.data_url}')`;
                    thumb.classList.remove('empty');
                } else {
                    thumb.style.backgroundImage = '';
                    thumb.classList.add('empty');
                }
            }
        } catch (e) {
            // não bloquear a execução por falha em atualizar a miniatura
            console.debug('Falha ao atualizar miniatura:', e);
        }
    }
}

function applyTemplate(template, context) {
    let rendered = String(template || '');
    Object.entries(context || {}).forEach(([key, value]) => {
        rendered = rendered.replaceAll(`{${key}}`, String(value || ''));
    });
    return rendered;
}

function handleTemplateCardToggle(event) {
    const card = event.target;
    if (!card || !card.matches || !card.matches('.template-card') || !card.open) {
        return;
    }

    syncPreviewWithCard(card);
}

function syncPreviewWithCard(card) {
    if (!card || !card.dataset) {
        return;
    }

    const previewScenario = document.getElementById('previewScenario');
    if (!previewScenario) {
        return;
    }

    const scenarioKey = card.dataset.templateKey || card.dataset.scenarioId;
    if (!scenarioKey) {
        return;
    }

    if (previewScenario.value !== scenarioKey) {
        previewScenario.value = scenarioKey;
    }

    renderPreview();
}

function addCustomScenario() {
    const input = document.getElementById('newScenarioName');
    const providedName = input && input.value ? input.value.trim() : '';
    const fallbackName = `Mensagem ${reminderState.custom_scenarios.length + 1}`;
    const name = providedName || fallbackName;
    const scenario = {
        id: ensureUniqueScenarioId(`custom-${slugifyScenarioName(name) || 'cenario'}`, new Set([
            ...SYSTEM_SCENARIOS.map((item) => item.key),
            ...reminderState.custom_scenarios.map((item) => item.id),
        ])),
        name,
        template: '',
        media: Object.assign({}, EMPTY_REMINDER_MEDIA),
    };

    reminderState.custom_scenarios.push(scenario);
    renderCustomScenarios();
    renderPreviewScenarioOptions(scenario.id);
    updateScenarioSummary();
    renderPreview();

    if (input) {
        input.value = '';
    }

    const card = document.querySelector(`[data-scenario-id="${scenario.id}"]`);
    if (card) {
        card.open = true;
        syncPreviewWithCard(card);
    }

    const templateField = card ? card.querySelector('textarea') : null;
    if (templateField) {
        templateField.focus();
    }

    showMessagesResult('info', 'Mensagem criada. Clique em salvar para deixar ela disponível nos envios.');
}

function renderCustomScenarios() {
    const container = document.getElementById('customScenarioList');
    if (!container) {
        return;
    }

    if (!reminderState.custom_scenarios.length) {
        container.innerHTML = '<div class="custom-scenario-empty">Nenhuma mensagem personalizada criada até o momento.</div>';
        return;
    }

    container.innerHTML = reminderState.custom_scenarios.map((scenario) => `
        <details class="template-card" data-scenario-id="${escapeHtml(scenario.id)}">
            <summary>
                <h3>${escapeHtml(scenario.name)}</h3>
                <p>Abra para editar o nome, o texto e remover esta mensagem personalizada.</p>
                <div class="template-thumb" id="template-thumb-${escapeHtml(scenario.id)}"></div>
            </summary>
            <div class="scenario-card-header">
                <div class="flex-grow-1">
                    <label class="form-label" for="scenario-name-${escapeHtml(scenario.id)}">Nome da mensagem</label>
                    <input
                        type="text"
                        id="scenario-name-${escapeHtml(scenario.id)}"
                        class="form-control"
                        data-field="name"
                        maxlength="80"
                        value="${escapeHtml(scenario.name)}"
                    >
                </div>
                <button type="button" class="btn btn-outline-danger" data-action="remove-scenario">Remover</button>
            </div>
            <p>Use esta mensagem para situações extras que não entram na régua automática padrão.</p>
            <label class="form-label" for="scenario-template-${escapeHtml(scenario.id)}">Mensagem</label>
            <textarea
                id="scenario-template-${escapeHtml(scenario.id)}"
                class="form-control"
                data-field="template"
                rows="4"
            >${escapeHtml(scenario.template)}</textarea>
            <div class="message-media">
                <div class="message-media-header">
                    <label class="form-label" for="scenario-media-${escapeHtml(scenario.id)}">Imagem opcional</label>
                    <button type="button" class="btn btn-outline-secondary btn-sm" data-action="remove-media" data-scope="scenario" data-scenario-id="${escapeHtml(scenario.id)}">Remover imagem</button>
                </div>
                <input
                    type="file"
                    id="scenario-media-${escapeHtml(scenario.id)}"
                    class="form-control"
                    accept="image/*"
                    data-media-input
                    data-scope="scenario"
                    data-scenario-id="${escapeHtml(scenario.id)}"
                >
                <div class="message-media-preview empty" id="scenario-media-preview-${escapeHtml(scenario.id)}">Nenhuma imagem configurada.</div>
            </div>
        </details>
    `).join('');
    reminderState.custom_scenarios.forEach((scenario) => {
        renderScenarioMediaPreview(scenario.id);
    });
}

function renderPreviewScenarioOptions(preferredScenario) {
    const select = document.getElementById('previewScenario');
    if (!select) {
        return;
    }

    const currentValue = preferredScenario || select.value;
    const options = [
        ...SYSTEM_SCENARIOS.map((scenario) => ({ value: scenario.key, label: scenario.label })),
        ...reminderState.custom_scenarios.map((scenario) => ({ value: scenario.id, label: scenario.name })),
    ];

    select.innerHTML = options.map((option) => `
        <option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>
    `).join('');

    const availableValues = new Set(options.map((option) => option.value));
    select.value = availableValues.has(currentValue) ? currentValue : 'upcoming';
}

function handleCustomScenarioInput(event) {
    const target = event.target;
    if (!target || !target.dataset || !target.dataset.field) {
        return;
    }

    const card = target.closest('[data-scenario-id]');
    if (!card) {
        return;
    }

    const scenario = reminderState.custom_scenarios.find((item) => item.id === card.dataset.scenarioId);
    if (!scenario) {
        return;
    }

    if (target.dataset.field === 'name') {
        scenario.name = target.value.trim() || 'Nova mensagem';
        if (!target.value.trim()) {
            target.value = scenario.name;
        }
        renderPreviewScenarioOptions(document.getElementById('previewScenario') && document.getElementById('previewScenario').value === scenario.id ? scenario.id : undefined);
    }

    if (target.dataset.field === 'template') {
        scenario.template = target.value;
    }

    renderPreview();
}

function handleCustomScenarioClick(event) {
    const target = event.target;
    if (!target || target.dataset.action !== 'remove-scenario') {
        return;
    }

    const card = target.closest('[data-scenario-id]');
    if (!card) {
        return;
    }

    const removedScenarioId = card.dataset.scenarioId;
    reminderState.custom_scenarios = reminderState.custom_scenarios.filter((item) => item.id !== removedScenarioId);
    renderCustomScenarios();
    renderPreviewScenarioOptions();
    updateScenarioSummary();
    renderPreview();
}

function updateScenarioSummary() {
    const summaryScenarioCount = document.getElementById('summaryScenarioCount');
    if (!summaryScenarioCount) {
        return;
    }

    summaryScenarioCount.textContent = String(SYSTEM_SCENARIOS.length + reminderState.custom_scenarios.length);
}

function sanitizeScenarioId(value) {
    if (typeof value !== 'string') {
        return '';
    }
    const raw = value
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');

    if (!raw) {
        return '';
    }

    return SYSTEM_SCENARIO_KEYS.has(raw) ? `custom-${raw}` : raw;
}

function slugifyScenarioName(value) {
    if (typeof value !== 'string') {
        return '';
    }

    return value
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '');
}

function ensureUniqueScenarioId(baseId, usedIds) {
    const normalizedBase = sanitizeScenarioId(baseId) || 'custom-cenario';
    let candidateId = normalizedBase;
    let suffix = 2;

    while (usedIds.has(candidateId)) {
        candidateId = `${normalizedBase}-${suffix}`;
        suffix += 1;
    }

    return candidateId;
}

function readFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

async function saveReminderSettings(event) {
    event.preventDefault();
    setSavingState(true);

    try {
        await fetchAPI('/users/me/settings', {
            method: 'PATCH',
            body: JSON.stringify({
                reminder_templates: collectTemplates(),
                reminder_scenarios: collectCustomScenarios(),
            }),
        });
        showMessagesResult('success', 'Mensagens de lembrete atualizadas com sucesso.');
    } catch (error) {
        showMessagesResult('danger', error.message || 'Falha ao salvar as mensagens.');
    } finally {
        setSavingState(false);
    }
}

function setSavingState(isSaving) {
    const saveButtons = Array.from(document.querySelectorAll('[data-save-messages]'));
    if (!saveButtons.length) {
        return;
    }

    saveButtons.forEach((button) => {
        const idleLabel = button.id === 'btnSaveMessages'
            ? 'Salvar mensagens'
            : 'Salvar mensagens personalizadas';
        button.disabled = isSaving;
        button.textContent = isSaving ? 'Salvando...' : idleLabel;
    });
}

function showMessagesResult(type, message) {
    const target = document.getElementById('messagesResult');
    if (!target) {
        return;
    }

    target.style.display = 'block';
    target.innerHTML = `<div class="alert alert-${type}" role="alert">${escapeHtml(message)}</div>`;
}
