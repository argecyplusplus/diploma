import numpy as np
import os
import sys
import matplotlib
matplotlib.use('Agg') # СТРОГО ЗДЕСЬ для работы на сервере/Flask
import matplotlib.pyplot as plt

def plot_from_npz(filename, output_dir):
    # Загрузка данных
    if not os.path.exists(filename):
        print(f"ОШИБКА: Файл {filename} не найден!")
        return

    data = np.load(filename)
    l_grid = data['l_grid']
    t_array = data['t_array']
    A = data['A']
    B = data['B']
    h = data['h'] if 'h' in data else 0.0003
    T_surface = A + B * h

    # График 1: Эволюция во времени
    plt.figure(figsize=(10, 6))
    plt.plot(t_array, A[len(l_grid)//2, :], label='Центр покрытия')
    plt.plot(t_array, T_surface[len(l_grid)//2, :], label='Внешняя поверхность')
    plt.xlabel('Время, с')
    plt.ylabel('Температура, К')
    plt.title('Температура в центре и на поверхности (v1)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_time_v1.png'), dpi=150)
    plt.close()

    # График 2: По профилю
    plt.figure(figsize=(10, 6))
    for t_idx in [0, len(t_array)//4, len(t_array)//2, -1]:
        plt.plot(l_grid, A[:, t_idx], label=f't = {t_array[t_idx]:.2f} с')
    plt.xlabel('Координата вдоль профиля, м')
    plt.ylabel('Температура, К')
    plt.title('Распределение по профилю (v1)')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_profile_v1.png'), dpi=150)
    plt.close()

    # График 3: Карта
    plt.figure(figsize=(10, 6))
    plt.imshow(A, aspect='auto', extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]],
               origin='lower', cmap='hot')
    plt.colorbar(label='Температура, К')
    plt.xlabel('Время, с')
    plt.ylabel('Координата вдоль профиля, м')
    plt.title('Карта температур (v1)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'plot_heatmap_v1.png'), dpi=150)
    plt.close()
    
    print(f"УСПЕХ: Графики v1 сохранены в {output_dir}")

if __name__ == "__main__":
    # --- ЛОГИКА ПОИСКА ПУТЕЙ ---
    # 1. Находим корень проекта (этот скрипт в scripts/v_001/ или v1)
    current_script_path = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_script_path)))
    
    # 2. Путь к папке результатов v1
    target_dir = os.path.join(project_root, 'results', 'v1')
    
    # 3. Путь к файлу данных, который создал основной скрипт
    data_file = os.path.join(target_dir, 'stable_results_from_gauss_v1.npz')

    # Запуск отрисовки
    plot_from_npz(data_file, target_dir)