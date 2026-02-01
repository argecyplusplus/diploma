from pathlib import Path

BASE_DIR = Path(__file__).parent

class Config:
    # Основные настройки Flask 3.0
    SECRET_KEY = "dev-secret-key-change-in-production"
    
    # Flask 3.0 имеет улучшенную систему конфигурации
    DEBUG = True
    PROPAGATE_EXCEPTIONS = True
    
    # База данных
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{BASE_DIR / 'app.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # SQLAlchemy 2.0 параметры
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    
    # Настройки модулей
    MODULES = ["data_fetcher", "data_processor"]
    MODULES_PATH = BASE_DIR / "modules"