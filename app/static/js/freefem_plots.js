let currentPlots = [];
let currentPlotIndex = 0;
let pollingInterval = null;

async function loadFreeFemPlots() {
    const simId = parseInt(window.location.pathname.split('/').slice(-2)[0]);
    const container = document.getElementById('freefemPlotsContent');

    if (!container) return;

    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }

    container.innerHTML = `
        <div class="status-message">
            <div class="conversion-status">
                <div class="conversion-spinner"></div>
                <div class="conversion-text">⏳ Поиск графиков FreeFEM...</div>
            </div>
        </div>
    `;

    await fetchPlots(simId);
}

async function fetchPlots(simId) {
    const container = document.getElementById('freefemPlotsContent');
    if (!container) return;

    try {
        const res = await fetch(`/simulation/${simId}/freefem_plots`);
        const data = await res.json();

        if (!res.ok) throw new Error(data.error || 'Ошибка загрузки');

        if (data.progress && data.progress.total > 0 && data.progress.converted < data.progress.total) {
            showConversionProgress(data.progress.converted, data.progress.total);

            if (!pollingInterval) {
                pollingInterval = setInterval(() => fetchPlots(simId), 1000);
            }
            return;
        }

        if (data.success && data.plots && data.plots.length > 0) {
            if (pollingInterval) {
                clearInterval(pollingInterval);
                pollingInterval = null;
            }

            currentPlots = data.plots;
            currentPlotIndex = 0;

            container.innerHTML = '<div class="status-message">🖼️ Загрузка изображений...</div>';
            await preloadAllImages(currentPlots);
            renderPlotGallery();
            return;
        }

        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        container.innerHTML = `<div class="status-message">${data.message || 'Графики FreeFEM не найдены'}</div>`;

    } catch(e) {
        console.error('Error:', e);
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        container.innerHTML = `<div class="status-message" style="color:#ef4444;">❌ Ошибка: ${e.message}</div>`;
    }
}

function showConversionProgress(converted, total) {
    const container = document.getElementById('freefemPlotsContent');
    if (!container) return;

    const percent = total > 0 ? Math.round((converted / total) * 100) : 0;

    container.innerHTML = `
        <div class="status-message">
            <div class="conversion-status">
                <div class="conversion-spinner"></div>
                <div class="conversion-text">🖼️ Конвертация графиков FreeFEM...</div>
                <div class="conversion-progress-bar">
                    <div class="conversion-progress-fill" style="width: ${percent}%"></div>
                </div>
                <div class="conversion-count">${converted} из ${total} графиков готово</div>
            </div>
        </div>
    `;
}

async function preloadAllImages(plots) {
    const promises = plots.map((plot) => {
        return new Promise((resolve) => {
            const img = new Image();
            img.onload = () => resolve(true);
            img.onerror = () => resolve(false);
            img.src = plot.url;
        });
    });
    await Promise.all(promises);
}

function renderPlotGallery() {
    const container = document.getElementById('freefemPlotsContent');
    if (!container) return;

    if (currentPlots.length === 0) {
        container.innerHTML = '<div class="status-message">Нет графиков для отображения</div>';
        return;
    }

    const current = currentPlots[currentPlotIndex];

    let html = `
        <div class="plot-gallery">
            <div class="plot-counter">${currentPlotIndex + 1} из ${currentPlots.length}</div>
            <div class="plot-title">${escapeHtml(current.name)}</div>
            <div class="plot-image-container">
                <img src="${current.url}" alt="${escapeHtml(current.name)}" class="plot-image">
            </div>
            <div class="plot-nav">
                <button class="btn-secondary" onclick="prevPlot()" ${currentPlotIndex === 0 ? 'disabled' : ''}>◀ Предыдущий</button>
                <button class="btn-secondary" onclick="nextPlot()" ${currentPlotIndex === currentPlots.length - 1 ? 'disabled' : ''}>Следующий ▶</button>
            </div>
            <div class="plot-thumbnails">
                ${currentPlots.map((plot, idx) => `
                    <div class="plot-thumbnail ${idx === currentPlotIndex ? 'active' : ''}" onclick="goToPlot(${idx})">
                        <img src="${plot.url}" alt="${escapeHtml(plot.name)}">
                        <span>${escapeHtml(plot.name.substring(0, 20))}${plot.name.length > 20 ? '...' : ''}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    container.innerHTML = html;
}

function nextPlot() {
    if (currentPlotIndex < currentPlots.length - 1) {
        currentPlotIndex++;
        renderPlotGallery();
    }
}

function prevPlot() {
    if (currentPlotIndex > 0) {
        currentPlotIndex--;
        renderPlotGallery();
    }
}

function goToPlot(index) {
    if (index >= 0 && index < currentPlots.length) {
        currentPlotIndex = index;
        renderPlotGallery();
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}