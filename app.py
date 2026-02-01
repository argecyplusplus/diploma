from flask import Flask, jsonify
from flask_cors import CORS
import importlib
from pathlib import Path
import sys

from core.database import db
from config import Config

def create_app(config_class=Config) -> Flask:
    """Фабрика приложений Flask 3.0"""
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Включаем CORS (Flask-CORS 4.0)
    CORS(app)
    
    # Инициализация базы данных
    db.init_app(app)
    
    # Создаем таблицы (SQLAlchemy 2.0)
    with app.app_context():
        db.create_all()
        print("✅ База данных инициализирована")
    
    # Загружаем модули
    load_modules(app)
    
    # Роуты
    @app.get("/")
    def index():
        """Главная страница"""
        from core.registry import registry
        return jsonify({
            "app": "Модульная система Flask 3.0",
            "status": "running",
            "services": registry.list_services(),
            "health": registry.health_check()
        })
    
    @app.get("/health")
    def health():
        """Health check endpoint"""
        from core.registry import registry
        return jsonify(registry.health_check())
    
    @app.get("/modules")
    def list_modules():
        """Список всех модулей"""
        modules_path = Path(app.config["MODULES_PATH"])
        modules = []
        
        if modules_path.exists():
            for item in modules_path.iterdir():
                if item.is_dir() and not item.name.startswith("_"):
                    modules.append(item.name)
        
        return jsonify({
            "modules": modules,
            "enabled": app.config["MODULES"]
        })
    
    return app

def load_modules(app):
    """Загрузка модулей динамически"""
    print("\n" + "="*50)
    print("🔄 ЗАГРУЗКА МОДУЛЕЙ")
    print("="*50)
    
    modules_loaded = []
    modules_path = app.config["MODULES_PATH"]
    
    # Добавляем путь к модулям в sys.path если его нет
    if str(modules_path.parent) not in sys.path:
        sys.path.insert(0, str(modules_path.parent))
    
    for module_name in app.config["MODULES"]:
        try:
            # Импортируем модуль
            module = importlib.import_module(f"modules.{module_name}")
            
            # Инициализируем модуль
            if hasattr(module, "init_module"):
                service = module.init_module(app)
                modules_loaded.append({
                    "name": module_name,
                    "status": "loaded",
                    "service": service.__class__.__name__ if service else None
                })
                print(f"✅ Модуль '{module_name}' загружен")
            else:
                print(f"⚠️  Модуль '{module_name}' не имеет init_module")
                modules_loaded.append({
                    "name": module_name,
                    "status": "error",
                    "error": "No init_module function"
                })
                
        except ImportError as e:
            print(f"❌ Ошибка импорта '{module_name}': {e}")
            modules_loaded.append({
                "name": module_name,
                "status": "error",
                "error": str(e)
            })
        except Exception as e:
            print(f"❌ Ошибка загрузки '{module_name}': {e}")
            modules_loaded.append({
                "name": module_name,
                "status": "error",
                "error": str(e)
            })
    
    print(f"\n📊 Загружено: {len([m for m in modules_loaded if m['status'] == 'loaded'])}/{len(app.config['MODULES'])}")
    print("="*50 + "\n")
    
    app.extensions["loaded_modules"] = modules_loaded
    
    return modules_loaded

if __name__ == "__main__":
    app = create_app()
    app.run(debug=app.config["DEBUG"], port=5000)