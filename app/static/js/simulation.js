// static/js/simulation.js

let currentPollInterval = null;

async function createSimulation(e) {
    e.preventDefault();
    const btn = document.getElementById('submitBtn');
    const btnText = btn.querySelector('.btn-text');
    const btnLoader = btn.querySelector('.btn-loader');

    btn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'inline-block';

    const form = e.target;
    const materialIds = [...document.querySelectorAll('input[name="material_ids"]:checked')].map(cb => parseInt(cb.value));
    if (materialIds.length === 0) {
        alert('❌ Выберите хотя бы один материал');
        resetBtn();
        return;
    }
    const bladeId = form.querySelector('[name="blade_id"]').value;
    const assemblyId = form.querySelector('[name="assembly_id"]').value;
    if ((bladeId && assemblyId) || (!bladeId && !assemblyId)) {
        alert('❌ Выберите либо лопатку, либо объединение');
        resetBtn();
        return;
    }

    const payload = {
        name: form.querySelector('[name="name"]').value,
        blade_id: bladeId ? parseInt(bladeId) : null,
        assembly_id: assemblyId ? parseInt(assemblyId) : null,
        initial_conditions_id: parseInt(form.querySelector('[name="initial_conditions_id"]').value),
        material_ids: materialIds,
        tasks: [...form.querySelectorAll('input[name="tasks"]:checked')].map(cb => ({task_id: parseInt(cb.value)}))
    };

    try {
        const res = await fetch('/simulation/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Ошибка');
        const simId = data.id;
        showStatusPanel(simId, payload.name);
        pollStatus(simId);
    } catch(e) {
        alert('❌ Ошибка: ' + e.message);
        resetBtn();
    }

    function resetBtn() {
        btn.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
    }
}

function showStatusPanel(simId, simName) {
    let panel = document.getElementById('simulationStatusPanel');
    if (!panel) {
        // создать панель, если её нет в DOM
        panel = document.createElement('div');
        panel.id = 'simulationStatusPanel';
        panel.className = 'card';
        panel.style.display = 'block';
        panel.innerHTML = `
            <div class="card-header">
                <h3>Статус текущего расчёта</h3>
            </div>
            <div style="padding:16px 24px; display:flex; align-items:center; gap:16px; flex-wrap:wrap;">
                <div style="flex:1;">
                    <strong id="statusSimName">—</strong>
                    <p class="card-hint" style="margin:4px 0 0;">ID: <code id="statusSimId" class="id-badge">—</code></p>
                </div>
                <span id="statusBadge" class="badge badge-secondary">Ожидание</span>
                <div style="min-width:200px; flex:2;">
                    <div style="height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden;">
                        <div id="statusProgress" style="height:100%; width:0%; background:var(--accent); transition:width 0.3s;"></div>
                    </div>
                    <small id="statusText" style="display:block; margin-top:6px; color:var(--text-muted);">—</small>
                </div>
            </div>
        `;
        const container = document.querySelector('.main .card:first-of-type');
        if (container && container.parentNode) {
            container.parentNode.insertBefore(panel, container.nextSibling);
        } else {
            document.querySelector('.main').prepend(panel);
        }
    }
    panel.style.display = 'block';
    document.getElementById('statusSimName').innerText = simName;
    document.getElementById('statusSimId').innerText = simId;
    document.getElementById('statusBadge').className = 'badge badge-secondary';
    document.getElementById('statusBadge').innerText = '⏳ Подготовка';
    document.getElementById('statusProgress').style.width = '0%';
    document.getElementById('statusText').innerText = 'Генерация скрипта...';
}

function pollStatus(simId) {
    if (currentPollInterval) clearInterval(currentPollInterval);
    currentPollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`/simulation/${simId}/status`);
            if (!resp.ok) throw new Error('Ошибка получения статуса');
            const statusData = await resp.json();

            // Обновляем панель
            updateStatusPanel(statusData);

            if (statusData.status === 'completed' || statusData.status === 'failed') {
                clearInterval(currentPollInterval);
                await loadSimulationsList();
                if (statusData.status === 'completed') {
                    alert('✅ Расчёт завершён! Результат появится в истории.');
                } else {
                    const errorMsg = statusData.error_message || 'Неизвестная ошибка';
                    const showLog = confirm(`❌ Ошибка расчёта:\n${errorMsg}\n\nПоказать полный лог?`);
                    if (showLog) {
                        await fetchAndShowLog(simId);
                    }
                }
                // Скрыть панель через 3 секунды
                setTimeout(() => {
                    const panel = document.getElementById('simulationStatusPanel');
                    if (panel) panel.style.display = 'none';
                }, 3000);

                // Разблокировать кнопку создания
                const btn = document.getElementById('submitBtn');
                if (btn) {
                    btn.disabled = false;
                    const btnText = btn.querySelector('.btn-text');
                    const btnLoader = btn.querySelector('.btn-loader');
                    if (btnText) btnText.style.display = 'inline';
                    if (btnLoader) btnLoader.style.display = 'none';
                }
            } else {
                // Обновляем текст на кнопке (если нужно)
                const btnLoader = document.querySelector('#submitBtn .btn-loader');
                if (btnLoader) btnLoader.textContent = `⏳ ${statusData.status === 'running' ? 'Выполняется...' : statusData.status}`;
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    }, 2000);
}

function updateStatusPanel(data) {
    const badgeElem = document.getElementById('statusBadge');
    const progressElem = document.getElementById('statusProgress');
    const textElem = document.getElementById('statusText');
    if (!badgeElem) return;

    let statusText = '', badgeClass = '', progress = data.progress || 0;
    switch (data.status) {
        case 'pending': statusText = '⏳ Ожидание'; badgeClass = 'badge-secondary'; break;
        case 'running': statusText = '🔄 Расчёт'; badgeClass = 'badge-warning'; break;
        case 'completed': statusText = '✅ Завершён'; badgeClass = 'badge-success'; progress = 100; break;
        case 'failed': statusText = '❌ Ошибка'; badgeClass = 'badge-danger'; break;
        default: statusText = data.status; badgeClass = 'badge-secondary';
    }
    badgeElem.innerText = statusText;
    badgeElem.className = `badge ${badgeClass}`;
    if (progressElem) progressElem.style.width = `${progress}%`;
    if (textElem) {
        if (data.status === 'failed' && data.error_message) {
            textElem.innerText = `⚠️ Ошибка: ${data.error_message.substring(0, 120)}`;
        } else if (data.status === 'running') {
            textElem.innerText = 'Выполняется FreeFEM++...';
        } else if (data.status === 'pending') {
            textElem.innerText = 'Подготовка скрипта...';
        } else {
            textElem.innerText = data.status;
        }
    }
}

async function fetchAndShowLog(simId) {
    try {
        const resp = await fetch(`/simulation/${simId}/log`);
        if (!resp.ok) throw new Error('Лог не найден');
        const data = await resp.json();
        const modal = document.createElement('div');
        modal.className = 'modal-overlay active';
        modal.innerHTML = `
            <div class="modal modal-lg">
                <h3>Лог расчёта #${simId}</h3>
                <pre style="background:#1e1e2f; color:#f8fafc; padding:16px; border-radius:8px; overflow:auto; max-height:60vh; font-family:monospace; font-size:12px; white-space:pre-wrap;">${escapeHtml(data.log)}</pre>
                <div class="modal-actions">
                    <button class="btn-secondary" onclick="this.closest('.modal-overlay').remove()">Закрыть</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.remove();
        });
    } catch (err) {
        alert('Не удалось загрузить лог: ' + err.message);
    }
}

// ===== ЗАГРУЗКА ДАННЫХ =====
async function loadMaterialsCheckboxes() {
    const container = document.getElementById('materialCheckboxes');
    if (!container) return;
    try {
        const [elementsRes, alloysRes] = await Promise.all([
            fetch('/api/elements'),
            fetch('/api/alloys')
        ]);
        const elements = elementsRes.ok ? await elementsRes.json() : [];
        const alloys = alloysRes.ok ? await alloysRes.json() : [];

        if (elements.length === 0 && alloys.length === 0) {
            container.innerHTML = '<div class="empty-state">Материалы не найдены</div>';
            return;
        }

        let html = '';
        elements.forEach(el => {
            html += `
                <label class="checkbox-item">
                    <input type="checkbox" name="material_ids" value="${el.material_id}">
                    <span class="cb-name">${escapeHtml(el.name)}</span>
                    <span class="cb-tag element">Элемент</span>
                </label>
            `;
        });
        alloys.forEach(al => {
            html += `
                <label class="checkbox-item">
                    <input type="checkbox" name="material_ids" value="${al.material_id}">
                    <span class="cb-name">${escapeHtml(al.name)}</span>
                    <span class="cb-tag alloy">Сплав</span>
                </label>
            `;
        });
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state" style="color:#ef4444;">Ошибка загрузки материалов</div>';
        console.error(e);
    }
}

async function loadBladesSelect() {
    const bladeSelect = document.getElementById('blade_id');
    if (!bladeSelect) return;
    try {
        const res = await fetch('/api/blades');
        if (!res.ok) throw new Error('Ошибка загрузки');
        const blades = await res.json();
        if (blades.length === 0) {
            bladeSelect.innerHTML = '<option value="" disabled selected>Нет лопаток</option>';
        } else {
            let options = '<option value="" disabled selected>Выберите лопатку...</option>';
            blades.forEach(b => {
                options += `<option value="${b.blade_id}">${escapeHtml(b.name)}</option>`;
            });
            bladeSelect.innerHTML = options;
        }
    } catch (e) {
        bladeSelect.innerHTML = '<option value="" disabled selected>Ошибка загрузки</option>';
        console.error('Ошибка загрузки лопаток:', e);
    }
}

async function loadAssembliesSelect() {
    const assemblySelect = document.getElementById('assembly_id');
    if (!assemblySelect) return;
    try {
        const res = await fetch('/api/assemblies');
        if (!res.ok) throw new Error('Ошибка загрузки');
        const assemblies = await res.json();
        let options = '<option value="" selected>Не выбрано</option>';
        assemblies.forEach(a => {
            options += `<option value="${a.blade_assembly_id}">${escapeHtml(a.name)}</option>`;
        });
        assemblySelect.innerHTML = options;
    } catch (e) {
        assemblySelect.innerHTML = '<option value="" selected>Не выбрано (ошибка)</option>';
        console.error('Ошибка загрузки объединений:', e);
    }
}

async function loadInitialConditionsSelect() {
    const select = document.getElementById('initial_conditions_id');
    if (!select) return;
    try {
        const res = await fetch('/initial-conditions/api/list');
        if (!res.ok) throw new Error('Ошибка загрузки');
        const ics = await res.json();
        if (ics.length === 0) {
            select.innerHTML = '<option value="" disabled selected>Нет наборов</option>';
        } else {
            let options = '<option value="" disabled selected>Выберите набор...</option>';
            ics.forEach(ic => {
                options += `<option value="${ic.initial_conditions_id}">${escapeHtml(ic.name)}</option>`;
            });
            select.innerHTML = options;
        }
    } catch (e) {
        select.innerHTML = '<option value="" disabled selected>Ошибка загрузки</option>';
        console.error('Ошибка загрузки начальных условий:', e);
    }
}

async function loadSimulationsList() {
    const tbody = document.getElementById('simulations-table-body');
    if (!tbody) return;
    try {
        const res = await fetch('/simulation/api/simulations');
        if (!res.ok) throw new Error('Ошибка загрузки');
        const sims = await res.json();
        if (sims.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">Расчеты еще не выполнялись</td></tr>';
            return;
        }
        let html = '';
        sims.forEach(s => {
            const statusBadge = s.status === 'completed' ? '<span class="badge badge-success">✅ Готово</span>' :
                                s.status === 'running' ? '<span class="badge badge-warning">⏳ Запущен</span>' :
                                s.status === 'failed' ? '<span class="badge badge-danger">❌ Ошибка</span>' :
                                '<span class="badge badge-secondary">' + s.status + '</span>';
            const downloadBtn = (s.status === 'completed' && s.has_vtk) ?
                `<a href="/simulation/${s.simulation_id}/download" class="btn-view btn-sm">📥 Скачать .vtk</a>` :
                '<span class="badge badge-warning">⏳ Нет файла</span>';
            const logBtn = (s.status === 'failed') ?
                `<button class="btn-log" onclick="fetchAndShowLog(${s.simulation_id})">📄 Лог</button>` : '';

            // Оборачиваем кнопки действия в контейнер
            const actionsHtml = `<div class="table-actions" style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">${downloadBtn} ${logBtn}</div>`;

            html += `
                <tr>
                    <td><span class="id-badge">#${s.simulation_id}</span></td>
                    <td><strong>${escapeHtml(s.name)}</strong></td>
                    <td>${escapeHtml(s.blade_name)}</td>
                    <td>${s.created_at}</td>
                    <td>${statusBadge}</td>
                    <td>${actionsHtml}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="color:#ef4444">Ошибка загрузки</td></tr>';
        console.error(e);
    }
}

function refreshSimulationsList() {
    loadSimulationsList();
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    loadMaterialsCheckboxes();
    loadBladesSelect();
    loadAssembliesSelect();
    loadInitialConditionsSelect();
    loadSimulationsList();

    const form = document.getElementById('simForm');
    if (form) form.onsubmit = createSimulation;
});

// escapeHtml глобально
if (typeof escapeHtml !== 'function') {
    window.escapeHtml = function(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };
}

// Делаем fetchAndShowLog глобальной, чтобы вызывать из onclick
window.fetchAndShowLog = fetchAndShowLog;