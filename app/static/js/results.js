const simId = parseInt(window.location.pathname.split('/').slice(-2)[0]);
let statusPollInterval = null;
let currentTaskType = null;

async function getSimulationInfo() {
    try {
        const res = await fetch(`/simulation/api/simulations`);
        if (!res.ok) return;
        const sims = await res.json();
        const sim = sims.find(s => s.simulation_id === simId);
        if (sim) {
            currentTaskType = sim.task_display;
            console.log('Task type:', currentTaskType);
        }
    } catch(e) {
        console.error('Error getting sim info:', e);
    }
}

async function checkAndPollStatus() {
    try {
        const res = await fetch(`/simulation/${simId}/status`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.status === 'running') {
            if (!statusPollInterval) {
                statusPollInterval = setInterval(() => checkAndPollStatus(), 5000);
            }
        } else if (data.status === 'completed') {
            if (statusPollInterval) clearInterval(statusPollInterval);
            await loadFiles();
            await showAppropriateContent();
        } else if (data.status === 'failed') {
            if (statusPollInterval) clearInterval(statusPollInterval);
            const container = document.getElementById('plotsContent');
            if (container) {
                container.innerHTML = `<div class="status-message" style="color:#ef4444;">❌ Ошибка расчёта: ${data.error_message || 'Неизвестная ошибка'}</div>`;
            }
        }
    } catch(e) {
        console.error('Poll error:', e);
    }
}

async function showAppropriateContent() {
    const plotsContainer = document.getElementById('plotsContent');

    if (currentTaskType === '1') {
        plotsContainer.innerHTML = '<div class="status-message">✅ Расчёт завершён!<br>Визуализация результатов доступна через VTK файл.</div>';
    }
    else if (currentTaskType === '2') {
        // Задача 2: загружаем график температуры по контуру из TFout.csv
        await loadMatplotlibPlots();
    }
    else if (currentTaskType === '3') {
        // Задача 3: загружаем matplotlib графики из CSV
        await loadMatplotlibPlots();
    }
    else {
        plotsContainer.innerHTML = '<div class="status-message">Неизвестный тип задачи</div>';
    }
}

async function loadMatplotlibPlots() {
    const container = document.getElementById('plotsContent');
    if (!container) return;

    container.innerHTML = '<div class="status-message">⏳ Загрузка графиков...</div>';
    try {
        const res = await fetch(`/simulation/${simId}/plots`);
        if (!res.ok) {
            throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        const data = await res.json();

        if (!data || typeof data !== 'object') {
            throw new Error('Некорректный ответ от сервера');
        }

        if (data.error) {
            throw new Error(data.error);
        }

        let html = '';
        let hasContent = false;

        // Ключи для задачи 2
        if (data['Распределение температуры по контуру']) {
            html += `
                <div style="margin-bottom: 30px;">
                    <h4>Распределение температуры по контуру лопатки</h4>
                    <img src="data:image/png;base64,${data['Распределение температуры по контуру']}" style="max-width:100%; border:1px solid #e2e8f0; border-radius:8px;">
                </div>
            `;
            hasContent = true;
        }

        // Ключи для задачи 3
        const task3Keys = ['Профиль лопатки', 'Деформация Мизеса', 'Температура (поверхность)', 'Напряжение Мизеса'];
        for (const key of task3Keys) {
            if (data[key]) {
                html += `
                    <div style="margin-bottom: 30px;">
                        <h4>${escapeHtml(key)}</h4>
                        <img src="data:image/png;base64,${data[key]}" style="max-width:100%; border:1px solid #e2e8f0; border-radius:8px;">
                    </div>
                `;
                hasContent = true;
            }
        }

        // Другие возможные ключи
        for (const [key, value] of Object.entries(data)) {
            if (key !== 'error' && !task3Keys.includes(key) && key !== 'Распределение температуры по контуру') {
                html += `
                    <div style="margin-bottom: 30px;">
                        <h4>${escapeHtml(key)}</h4>
                        <img src="data:image/png;base64,${value}" style="max-width:100%; border:1px solid #e2e8f0; border-radius:8px;">
                    </div>
                `;
                hasContent = true;
            }
        }

        if (!hasContent) {
            container.innerHTML = '<div class="status-message">Нет данных для отображения</div>';
        } else {
            container.innerHTML = html;
        }
    } catch(e) {
        console.error('Load matplotlib plots error:', e);
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка загрузки графиков: ${e.message}</div>`;
    }
}

async function loadFiles() {
    const container = document.getElementById('filesContent');
    if (!container) return;
    container.innerHTML = '<div class="status-message">Загрузка...</div>';
    try {
        const res = await fetch(`/simulation/${simId}/files`);
        if (!res.ok) throw new Error('Ошибка загрузки списка файлов');
        const files = await res.json();
        if (files.length === 0) {
            container.innerHTML = '<div class="status-message">Нет доступных файлов</div>';
            return;
        }
        let html = '';
        files.forEach(file => {
            let btnClass = 'btn-secondary';
            if (file.name === 'result.vtk') btnClass = 'btn-primary';
            let fileType = '';
            if (file.name === 'result.vtk') fileType = 'vtk';
            else if (file.name === 'Profout.csv') fileType = 'profout';
            else if (file.name === 'TSout.csv') fileType = 'tsout';
            else if (file.name === 'TEpsout.csv') fileType = 'tepsout';
            else fileType = file.name.split('.')[0].toLowerCase();

            html += `<a href="/simulation/${simId}/result/${fileType}" class="${btnClass}">📥 ${file.description}</a>`;
        });
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка: ${e.message}</div>`;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function checkStatusManually() {
    try {
        const res = await fetch(`/simulation/${simId}/status`);
        const data = await res.json();
        alert(`Статус расчёта: ${data.status}\nПрогресс: ${data.progress}%\n${data.error_message ? 'Ошибка: ' + data.error_message : ''}`);
        if (data.status === 'completed') {
            location.reload();
        }
    } catch(e) {
        alert('Ошибка: ' + e.message);
    }
}

async function checkCompletionManually() {
    try {
        const res = await fetch(`/simulation/${simId}/check_completion`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'completed') {
            alert('✅ Расчёт завершён! Страница будет обновлена.');
            location.reload();
        } else {
            alert(`Статус расчёта: ${data.status}\n${data.message || ''}`);
        }
    } catch(e) {
        alert('Ошибка: ' + e.message);
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    await getSimulationInfo();
    await loadFiles();
    await checkAndPollStatus();

    // Если статус уже completed, показываем соответствующий контент
    const statusRes = await fetch(`/simulation/${simId}/status`);
    const statusData = await statusRes.json();
    if (statusData.status === 'completed') {
        await showAppropriateContent();
    }
});