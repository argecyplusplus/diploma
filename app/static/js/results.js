const simId = parseInt(window.location.pathname.split('/').slice(-2)[0]);

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
        for (const [name, imgBase64] of Object.entries(data)) {
            if (name === 'error') continue;
            html += `<div><h4>${name}</h4><img src="data:image/png;base64,${imgBase64}" style="max-width:100%; margin-bottom:20px;"></div>`;
        }
        if (html === '') html = '<div class="status-message">Нет данных для отображения</div>';
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">Ошибка: ${e.message}</div>`;
    }
}

document.addEventListener('DOMContentLoaded', loadPlots);