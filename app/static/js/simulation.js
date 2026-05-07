// static/js/simulation.js

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
        resetBtn(); return;
    }
    const bladeId = form.querySelector('[name="blade_id"]').value;
    const assemblyId = form.querySelector('[name="assembly_id"]').value;
    if ((bladeId && assemblyId) || (!bladeId && !assemblyId)) {
        alert('❌ Выберите либо лопатку, либо объединение');
        resetBtn(); return;
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

function pollStatus(simId) {
    const interval = setInterval(async () => {
        const resp = await fetch(`/simulation/${simId}/status`);
        const statusData = await resp.json();
        if (statusData.status === 'completed' || statusData.status === 'failed') {
            clearInterval(interval);
            await loadSimulationsList();
            if (statusData.status === 'completed') {
                alert('✅ Расчет завершен! Результат появится в истории.');
            } else {
                alert('❌ Ошибка расчета. Проверьте консоль.');
            }
            const btn = document.getElementById('submitBtn');
            if (btn) {
                btn.disabled = false;
                const btnText = btn.querySelector('.btn-text');
                const btnLoader = btn.querySelector('.btn-loader');
                if (btnText) btnText.style.display = 'inline';
                if (btnLoader) btnLoader.style.display = 'none';
            }
        } else {
            const btnLoader = document.querySelector('#submitBtn .btn-loader');
            if (btnLoader) btnLoader.textContent = `⏳ ${statusData.status}...`;
        }
    }, 2000);
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
            container.innerHTML = '<div style="padding:10px; color:#64748b; text-align:center;">Материалы не найдены</div>';
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
        container.innerHTML = '<div style="padding:10px; color:#ef4444; text-align:center;">Ошибка загрузки материалов</div>';
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
            html += `
                <tr>
                    <td><span class="id-badge">#${s.simulation_id}</span></td>
                    <td><strong>${escapeHtml(s.name)}</strong></td>
                    <td>${escapeHtml(s.blade_name)}</td>
                    <td>${s.created_at}</td>
                    <td>${statusBadge}</td>
                    <td>${downloadBtn}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = '</tr><td colspan="6" class="text-center" style="color:#ef4444">Ошибка загрузки</td></tr>';
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

// Глобальные функции, используемые в onsubmit и onclick, уже определены.
// escapeHtml должна быть определена в base.js, но на всякий случай продублируем
if (typeof escapeHtml !== 'function') {
    window.escapeHtml = function(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };
}