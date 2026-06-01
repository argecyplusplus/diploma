let currentPollInterval = null;
let currentSimId = null;

const taskHints = {
    gas_dynamics: 'Для задачи 1 набор начальных условий должен содержать: параметры потенциального потока (beta, B), идентификатор границы (S1), хорду лопасти, параметры построения сетки (NC, NSp, NSm, NSpm). Временные и тепловые параметры НЕ используются.',
    thermal_field: 'Для задачи 2 набор начальных условий должен содержать: временные параметры (dt, nbT), начальную температуру материала, хорду лопасти, параметры построения сетки (NC, NSp, NSm, NSpm, NSpn).',
    thermal_stress: 'Для задачи 3 необходимы: временные параметры, начальная температура материала, параметры упругости (b, nu, KLT), параметры вывода напряжений (delt, Npt), конструктивные параметры сетки, хорда лопасти, идентификатор границы S1.',
    thermal_transient: 'Для задачи 4 необходимы: временные параметры (dt, nbT), начальная температура материала, параметры покрытия (толщина, теплопроводность), хорда лопасти, параметры построения сетки (NC, NSp, NSm, NSpm, NSpn).'
};

function updateTaskHint() {
    const selected = document.querySelector('input[name="task_type"]:checked');
    if (!selected) return;
    const hint = taskHints[selected.value] || 'Выберите задачу';
    const helpDiv = document.getElementById('taskHelpText');
    if (helpDiv) helpDiv.innerHTML = hint;
    updateObjectHint();
}

async function validateInitialConditionForTask(icId) {
    const selectedTask = document.querySelector('input[name="task_type"]:checked');
    if (!selectedTask) return;
    const required = selectedTask.dataset.requires.split(',');
    try {
        const resp = await fetch(`/initial-conditions/api/${icId}`);
        if (!resp.ok) throw new Error('Ошибка загрузки начальных условий');
        const data = await resp.json();
        const missing = [];
        if (required.includes('potential_flow') && (!data.potential_flow || Object.keys(data.potential_flow).length === 0))
            missing.push('Параметры потенциального потока');
        if (required.includes('boundaries') && (!data.boundaries || data.boundaries.length === 0))
            missing.push('Идентификаторы границ');
        if (required.includes('construction') && (!data.construction || Object.keys(data.construction).length === 0))
            missing.push('Параметры построения сетки');
        if (required.includes('blade_chord') && (!data.chords || data.chords.length === 0))
            missing.push('Хорда лопасти');
        if (required.includes('time_parameters') && (!data.time_parameters || Object.keys(data.time_parameters).length === 0))
            missing.push('Временные параметры');
        if (required.includes('initial_temps') && (!data.initial_temps || data.initial_temps.length === 0))
            missing.push('Начальная температура материала');
        if (required.includes('elasticity') && (!data.elasticity || Object.keys(data.elasticity).length === 0))
            missing.push('Параметры упругости (b, nu, KLT)');
        if (required.includes('stress_output') && (!data.stress_output || Object.keys(data.stress_output).length === 0))
            missing.push('Параметры вывода напряжений (delt, Npt)');

        const helpDiv = document.getElementById('taskHelpText');
        if (helpDiv) {
            if (missing.length) {
                helpDiv.innerHTML += `<br><span style="color:var(--status-err)">⚠️ В выбранном наборе отсутствуют: ${missing.join(', ')}. Расчёт может быть невозможен.</span>`;
            } else {
                helpDiv.innerHTML += `<br><span style="color:var(--status-ok)">✅ Все необходимые параметры присутствуют.</span>`;
            }
        }
    } catch(e) {
        console.error('Ошибка валидации начальных условий', e);
    }
}

function syncActiveTaskCard() {
    const selectedRadio = document.querySelector('input[name="task_type"]:checked');
    if (!selectedRadio) return;
    const cards = document.querySelectorAll('.task-card');
    cards.forEach(card => {
        const radio = card.querySelector('input[type="radio"]');
        if (radio && radio === selectedRadio) {
            card.classList.add('active');
        } else {
            card.classList.remove('active');
        }
    });
}

// Удаление одной симуляции
async function deleteSimulation(simId) {
    if (!confirm('Удалить расчёт и все связанные файлы?')) return;
    try {
        const res = await fetch(`/simulation/${simId}`, { method: 'DELETE' });
        if (res.ok) {
            alert('Расчёт удалён');
            loadSimulationsList();
        } else {
            const err = await res.json();
            alert('Ошибка: ' + err.error);
        }
    } catch(e) {
        alert('Ошибка: ' + e.message);
    }
}

// Очистка неудачных симуляций
async function cleanFailedSimulations() {
    if (!confirm('Удалить все расчёты со статусом "failed"?')) return;
    try {
        const res = await fetch('/simulation/failed', { method: 'DELETE' });
        if (res.ok) {
            const data = await res.json();
            alert(data.message);
            loadSimulationsList();
        } else {
            const err = await res.json();
            alert('Ошибка: ' + err.error);
        }
    } catch(e) {
        alert('Ошибка: ' + e.message);
    }
}

function viewResults(simId) {
    window.location.href = `/simulation/${simId}/results`;
}

// ===== ЗАПУСК РАСЧЁТА ПО КНОПКЕ =====
async function runSimulation(simId) {
    // Сначала получаем тип задачи
    let taskType = null;
    try {
        const res = await fetch('/simulation/api/simulations');
        const sims = await res.json();
        const sim = sims.find(s => s.simulation_id === simId);
        if (sim) taskType = sim.task_display;
    } catch(e) {
        console.error('Error getting task type:', e);
    }

    let message = 'Запустить расчёт?\n\nОткроется папка с файлом. Дважды кликните по файлу .edp, чтобы запустить FreeFEM++.';
    if (taskType === '3') {
        message = 'Запустить расчёт?\n\nПосле запуска FreeFEM++ и завершения расчёта нажмите "Обновить результаты" для отображения графиков.';
    }

    if (!confirm(message)) return;

    try {
        const res = await fetch(`/simulation/${simId}/run_local`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Ошибка запуска');

        if (data.instruction) {
            alert('✅ Папка с файлом открыта!\n\nНайдите файл simulation_' + simId + '.edp и дважды кликните по нему, чтобы запустить FreeFEM++.\n\nПосле завершения расчёта нажмите "Обновить результаты" на этой странице.');
        } else {
            alert('✅ FreeFEM++ запущен! После завершения расчёта обновите страницу.');
        }

        window.location.href = `/simulation/${simId}/results`;
    } catch(e) {
        alert('❌ Ошибка: ' + e.message);
    }
}

// ===== ПРОГРЕСС МОДАЛЬНОЕ ОКНО =====
function showProgressModal() {
    const modal = document.getElementById('progressModal');
    if (modal) modal.classList.add('active');
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('progressMessage').innerText = 'Подготовка...';
    document.getElementById('progressError').style.display = 'none';
    document.getElementById('progressShowLogBtn').style.display = 'none';
    const badge = document.getElementById('progressStatusBadge');
    if (badge) {
        badge.innerText = '⏳ Ожидание';
        badge.className = 'badge badge-secondary';
    }
}

function closeProgressModal() {
    const modal = document.getElementById('progressModal');
    if (modal) modal.classList.remove('active');
    currentSimId = null;
}

function updateProgressModal(data) {
    const modal = document.getElementById('progressModal');
    if (!modal || !modal.classList.contains('active')) return;
    let statusText = '', badgeClass = '', progress = data.progress || 0;
    switch (data.status) {
        case 'pending': statusText = '⏳ Ожидание'; badgeClass = 'badge-secondary'; break;
        case 'running': statusText = '🔄 Расчёт'; badgeClass = 'badge-warning'; break;
        case 'completed': statusText = '✅ Завершён'; badgeClass = 'badge-success'; progress = 100; break;
        case 'failed': statusText = '❌ Ошибка'; badgeClass = 'badge-danger'; break;
        default: statusText = data.status; badgeClass = 'badge-secondary';
    }
    document.getElementById('progressStatusBadge').innerText = statusText;
    document.getElementById('progressStatusBadge').className = `badge ${badgeClass}`;
    document.getElementById('progressFill').style.width = `${progress}%`;
    document.getElementById('progressPercent').innerText = `${Math.round(progress)}%`;
    if (data.status === 'running') {
        document.getElementById('progressMessage').innerText = 'Выполняется FreeFEM++...';
    } else if (data.status === 'pending') {
        document.getElementById('progressMessage').innerText = 'Генерация скрипта...';
    } else if (data.status === 'failed') {
        let errMsg = data.error_message || 'Неизвестная ошибка';
        document.getElementById('progressError').innerHTML = `⚠️ ${errMsg.substring(0, 200)}`;
        document.getElementById('progressError').style.display = 'block';
        document.getElementById('progressShowLogBtn').style.display = 'inline-block';
    } else if (data.status === 'completed') {
        document.getElementById('progressMessage').innerText = 'Расчёт завершён!';
        setTimeout(() => closeProgressModal(), 2000);
    }
}

// ===== ЗАГРУЗКА ОБЪЕКТА (ЛОПАТКИ/ОБЪЕДИНЕНИЯ) =====
async function loadObjectSelect() {
    const select = document.getElementById('objectSelect');
    if (!select) return;
    try {
        const [bladesRes, assembliesRes] = await Promise.all([
            fetch('/api/blades'),
            fetch('/api/assemblies')
        ]);
        const blades = bladesRes.ok ? await bladesRes.json() : [];
        const assemblies = assembliesRes.ok ? await assembliesRes.json() : [];
        let options = '<option value="" disabled selected>Выберите объект</option>';
        blades.forEach(b => {
            options += `<option value="blade_${b.blade_id}" data-type="blade" data-id="${b.blade_id}">Лопатка: ${escapeHtml(b.name)}</option>`;
        });
        assemblies.forEach(a => {
            options += `<option value="assembly_${a.blade_assembly_id}" data-type="assembly" data-id="${a.blade_assembly_id}">Объединение: ${escapeHtml(a.name)}</option>`;
        });
        select.innerHTML = options;
        updateObjectHint();
    } catch(e) {
        select.innerHTML = '<option value="" disabled selected>Ошибка загрузки</option>';
        console.error(e);
    }
}

function updateObjectHint() {
    const select = document.getElementById('objectSelect');
    const taskType = document.querySelector('input[name="task_type"]:checked');
    if (!taskType || !select) return;
    const small = document.getElementById('objectHint');
    if (taskType.value === 'gas_dynamics') {
        for (let option of select.options) {
            if (option.value && option.value.startsWith('assembly_')) {
                option.disabled = true;
            } else {
                option.disabled = false;
            }
        }
        if (small) small.innerText = ' (для газодинамики доступны только лопатки)';
        if (select.value && select.value.startsWith('assembly_')) select.value = '';
    } else {
        for (let option of select.options) {
            option.disabled = false;
        }
        if (small) small.innerText = ' (лопатка или объединение)';
    }
}

// ===== ЗАГРУЗКА НАЧАЛЬНЫХ УСЛОВИЙ =====
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

// ===== МАТЕРИАЛЫ (ЧЕКБОКСЫ) =====
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

// ===== ИСТОРИЯ РАСЧЁТОВ =====
// ===== ИСТОРИЯ РАСЧЁТОВ =====
async function loadSimulationsList() {
    const tbody = document.getElementById('simulations-table-body');
    if (!tbody) return;
    try {
        const res = await fetch('/simulation/api/simulations');
        if (!res.ok) throw new Error('Ошибка загрузки');
        const sims = await res.json();
        if (sims.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">Расчеты еще не выполнялись</td></tr>';
            return;
        }
        let html = '';
        sims.forEach(s => {
            const statusBadge = s.status === 'completed' ? '<span class="badge badge-success">✅ Готово</span>' :
                                s.status === 'running' ? '<span class="badge badge-warning">⏳ Запущен</span>' :
                                s.status === 'failed' ? '<span class="badge badge-danger">❌ Ошибка</span>' :
                                '<span class="badge badge-secondary">' + s.status + '</span>';

            const logBtn = (s.status === 'failed') ?
                `<button class="btn-log" onclick="fetchAndShowLog(${s.simulation_id})">Лог</button>` : '';

            const resultsBtn = `<button class="btn-secondary btn-sm" onclick="viewResults(${s.simulation_id})">Результаты</button>`;
            const deleteBtn = `<button class="btn-delete btn-sm" onclick="deleteSimulation(${s.simulation_id})">Удалить</button>`;
            const resetBtn = `<button class="btn-warning btn-sm" onclick="resetSimulation(${s.simulation_id})">Сбросить</button>`;

            // Кнопка Моделировать показывается для статусов: pending, failed, completed (можно перезапустить)
            const canRun = (s.status === 'pending' || s.status === 'failed' || s.status === 'completed');
            const runBtn = canRun ?
                `<button class="btn-run" onclick="runSimulation(${s.simulation_id})">Моделировать</button>` : '';

            const actionsHtml = `<div class="table-actions" style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">${runBtn} ${resetBtn} ${logBtn} ${resultsBtn} ${deleteBtn}</div>`;

            html += `
                <tr>
                    <td><span class="id-badge">#${s.simulation_id}</span></td>
                    <td><strong>${escapeHtml(s.name)}</strong></td>
                    <td>${s.task_display}</td>
                    <td>${escapeHtml(s.blade_name)}</td>
                    <td>${s.created_at}</td>
                    <td>${statusBadge}</td>
                    <td>${actionsHtml}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center" style="color:#ef4444">Ошибка загрузки</td></tr>';
        console.error(e);
    }
}

function refreshSimulationsList() {
    loadSimulationsList();
}

// ===== ЛОГ =====
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

// ===== СОЗДАНИЕ СИМУЛЯЦИИ =====
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

    const objectSelect = document.getElementById('objectSelect');
    const selectedOption = objectSelect.options[objectSelect.selectedIndex];
    if (!selectedOption || !selectedOption.value) {
        alert('❌ Выберите объект расчёта (лопатку или объединение)');
        resetBtn();
        return;
    }
    const type = selectedOption.dataset.type;
    const objId = parseInt(selectedOption.dataset.id);
    let bladeId = null, assemblyId = null;
    if (type === 'blade') bladeId = objId;
    else assemblyId = objId;

    const taskType = form.querySelector('input[name="task_type"]:checked').value;

    // Временная заглушка для четвёртой задачи
    if (taskType === 'thermal_transient') {
        alert('⚠️ Функционал четвёртой задачи временно недоступен. Ожидайте обновления.');
        resetBtn();
        return;
    }

    if (taskType === 'gas_dynamics' && assemblyId) {
        alert('Для газодинамики нельзя выбирать объединение, выберите конкретную лопатку');
        resetBtn();
        return;
    }
    if (taskType !== 'gas_dynamics' && !bladeId && !assemblyId) {
        alert('Для выбранной задачи необходимо выбрать лопатку или объединение');
        resetBtn();
        return;
    }

    const payload = {
        name: form.querySelector('[name="name"]').value,
        blade_id: bladeId,
        assembly_id: assemblyId,
        initial_conditions_id: parseInt(form.querySelector('[name="initial_conditions_id"]').value),
        material_ids: materialIds,
        task_type: taskType
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
        currentSimId = simId;

        // Показываем модалку с успешным созданием
        const modal = document.createElement('div');
        modal.className = 'modal-overlay active';
        modal.innerHTML = `
            <div class="modal" style="max-width: 450px;">
                <h3>Расчёт создан</h3>
                <div style="margin: 20px 0;">
                    <p>✅ Расчёт успешно создан и сохранён в истории.</p>
                    <p>Чтобы выполнить расчёт, нажмите кнопку <strong>«Моделировать»</strong> в истории расчётов.</p>
                    <p>После нажатия файл будет скачан, откроется FreeFEM++ и вы будете перенаправлены на страницу результатов.</p>
                </div>
                <div class="modal-actions">
                    <button class="btn-primary" onclick="window.location.href='/simulation'">Перейти к истории</button>
                    <button class="btn-secondary" onclick="this.closest('.modal-overlay').remove()">Закрыть</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

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

// ===== ОБРАБОТЧИКИ И ИНИЦИАЛИЗАЦИЯ =====
function setupEventListeners() {
    document.querySelectorAll('input[name="task_type"]').forEach(radio => {
        radio.addEventListener('change', () => {
            updateTaskHint();
            syncActiveTaskCard();
            const icSelect = document.getElementById('initial_conditions_id');
            if (icSelect && icSelect.value) validateInitialConditionForTask(icSelect.value);
            const objectSelect = document.getElementById('objectSelect');
            if (objectSelect) updateObjectHint();
        });
    });
    const icSelect = document.getElementById('initial_conditions_id');
    if (icSelect) {
        icSelect.addEventListener('change', (e) => {
            if (e.target.value) validateInitialConditionForTask(e.target.value);
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadMaterialsCheckboxes();
    loadObjectSelect();
    loadInitialConditionsSelect();
    loadSimulationsList();
    setupEventListeners();
    syncActiveTaskCard();
    const form = document.getElementById('simForm');
    if (form) form.onsubmit = createSimulation;
    window.deleteSimulation = deleteSimulation;
    window.cleanFailedSimulations = cleanFailedSimulations;
    window.viewResults = viewResults;
    window.fetchAndShowLog = fetchAndShowLog;
    window.closeProgressModal = closeProgressModal;
    window.runSimulation = runSimulation;
});

// escapeHtml
if (typeof escapeHtml !== 'function') {
    window.escapeHtml = function(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };
}

// Добавить в конец файла
async function resetSimulation(simId) {
    if (!confirm('Сбросить статус расчёта? Это позволит запустить его заново.')) return;
    try {
        const res = await fetch(`/simulation/${simId}/reset`, { method: 'POST' });
        if (!res.ok) throw new Error('Ошибка сброса');
        alert('✅ Статус сброшен');
        loadSimulationsList();
    } catch(e) {
        alert('❌ Ошибка: ' + e.message);
    }
}