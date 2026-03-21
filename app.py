import os
import subprocess
import sys
import shutil
import threading
from flask import Flask, render_template, request, jsonify
import re

app = Flask(__name__)

FF_PATH = r"C:\Program Files (x86)\FreeFem++\FreeFem++.exe"

# Глобальное хранилище статуса
progress_tracker = {
    'geometry': {'status': 'waiting', 'label': 'Запуск геометрии (Python)'},
    'edp_prep': {'status': 'waiting', 'label': 'Подготовка .EDP файла'},
    'simulation': {'status': 'waiting', 'label': 'Моделирование FreeFem++', 'details': ''},
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

def run_calculation(params, base_dir, gen_dir):
    global progress_tracker
    # Сброс статусов
    for key in ['geometry', 'edp_prep', 'simulation']:
        progress_tracker[key]['status'] = 'waiting'
        if 'details' in progress_tracker[key]: progress_tracker[key]['details'] = ''
    progress_tracker['complete'] = False
    progress_tracker['error'] = None

    try:
        # --- ШАГ 1: ГЕОМЕТРИЯ ---
        progress_tracker['geometry']['status'] = 'running'
        res = subprocess.run([sys.executable, 'geometry_app.py'], capture_output=True, text=True, encoding='cp1251')
        
        source_csv = os.path.join(base_dir, 'out_L.csv')
        target_csv = os.path.join(gen_dir, 'out_L.csv')
        if os.path.exists(source_csv):
            if os.path.exists(target_csv): os.remove(target_csv)
            shutil.move(source_csv, target_csv)
            progress_tracker['geometry']['status'] = 'done'
        else:
            raise Exception("out_L.csv не создан")

        # --- ШАГ 2: EDP ---
        progress_tracker['edp_prep']['status'] = 'running'
        with open('template.edp', 'r', encoding='utf-8') as f:
            content = f.read()
        for key, value in params.items():
            content = content.replace(f"{{{{ {key} }}}}", str(value))
            content = content.replace(f"{{{{{key}}}}}", str(value))
        
        with open(os.path.join(gen_dir, 'AeroTherm_gen.edp'), 'w', encoding='utf-8') as f:
            f.write(content)
        progress_tracker['edp_prep']['status'] = 'done'

        # --- ШАГ 3: FREEFEM ---
        progress_tracker['simulation']['status'] = 'running'
        
        process = subprocess.Popen(
            [FF_PATH, 'AeroTherm_gen.edp', '-nw'],
            cwd=gen_dir, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True, 
            encoding='cp1251', 
            errors='replace',
            bufsize=1 
        )

        # Устанавливаем начальную заглушку вручную, чтобы не висел пустой экран или код
        # Начальная заглушка
        progress_tracker['simulation']['details'] = "Подготовка математической модели..."

        for line in process.stdout:
            clean_line = line.strip()
            if not clean_line:
                continue

            # Печатаем в консоль (черное окно) всё как есть
            print(f"FF++: {clean_line}")

            # Ищем строгое соответствие: строка должна начинаться с PROG:
            # ^ - начало строки, далее PROG: и любой текст
            match = re.search(r"^PROG:\s*(.*)", clean_line)
            
            if match:
                # Берем только то, что идет ПОСЛЕ PROG:
                progress_tracker['simulation']['details'] = match.group(1)
            
            # Ловим ошибки (но только если это не эхо строки с cout)
            elif "error" in clean_line.lower() and "cout" not in clean_line:
                if "load" not in clean_line.lower():
                    progress_tracker['error'] = f"Ошибка: {clean_line}"

        process.wait()

        if progress_tracker['error'] is None:
            progress_tracker['simulation']['status'] = 'done'
            progress_tracker['complete'] = True  # <--- ВОТ ЭТА СТРОЧКА

    except Exception as e:
        progress_tracker['error'] = str(e)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        params = {key: request.form.get(key, default=DEFAULTS[key], type=float) for key in DEFAULTS}
        base_dir = os.getcwd()
        gen_dir = os.path.join(base_dir, 'generated')
        if not os.path.exists(gen_dir): os.makedirs(gen_dir)
        
        # Запускаем поток
        threading.Thread(target=run_calculation, args=(params, base_dir, gen_dir)).start()
        return render_template('waiting.html')
    
    return render_template('index.html', defaults=DEFAULTS)

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