import numpy as np
from numpy.linalg import inv
import os
import sys

# --- МАТЕМАТИЧЕСКИЙ БЛОК (БЕЗ ИЗМЕНЕНИЙ) ---
def Lezh(x):
    y = np.zeros((10, len(x)))
    y[0,:] = 1
    y[1,:] = x
    y[2,:] = (3*x**2-1)/2
    y[3,:] = (5*x**3-3*x)/2
    y[4,:] = (35*x**4-30*x**2+3)/8
    y[5,:] = (63*x**5-70*x**3+15*x)/8
    y[6,:] = 231/16*x**6-315/16*x**4+105/16*x**2-5/16
    y[7,:] = 429/16*x**7-693/16*x**5+315/16*x**3-35/16*x
    y[8,:] = 6435/128*x**8-3003/32*x**6+3465/64*x**4-315/32*x**2+35/128
    y[9,:] = 12155/128*x**9-6435/32*x**7+9009/64*x**5-1155/32*x**3+315/128*x
    return y

def calc_L(x, y_exp):
    X = Lezh(x)
    L = np.dot(inv(np.dot(X, np.transpose(X))), np.dot(X, y_exp))
    return L

# --- БЛОК ОБРАБОТКИ ФАЙЛОВ ---
def run_processing():
    # Определяем пути относительно этого файла
    wdir = os.path.dirname(os.path.abspath(__file__))
    todir = os.path.join(wdir, 'input_files')
    output_file = os.path.join(wdir, 'out_L.csv')
    
    # Создаем папки, которые требует твой старый код (на всякий случай)
    for folder in ['out_files', 'tmp']:
        folder_path = os.path.join(wdir, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

    if not os.path.exists(todir):
        print(f"Ошибка: Папка {todir} не существует.")
        return

    files_lst = os.listdir(todir)
    file_links = []
    
    # Ищем уникальные префиксы профилей
    for fl in files_lst:
        if fl.endswith('_up.csv'):
            prefix = fl.replace('_up.csv', '')
            if prefix not in file_links:
                file_links.append(prefix)
    
    file_links.sort() # Сортируем: prof_1, prof_2
    
    # Очищаем выходной файл
    with open(output_file, 'w') as f:
        f.write("")

    if not file_links:
        print("Ошибка: В input_files не найдено парных файлов _up.csv")
        return

    for link in file_links:
        print(f"Обработка: {link}")
        try:
            y_upex = np.loadtxt(os.path.join(todir, link + "_up.csv"))
            y_lwex = np.loadtxt(os.path.join(todir, link + "_lw.csv"))
            
            # Твой алгоритм нормализации
            y_upex[:,1] = np.max(y_lwex[:,1]) - y_upex[:,1]
            y_lwex[:,1] = np.max(y_lwex[:,1]) - y_lwex[:,1]
            delta_x = np.min([y_upex[0,0], y_lwex[0,0]])
            y_upex[:,0] -= delta_x
            y_lwex[:,0] -= delta_x
            
            if (y_lwex[-1,0] - y_lwex[np.argmin(y_lwex[:,1]), 0]) != 0:
                phi = -np.arctan((y_lwex[-1,1] - np.min(y_lwex[:,1])) / 
                                 (y_lwex[-1,0] - y_lwex[np.argmin(y_lwex[:,1]), 0]))
            else: phi = 0 
            
            R = np.array([[np.cos(phi), -np.sin(phi)], [np.sin(phi), np.cos(phi)]])
            shift_x, shift_y = y_lwex[np.argmin(y_lwex[:,1]), 0], np.min(y_lwex[:,1])
            
            # Поворот и смещение
            for pts in [y_upex, y_lwex]:
                xr, yr = pts[:,0] - shift_x, pts[:,1] - shift_y
                pts[:,0] = R[0,0]*xr + R[0,1]*yr + shift_x
                pts[:,1] = R[1,0]*xr + R[1,1]*yr + shift_y

            min_x = np.min([np.min(y_upex[:,0]), np.min(y_lwex[:,0])])
            y_upex[:,0] -= min_x
            y_lwex[:,0] -= min_x
            
            chord = np.max([y_upex[-1,0]-y_upex[0,0], y_lwex[-1,0]-y_lwex[0,0]])
            y_upex /= chord
            y_lwex /= chord

            # Расчет и запись
            Lup = calc_L(y_upex[:,0], y_upex[:,1])
            Llw = calc_L(y_lwex[:,0], y_lwex[:,1])

            with open(output_file, 'a') as f:
                f.write(" ".join(map(str, Lup)) + "\n")
                f.write(" ".join(map(str, Llw)) + "\n")
                
        except Exception as e:
            print(f"Ошибка в профиле {link}: {e}")

if __name__ == "__main__":
    run_processing()