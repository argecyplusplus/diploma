import os
import subprocess
import sys
import shutil
import threading
import re
from flask import Flask, render_template, request, jsonify, send_from_directory


app = Flask(__name__)

GEN_DIR_NAME = 'generated'
FF_PATH = r"C:\Program Files (x86)\FreeFem++\FreeFem++.exe"

progress_tracker = {
    'geometry': {'status': 'waiting', 'label': 'Запуск геометрии (Python)'},
    'edp_prep': {'status': 'waiting', 'label': 'Подготовка .EDP файла'},
    'simulation': {'status': 'waiting', 'label': 'Моделирование FreeFem++', 'details': ''},
    'processing': {'status': 'waiting', 'label': 'Аппроксимация (Gauss Fit)'},
    'thermal': {'status': 'waiting', 'label': 'Расчет теплового слоя (Python)', 'details': ''},
    'complete': False,
    'error': None
}

DEFAULTS = {
    'chord': 1.0, 'chord2': 0.5, 'dely_offset': 0.0,
    't_gas': 673.0, 't_cool': 1223.0, 't_blade': 1223.0,
    'press0': 1500000.0, 'u0': 1.0, 'beta': -10.0,
    'houter': 15000.0, 'hinner': 15.0,
    'rgas': 287.0, 'cpgas': 1005.0, 'kgas': 0.026,
    'rhosteel': 7800.0, 'cpsteel': 500.0, 'ksteel': 25.0
}

def run_calculation(params, base_dir, gen_dir, fast_mode=False):
    global progress_tracker
    # Сброс статусов
    for key in ['geometry', 'edp_prep', 'simulation', 'processing', 'thermal']:
        progress_tracker[key]['status'] = 'waiting'
        if 'details' in progress_tracker[key]: progress_tracker[key]['details'] = ''
    progress_tracker['complete'] = False
    progress_tracker['error'] = None

    try:
        if not fast_mode:
            # --- ШАГ 1: ГЕОМЕТРИЯ ---
            progress_tracker['geometry']['status'] = 'running'
            subprocess.run([sys.executable, 'geometry_app.py'], capture_output=True, text=True, encoding='cp1251')
            
            source_csv = os.path.join(base_dir, 'out_L.csv')
            target_csv = os.path.join(gen_dir, 'out_L.csv')
            if os.path.exists(source_csv):
                shutil.move(source_csv, target_csv)
                progress_tracker['geometry']['status'] = 'done'
            else: raise Exception("out_L.csv не создан")

            # --- ШАГ 2: EDP ---
            progress_tracker['edp_prep']['status'] = 'running'
            with open('template.edp', 'r', encoding='utf-8') as f:
                content = f.read()
            for key, value in params.items():
                pattern = re.compile(r'\{\{\s*' + re.escape(key) + r'\s*\}\}', re.IGNORECASE)
                content = pattern.sub(str(value), content)
            
            with open(os.path.join(gen_dir, 'AeroTherm_gen.edp'), 'w', encoding='utf-8') as f:
                f.write(content)
            progress_tracker['edp_prep']['status'] = 'done'

            # --- ШАГ 3: FREEFEM (Самый долгий этап) ---
            progress_tracker['simulation']['status'] = 'running'
            process = subprocess.Popen(
                [FF_PATH, 'AeroTherm_gen.edp', '-nw'],
                cwd=gen_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='cp1251', errors='replace', bufsize=1 
            )
            for line in process.stdout:
                match = re.search(r"^PROG:\s*(.*)", line.strip())
                if match: progress_tracker['simulation']['details'] = match.group(1)
            process.wait()
            progress_tracker['simulation']['status'] = 'done'
        else:
            # Если быстрый режим — помечаем предыдущие шаги как "пропущенные" или "готовые"
            progress_tracker['geometry']['status'] = 'done'
            progress_tracker['edp_prep']['status'] = 'done'
            progress_tracker['simulation']['status'] = 'done'
            progress_tracker['simulation']['details'] = "Использованы готовые данные FreeFem++"

        # --- ШАГ 4: ПОДГОТОВКА ГАУССА ---
        progress_tracker['processing']['status'] = 'running'
        # В вашем случае файл статичен или уже должен быть в gen_dir / scripts
        progress_tracker['processing']['status'] = 'done'

        # --- ШАГ 5: ТЕПЛОВОЙ РАСЧЕТ И ГРАФИКИ (ПОСЛЕДОВАТЕЛЬНО v_001 и v_1) ---
        progress_tracker['thermal']['status'] = 'running'
        
        versions = [
            {'name': 'v001', 'calc': 'thermal_simulation_from_Gaussfile_v001.py'},
            {'name': 'v1',   'calc': 'thermal_simulation_from_Gaussfile_v1.py'}
        ]

        for ver in versions:
            v_clean = ver['name'] # 'v001' или 'v1'
            
            progress_tracker['thermal']['details'] = f"Запуск расчета {v_clean}..."
            print(f"--- Processing {v_clean} ---")
            
            # Путь к универсальному скрипту расчета (лежит в /scripts/)
            calc_path = os.path.join(base_dir, 'scripts', 'thermal_solver.py')
            
            # 1. Запуск РАСЧЕТА с передачей аргумента --ver
            # Скрипт сам поймет, какой gauss_params.csv взять и куда сохранить результат
            calc_res = subprocess.run(
                [sys.executable, calc_path, "--ver", v_clean],
                cwd=gen_dir, 
                capture_output=True, 
                text=True, 
                encoding='cp1251', 
                errors='replace'
            )
            
            if calc_res.returncode != 0:
                print(f"Stdout: {calc_res.stdout}")
                print(f"Stderr: {calc_res.stderr}")
                raise Exception(f"Ошибка в расчете {v_clean}: {calc_res.stderr}")

            # 2. Запуск УНИВЕРСАЛЬНЫХ ГРАФИКОВ
            # Если plot_npz.py тоже общий и лежит в /scripts/
            plot_path = os.path.join(base_dir, 'scripts', 'plot_npz.py') 
            
            plot_res = subprocess.run(
                [sys.executable, plot_path, "--ver", v_clean],
                cwd=gen_dir, 
                capture_output=True, 
                text=True, 
                encoding='cp1251', 
                errors='replace'
            )

            if plot_res.returncode != 0:
                print(f"ERR in {v_clean} plots: {plot_res.stderr}")
                raise Exception(f"Ошибка в графиках {v_clean}: {plot_res.stderr}")

            print(f"--- {v_clean} успешно завершен ---")

        progress_tracker['thermal']['details'] = "Все версии рассчитаны"
        progress_tracker['thermal']['status'] = 'done'
        progress_tracker['complete'] = True
        
        # --- ШАГ 6: СРАВНЕНИЕ ВЕРСИЙ ---
        progress_tracker['thermal']['details'] = "Финальное сравнение v001 и v1..."
        compare_script = os.path.join(base_dir, 'scripts', 'compare_v', 'compare_velocities.py')
        
        comp_res = subprocess.run(
            [sys.executable, compare_script],
            cwd=gen_dir, capture_output=True, text=True, encoding='cp1251', errors='replace'
        )
        
        if comp_res.returncode != 0:
            print("ERR in comparison:", comp_res.stderr)
            # Не кидаем Exception, чтобы хотя бы основные графики показались
        
        progress_tracker['thermal']['details'] = "Все расчеты и сравнения завершены"
        progress_tracker['thermal']['status'] = 'done'
        progress_tracker['complete'] = True



    except Exception as e:
        progress_tracker['error'] = str(e)

# Роуты (index, progress, result) без изменений

@app.route('/', methods=['GET', 'POST'])
def index():
    base_dir = os.getcwd()
    gen_dir = os.path.join(base_dir, GEN_DIR_NAME)
    
    if request.method == 'POST':
        params = {key: request.form.get(key, default=DEFAULTS[key], type=float) for key in DEFAULTS}
        # Проверяем, какая кнопка была нажата
        fast_mode = 'fast_calc' in request.form 
        
        if not os.path.exists(gen_dir): os.makedirs(gen_dir)
        
        threading.Thread(target=run_calculation, args=(params, base_dir, gen_dir, fast_mode)).start()
        return render_template('waiting.html')
    
    # --- ЛОГИКА ВЫВОДА ПОСЛЕДНИХ РЕЗУЛЬТАТОВ (в корне) ---
    last_results = None
    res_full_path = os.path.join(base_dir, 'results', 'v001') # Ищем в корне!

    if os.path.exists(res_full_path):
        images = [f for f in os.listdir(res_full_path) if f.endswith('.png')]
        data_file = 'stable_results_from_gauss_v001.npz'

        if images and os.path.exists(os.path.join(res_full_path, data_file)):
            mtime = os.path.getmtime(os.path.join(res_full_path, data_file))
            import datetime
            last_results = {
                'time': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                # Путь для url_for или прямой ссылки
                'images': [os.path.join('v001', img).replace('\\', '/') for img in images]
            }

    return render_template('index.html', defaults=DEFAULTS, last_results=last_results)

# Добавляем специальный роут для раздачи файлов из папки generated
@app.route('/generated/<path:filename>')
def custom_static(filename):
    return send_from_directory(os.path.join(os.getcwd(), 'generated'), filename)

@app.route('/results_files/<path:filename>')
def serve_results(filename):
    # Находим папку results строго в корне, где лежит app.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    results_root = os.path.join(current_dir, 'results')
    return send_from_directory(results_root, filename)


@app.route('/progress')
def get_progress():
    return jsonify(progress_tracker)

@app.route('/result')
def result():
    # Читаем лог, если нужно вывести его на финальной странице
    # Для упрощения пока просто возвращаем шаблон
    return render_template('result.html')

if __name__ == '__main__':
    app.run(debug=True)