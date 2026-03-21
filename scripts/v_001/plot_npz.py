import numpy as np
import matplotlib.pyplot as plt
import os



def plot_from_npz(filename, output_dir='../../static/results'):
    # Создаем папку, если она еще не существует
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)


    # Загрузка данных из архива .npz
    data = np.load(filename)
    # Список доступных переменных
    print("Содержимое архива:", list(data.keys()))
    # Популярные имена: l_grid, t_array, A, B
    l_grid = data['l_grid']
    t_array = data['t_array']
    A = data['A']
    B = data['B']
    # Толщина покрытия (если есть)
    h = data['h'] if 'h' in data else 0.0003
    # Температура на внешней поверхности покрытия
    T_surface = A + B * h

    # График 1: эволюция температуры в центре и на поверхности покрытия
    plt.figure(figsize=(10, 6))
    plt.plot(t_array, A[len(l_grid)//2, :], label='Центр покрытия')
    plt.plot(t_array, T_surface[len(l_grid)//2, :], label='Внешняя поверхность')
    plt.xlabel('Время, с')
    plt.ylabel('Температура, К')
    plt.title('Температура в центре и на поверхности покрытия (середина профиля)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_evolution_v001.png'))
    plt.close() # Важно закрыть, чтобы не накладывались

    # График 2: температурное поле вдоль профиля в разные моменты времени (в центре покрытия)
    plt.figure(figsize=(10, 6))
    for t_idx in [0, len(t_array)//4, len(t_array)//2, -1]:
        plt.plot(l_grid, A[:, t_idx], label=f't = {t_array[t_idx]:.2f} с')
    plt.xlabel('Координата вдоль профиля, м')
    plt.ylabel('Температура в центре покрытия, К')
    plt.title('Распределение температуры по профилю (центр покрытия)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_profile_v001.png'))
    plt.close()

    # График 3: карта температурного поля (центр покрытия)
    plt.figure(figsize=(10, 6))
    plt.imshow(
        A,
        aspect='auto',
        extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]],
        origin='lower',
        cmap='hot'
    )
    plt.colorbar(label='Температура, К')
    plt.xlabel('Время, с')
    plt.ylabel('Координата вдоль профиля, м')
    plt.title('Карта температурного поля (центр покрытия)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_heatmap_v001.png'))
    plt.close()

if __name__ == "__main__":
    # Замените имя файла на нужное
    plot_from_npz('stable_results_from_gauss_001.npz')
