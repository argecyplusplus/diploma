import os
import subprocess
import sys
import shutil
from flask import Flask, render_template, request

app = Flask(__name__)

# Путь к исполняемому файлу FreeFem++
FF_PATH = r"C:\Program Files (x86)\FreeFem++\FreeFem++.exe"

# Значения по умолчанию (ключи в точности как в вашем template.edp)
DEFAULTS = {
    'chord': 1.0, 
    'chord2': 0.5, 
    'dely_offset': 0.0,
    't_gas': 673.0, 
    't_cool': 1223.0, 
    't_blade': 1223.0,
    'press0': 1500000.0, 
    'u0': 1.0, 
    'beta': -10.0,
    'houter': 15000.0, 
    'hinner': 15.0,
    'rgas': 287.0, 
    'cpgas': 1005.0, 
    'kgas': 0.026,
    'rhosteel': 7800.0, 
    'cpsteel': 500.0, 
    'ksteel': 25.0
}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Создаем необходимые папки
        base_dir = os.getcwd()
        gen_dir = os.path.join(base_dir, 'generated')
        plots_dir = os.path.join(gen_dir, 'plots')
        
        for folder in [gen_dir, plots_dir]:
            if not os.path.exists(folder):
                os.makedirs(folder)

        # --- ШАГ 1: ЗАПУСК ГЕОМЕТРИИ (Python) ---
        try:
            print("--- ЗАПУСК ГЕОМЕТРИИ ---")
            result = subprocess.run(
                [sys.executable, 'geometry_app.py'], 
                capture_output=True, 
                text=True,
                encoding='cp1251', 
                errors='replace'
            )
            
            if result.stdout: print("STDOUT геометрии:", result.stdout)
            
            if result.returncode != 0:
                print("ОШИБКА ГЕОМЕТРИИ:", result.stderr)
                return f"Скрипт геометрии упал! Ошибка: <pre>{result.stderr}</pre>"

            # Перемещаем out_L.csv в папку к FreeFem
            source_csv = os.path.join(base_dir, 'out_L.csv')
            target_csv = os.path.join(gen_dir, 'out_L.csv')
            
            if os.path.exists(source_csv):
                if os.path.exists(target_csv): os.remove(target_csv)
                shutil.move(source_csv, target_csv)
                print("Файл out_L.csv успешно подготовлен.")
            else:
                return f"Ошибка: out_L.csv не был создан скриптом геометрии."

        except Exception as e:
            return f"Критическая ошибка Python: {e}"

        # --- ШАГ 2: ПОДГОТОВКА .EDP ФАЙЛА ---
        params = {key: request.form.get(key, default=DEFAULTS[key], type=float) for key in DEFAULTS}
        
        try:
            with open('template.edp', 'r', encoding='utf-8') as f:
                content = f.read()

            for key, value in params.items():
                content = content.replace(f"{{{{ {key} }}}}", str(value))
                content = content.replace(f"{{{{{key}}}}}", str(value))

            edp_path = os.path.join(gen_dir, 'AeroTherm_gen.edp')
            with open(edp_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            return f"Ошибка при подготовке файла шаблона: {e}"

        # --- ШАГ 3: ЗАПУСК FREEFEM++ С ВЫВОДОМ В РЕАЛЬНОМ ВРЕМЕНИ ---
        try:
            print("--- ЗАПУСК FREEFEM++ (Расчет пошел...) ---")
            
            # Используем Popen для чтения вывода в реальном времени
            process = subprocess.Popen(
                [FF_PATH, 'AeroTherm_gen.edp', '-nw'],
                cwd=gen_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='cp1251', # Для русской Windows
                errors='replace'
            )

            full_output = []
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    clean_line = line.strip()
                    full_output.append(clean_line)
                    # Выводим важные этапы в консоль сервера
                    if "it =" in clean_line or "t=" in clean_line:
                        print(f"ПРОГРЕСС: {clean_line}")
                    elif "error" in clean_line.lower():
                        print(f"!!! ОШИБКА В FF++: {clean_line}")
                    else:
                        print(clean_line)

            final_output = "\n".join(full_output)
            return render_template('result.html', output=final_output)
        
        except Exception as e:
            return f"Ошибка при запуске FreeFEM++: {e}"

    return render_template('index.html', defaults=DEFAULTS)

if __name__ == '__main__':
    # Гарантируем наличие папки при старте
    if not os.path.exists('generated'):
        os.makedirs('generated')
    app.run(debug=True)