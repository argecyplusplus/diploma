const simId = parseInt(window.location.pathname.split('/').slice(-2)[0]);

// Добавить в начало файла
let statusPollInterval = null;

async function checkAndPollStatus() {
    try {
        const res = await fetch(`/simulation/${simId}/status`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.status === 'running') {
            if (!statusPollInterval) {
                statusPollInterval = setInterval(() => checkAndPollStatus(), 3000);
            }
            document.getElementById('statusMessage')?.remove();
            const container = document.getElementById('plotsContent');
            if (container && !container.querySelector('.status-running')) {
                container.innerHTML = '<div class="status-message status-running">⏳ Расчёт выполняется... Страница обновится автоматически.</div>';
            }
        } else if (data.status === 'completed') {
            if (statusPollInterval) clearInterval(statusPollInterval);
            await loadPlots();
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
    container.innerHTML = '<div class="status-message">⏳ Загрузка графиков...</div>';
    try {
        const res = await fetch(`/simulation/${simId}/plots`);
        if (!res.ok) throw new Error('Ошибка загрузки');
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        let html = '';
        // Перебираем все ключи – они уже содержат нормальные названия
        for (const [title, imgBase64] of Object.entries(data)) {
            if (title === 'error') continue;
            // Для анимации (GIF) тип image/gif, для остальных image/png
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
            html += `<a href="/simulation/${simId}/result/${file.name.split('.')[0].toLowerCase()}" class="${btnClass}">📥 ${file.description}</a>`;
        });
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка: ${e.message}</div>`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadPlots();
    loadFiles();
    checkAndPollStatus();
});

// Вспомогательная функция
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}