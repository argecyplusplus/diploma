// static/js/initial_conditions.js

let materialsList = [];

// ================= ЗАГРУЗКА МАТЕРИАЛОВ =================
async function loadMaterialsForIC() {
    try {
        const [elementsRes, alloysRes] = await Promise.all([
            fetch('/api/elements'),
            fetch('/api/alloys')
        ]);
        const elements = elementsRes.ok ? await elementsRes.json() : [];
        const alloys = alloysRes.ok ? await alloysRes.json() : [];
        materialsList = [...elements, ...alloys];
    } catch (e) {
        console.error('Ошибка загрузки материалов:', e);
        materialsList = [];
    }
}

function getMaterialOptions(selectedId = null) {
    if (materialsList.length === 0) {
        return '<option value="">Материалы не загружены</option>';
    }
    let options = '<option value="">-- Выберите материал --</option>';
    materialsList.forEach(m => {
        const selected = (selectedId === m.material_id) ? 'selected' : '';
        options += `<option value="${m.material_id}" ${selected}>${escapeHtml(m.name)}</option>`;
    });
    return options;
}

function getMaterialOptionsWithSelected(selectedId) {
    return getMaterialOptions(selectedId);
}

// ================= ДИНАМИЧЕСКИЕ СТРОКИ =================
function addDynamicRow(containerId, fields, defaults = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const index = container.querySelectorAll('.dynamic-row').length;
    const row = document.createElement('div');
    row.className = 'dynamic-row';

    let html = '';
    fields.forEach(field => {
        const defaultValue = defaults[field] || '';
        const nameAttr = `${containerId.split('-')[0]}[${index}].${field}`;
        html += `<input type="${field === 'name' ? 'text' : 'number'}" 
                        step="${field === 'name' ? '1' : 'any'}"
                        name="${nameAttr}" 
                        placeholder="${field}" 
                        value="${defaultValue}" 
                        required>`;
    });
    html += `<button type="button" class="btn-remove" onclick="removeRow(this)">✕</button>`;

    row.innerHTML = html;
    container.appendChild(row);
    updateRemoveButtons(containerId);
}

function addTempRow() {
    const container = document.getElementById('initial-temps-list');
    if (!container) return;
    const index = container.querySelectorAll('.dynamic-row').length;
    const row = document.createElement('div');
    row.className = 'dynamic-row';
    row.innerHTML = `
        <select name="initial_temps[${index}].material_id" style="flex:1;">
            ${getMaterialOptions()}
        </select>
        <input type="number" step="any" name="initial_temps[${index}].value" placeholder="T, °C" required>
        <button type="button" class="btn-remove" onclick="removeRow(this)">✕</button>
    `;
    container.appendChild(row);
    updateRemoveButtons('initial-temps-list');
}

function addEiRow(selectedId = '', value = '') {
    const container = document.getElementById('ei-values-list');
    if (!container) return;
    const index = container.querySelectorAll('.dynamic-row').length;
    const row = document.createElement('div');
    row.className = 'dynamic-row';
    row.innerHTML = `
        <select name="ei_values[${index}].material_id" style="flex:2;">
            ${getMaterialOptions(selectedId)}
        </select>
        <input type="number" step="any" name="ei_values[${index}].value" placeholder="Ei, МПа" value="${value}" style="flex:1;">
        <button type="button" class="btn-remove" onclick="removeRow(this)">✕</button>
    `;
    container.appendChild(row);
    updateRemoveButtons('ei-values-list');
}

function removeRow(btn) {
    const row = btn.closest('.dynamic-row');
    const container = row.parentElement;
    row.remove();
    updateRemoveButtons(container.id);
}

function updateRemoveButtons(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const rows = container.querySelectorAll('.dynamic-row');
    rows.forEach(row => {
        const btn = row.querySelector('.btn-remove');
        if (btn) btn.style.display = rows.length > 1 ? 'block' : 'none';
    });
}

// ================= СОЗДАНИЕ НАБОРА =================
async function createIC(e) {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    const payload = {
        name: formData.get('name'),
        time_parameters: {},
        potential_flow: {},
        construction: {},
        elasticity: {},
        stress_output: {},
        boundaries: [],
        initial_temps: [],
        chords: [],
        ei_values: []
    };

    function setNested(obj, path, value) {
        const parts = path.split('.');
        let current = obj;
        for (let i = 0; i < parts.length - 1; i++) {
            if (!current[parts[i]]) current[parts[i]] = {};
            current = current[parts[i]];
        }
        const key = parts[parts.length - 1];
        current[key] = isNaN(value) ? value : parseFloat(value);
    }

    for (const [key, value] of formData.entries()) {
        if (key === 'name') continue;
        const arrayMatch = key.match(/^([a-z_]+)\[(\d+)\]\.([a-z_]+)$/);
        if (arrayMatch) {
            const [, arrayName, idx, field] = arrayMatch;
            const index = parseInt(idx);
            if (!payload[arrayName][index]) payload[arrayName][index] = {};
            payload[arrayName][index][field] = isNaN(value) ? value : parseFloat(value);
        } else {
            setNested(payload, key, value);
        }
    }

    // Очистка
    ['boundaries', 'initial_temps', 'chords'].forEach(key => {
        payload[key] = payload[key].filter(item => item && Object.keys(item).length);
    });

    // Дополнительно собираем ei_values
    const eiRows = document.querySelectorAll('#ei-values-list .dynamic-row');
    eiRows.forEach(row => {
        const select = row.querySelector('select');
        const input = row.querySelector('input[type="number"]');
        if (select && select.value && input && input.value) {
            payload.ei_values.push({
                material_id: parseInt(select.value),
                value: parseFloat(input.value)
            });
        }
    });

    try {
        const res = await fetch('/initial-conditions/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            alert('✅ Набор сохранён!');
            location.reload();
        } else {
            alert('❌ Ошибка: ' + JSON.stringify(data.error || 'Неизвестная'));
        }
    } catch (err) {
        alert('❌ Ошибка сети: ' + err.message);
    }
}

// ================= РЕДАКТИРОВАНИЕ НАБОРА =================
async function editIC(id) {
    try {
        const res = await fetch(`/initial-conditions/api/${id}`);
        if (!res.ok) throw new Error('Ошибка загрузки');
        const data = await res.json();

        // Заполнение базовых полей
        const form = document.getElementById('icForm');
        form.querySelector('input[name="name"]').value = data.name;
        form.querySelector('input[name="time_parameters.time"]').value = data.time_parameters.time;
        form.querySelector('input[name="time_parameters.dt"]').value = data.time_parameters.dt;
        form.querySelector('input[name="time_parameters.nbT"]').value = data.time_parameters.nbT;
        form.querySelector('input[name="time_parameters.Nplot"]').value = data.time_parameters.Nplot;
        form.querySelector('input[name="potential_flow.beta"]').value = data.potential_flow.beta;
        form.querySelector('input[name="potential_flow.B"]').value = data.potential_flow.B;
        form.querySelector('input[name="construction.NC"]').value = data.construction.NC;
        form.querySelector('input[name="construction.NSp"]').value = data.construction.NSp;
        form.querySelector('input[name="construction.NSm"]').value = data.construction.NSm;
        form.querySelector('input[name="construction.NSpn"]').value = data.construction.NSpn;
        form.querySelector('input[name="construction.NSpm"]').value = data.construction.NSpm;
        form.querySelector('input[name="elasticity.b"]').value = data.elasticity.b;
        form.querySelector('input[name="elasticity.nu"]').value = data.elasticity.nu;
        form.querySelector('input[name="elasticity.KLT"]').value = data.elasticity.KLT;
        form.querySelector('input[name="stress_output.coef"]').value = data.stress_output.coef;
        form.querySelector('input[name="stress_output.delt"]').value = data.stress_output.delt;
        form.querySelector('input[name="stress_output.Npt"]').value = data.stress_output.Npt;

        // Заполнение динамических списков
        function fillDynamicList(containerId, items, fieldMapping) {
            const container = document.getElementById(containerId);
            container.innerHTML = '';
            items.forEach((item, idx) => {
                const row = document.createElement('div');
                row.className = 'dynamic-row';
                let html = '';
                for (const [key, cfg] of Object.entries(fieldMapping)) {
                    const inputValue = item[cfg.field] ?? '';
                    html += `<input type="${cfg.type}" step="${cfg.step}" 
                                   name="${containerId.split('-')[0]}[${idx}].${key}" 
                                   value="${inputValue}" 
                                   placeholder="${cfg.placeholder}" 
                                   ${cfg.required ? 'required' : ''}>`;
                }
                html += `<button type="button" class="btn-remove" onclick="removeRow(this)">✕</button>`;
                row.innerHTML = html;
                container.appendChild(row);
            });
            updateRemoveButtons(containerId);
        }

        fillDynamicList('boundaries-list', data.boundaries, {
            name: {type: 'text', step: '1', placeholder: 'Имя', required: true, field: 'name'},
            value: {type: 'number', step: 'any', placeholder: 'Значение', required: true, field: 'value'}
        });
        fillDynamicList('chords-list', data.chords, {
            name: {type: 'text', step: '1', placeholder: 'Имя', required: true, field: 'name'},
            value: {type: 'number', step: 'any', placeholder: 'Значение', required: true, field: 'value'}
        });

        // Начальные температуры
        const initTempsContainer = document.getElementById('initial-temps-list');
        initTempsContainer.innerHTML = '';
        data.initial_temps.forEach((t, idx) => {
            const row = document.createElement('div');
            row.className = 'dynamic-row';
            row.innerHTML = `
                <select name="initial_temps[${idx}].material_id">
                    ${getMaterialOptions(t.material_id)}
                </select>
                <input type="number" step="any" name="initial_temps[${idx}].value" value="${t.value}" placeholder="T, °C" required>
                <button type="button" class="btn-remove" onclick="removeRow(this)">✕</button>
            `;
            initTempsContainer.appendChild(row);
        });
        updateRemoveButtons('initial-temps-list');

        // Ei значения
        const eiContainer = document.getElementById('ei-values-list');
        eiContainer.innerHTML = '';
        if (data.ei_values && data.ei_values.length) {
            data.ei_values.forEach((ei, idx) => {
                const row = document.createElement('div');
                row.className = 'dynamic-row';
                row.innerHTML = `
                    <select name="ei_values[${idx}].material_id" style="flex:2;">
                        ${getMaterialOptions(ei.material_id)}
                    </select>
                    <input type="number" step="any" name="ei_values[${idx}].value" value="${ei.value}" placeholder="Ei, МПа" style="flex:1;">
                    <button type="button" class="btn-remove" onclick="removeRow(this)">✕</button>
                `;
                eiContainer.appendChild(row);
            });
        } else {
            addEiRow();
        }
        updateRemoveButtons('ei-values-list');

        // Меняем обработчик отправки на обновление
        form.dataset.editId = id;
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.textContent = '💾 Обновить набор';
        form.onsubmit = (e) => updateIC(e, id);

        form.scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        alert('Ошибка загрузки данных: ' + err.message);
    }
}

async function updateIC(e, id) {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    const payload = {
        name: formData.get('name'),
        time_parameters: {},
        potential_flow: {},
        construction: {},
        elasticity: {},
        stress_output: {},
        boundaries: [],
        initial_temps: [],
        chords: [],
        ei_values: []
    };

    function setNested(obj, path, value) {
        const parts = path.split('.');
        let current = obj;
        for (let i = 0; i < parts.length - 1; i++) {
            if (!current[parts[i]]) current[parts[i]] = {};
            current = current[parts[i]];
        }
        const key = parts[parts.length - 1];
        current[key] = isNaN(value) ? value : parseFloat(value);
    }

    for (const [key, value] of formData.entries()) {
        if (key === 'name') continue;
        const arrayMatch = key.match(/^([a-z_]+)\[(\d+)\]\.([a-z_]+)$/);
        if (arrayMatch) {
            const [, arrayName, idx, field] = arrayMatch;
            const index = parseInt(idx);
            if (!payload[arrayName][index]) payload[arrayName][index] = {};
            payload[arrayName][index][field] = isNaN(value) ? value : parseFloat(value);
        } else {
            setNested(payload, key, value);
        }
    }

    // Очистка массивов
    ['boundaries', 'initial_temps', 'chords', 'ei_values'].forEach(key => {
        if (payload[key]) payload[key] = payload[key].filter(item => item && Object.keys(item).length);
    });

    // Дополнительно собираем ei_values из динамических строк (на случай, если они не попали в FormData)
    const eiRows = document.querySelectorAll('#ei-values-list .dynamic-row');
    payload.ei_values = [];
    eiRows.forEach(row => {
        const select = row.querySelector('select');
        const input = row.querySelector('input[type="number"]');
        if (select && select.value && input && input.value) {
            payload.ei_values.push({
                material_id: parseInt(select.value),
                value: parseFloat(input.value)
            });
        }
    });

    try {
        const res = await fetch(`/initial-conditions/api/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            alert('Набор обновлён');
            location.reload();
        } else {
            const err = await res.json();
            alert('Ошибка: ' + JSON.stringify(err.error));
        }
    } catch (err) {
        alert('Ошибка сети: ' + err.message);
    }
}

// ================= ЗАГРУЗКА СПИСКА НАБОРОВ =================
async function loadICsTable() {
    const tbody = document.getElementById('icTableBody');
    try {
        const res = await fetch('/initial-conditions/api/list');
        if (!res.ok) throw new Error('Ошибка загрузки');
        const ics = await res.json();
        if (ics.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center">Наборы не найдены</td></tr>';
        } else {
            tbody.innerHTML = ics.map(ic => `
                <tr>
                    <td>${ic.initial_conditions_id}</td>
                    <td>${escapeHtml(ic.name)}</td>
                    <td>
                        <button class="btn-edit" onclick="editIC(${ic.initial_conditions_id})">✏️</button>
                        <button class="btn-delete" onclick="deleteIC(${ic.initial_conditions_id})">🗑️</button>
                    </td>
                </tr>
            `).join('');
        }
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="3" class="text-center" style="color:#ef4444">Ошибка загрузки</td></tr>';
        console.error(e);
    }
}

async function deleteIC(id) {
    if (!confirm('Удалить этот набор начальных условий?')) return;
    try {
        const res = await fetch(`/initial-conditions/${id}`, { method: 'DELETE' });
        if (res.ok) {
            alert('✅ Удалено');
            location.reload();
        } else {
            alert('❌ Ошибка удаления');
        }
    } catch (e) {
        alert('❌ Ошибка: ' + e.message);
    }
}

// ================= ИНИЦИАЛИЗАЦИЯ =================
document.addEventListener('DOMContentLoaded', async () => {
    await loadMaterialsForIC();
    await loadICsTable();

    // Инициализация динамических списков
    ['boundaries-list', 'chords-list', 'initial-temps-list', 'ei-values-list'].forEach(id => {
        updateRemoveButtons(id);
        if (id === 'ei-values-list') addEiRow();
    });

    const form = document.getElementById('icForm');
    if (form) form.onsubmit = createIC;
});

// Утилита escapeHtml
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}