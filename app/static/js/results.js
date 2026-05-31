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
            const container = document.getElementById('plotsContent');
            if (container && !container.querySelector('.status-running')) {
                container.innerHTML = '<div class="status-message status-running">⏳ Расчёт выполняется... Обновите страницу после завершения.</div>';
            }
        } else if (data.status === 'completed') {
            if (statusPollInterval) clearInterval(statusPollInterval);
            // Для задачи 1 показываем только файлы
            if (currentTaskType === '1') {
                const container = document.getElementById('plotsContent');
                if (container) {
                    container.innerHTML = '<div class="status-message">✅ Расчёт завершён! Файлы результатов доступны для скачивания выше.</div>';
                }
            } else {
                await loadPlots();
            }
            await loadFiles();
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

async function loadPlots() {
    const container = document.getElementById('plotsContent');
    if (!container) return;

    // Для задачи 1 не загружаем графики
    if (currentTaskType === '1') {
        container.innerHTML = '<div class="status-message">Для этой задачи графики не генерируются. Используйте VTK файл для визуализации.</div>';
        return;
    }

    container.innerHTML = '<div class="status-message">⏳ Загрузка графиков...</div>';
    try {
        const res = await fetch(`/simulation/${simId}/plots`);
        if (!res.ok) throw new Error('Ошибка загрузки');
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        let html = '';
        for (const [title, imgBase64] of Object.entries(data)) {
            if (title === 'error') continue;
            const isGif = title === 'Анимация температурного поля';
            const mimeType = isGif ? 'image/gif' : 'image/png';
            html += `
                <div style="margin-bottom: 30px;">
                    <h4>${escapeHtml(title)}</h4>
                    <img src="data:${mimeType};base64,${imgBase64}" style="max-width:100%; border:1px solid #e2e8f0; border-radius:8px;">
                </div>
            `;
        }
        if (html === '') html = '<div class="status-message">Нет данных для отображения</div>';
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка: ${e.message}</div>`;
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
    if (currentTaskType !== '1') {
        await loadPlots();
    }
});