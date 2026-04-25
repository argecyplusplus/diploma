import numpy as np
import matplotlib.pyplot as plt
import os
import matplotlib
matplotlib.use('Agg') # Для работы в фоновом режиме

def compare_results():
    # Находим корень проекта (скрипт в /scripts/compare_v/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    
    # Пути к исходным данным
    file_v001 = os.path.join(project_root, 'results', 'v001', 'stable_results_from_gauss_v001.npz')
    file_v1 = os.path.join(project_root, 'results', 'v1', 'stable_results_from_gauss_v1.npz')
    
    # Папка для сохранения сравнения
    output_dir = os.path.join(project_root, 'results', 'comparison')
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(file_v001) or not os.path.exists(file_v1):
        print(f"ERROR: Один из файлов не найден для сравнения")
        return

    # Загрузка
    d001 = np.load(file_v001)
    d1 = np.load(file_v1)
    
    l_grid = d001['l_grid']
    t_array = d001['t_array']
    A_001 = d001['A']
    A_1 = d1['A']

    # График 1: Сравнение во времени (центр)
    plt.figure(figsize=(10, 6))
    center_idx = len(l_grid) // 2
    plt.plot(t_array, A_001[center_idx, :], 'r--', label='v = 0.01 м/с (v001)')
    plt.plot(t_array, A_1[center_idx, :], 'b-', label='v = 1 м/с (v1)')
    plt.xlabel('Время, с')
    plt.ylabel('Температура К')
    plt.title('Сравнение температур в центре покрытия')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(os.path.join(output_dir, 'compare_time.png'), dpi=150)
    plt.close()

    # График 2: Разница температур (Heatmap разности)
    plt.figure(figsize=(10, 6))
    diff = A_1 - A_001
    plt.imshow(diff, aspect='auto', extent=[t_array[0], t_array[-1], l_grid[0], l_grid[-1]], origin='lower', cmap='RdBu_r')
    plt.colorbar(label='Разница температур (v1 - v001), К')
    plt.title('Карта разности температурных полей')
    plt.savefig(os.path.join(output_dir, 'compare_diff_map.png'), dpi=150)
    plt.close()
    
    print(f"SUCCESS: Сравнение сохранено в {output_dir}")

if __name__ == "__main__":
    compare_results()