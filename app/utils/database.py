import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from flask import g
from ..models.base import Base

# Импорт моделей для создания таблиц
from ..models import blade, material, simulation

DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'databases')
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'db_config.json')


def _load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"current_db": None}, f)
        return {"current_db": None}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def _save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def get_db_list():
    """Сканирует папку databases и возвращает список БД (без .db) и текущую активную"""
    os.makedirs(DB_DIR, exist_ok=True)
    dbs = []
    for f in os.listdir(DB_DIR):
        if f.endswith('.db'):
            dbs.append(f[:-3])  # удаляем расширение

    config = _load_config()
    current = config.get("current_db")
    # Проверяем, существует ли файл текущей БД
    if current and not os.path.exists(os.path.join(DB_DIR, current + '.db')):
        current = None
        config["current_db"] = None
        _save_config(config)

    return dbs, current


def get_current_db():
    _, current = get_db_list()
    return current


def create_database(name):
    """Создаёт новый файл .db и возвращает имя без расширения"""
    if not name.endswith('.db'):
        name += '.db'
    os.makedirs(DB_DIR, exist_ok=True)
    db_path = os.path.join(DB_DIR, name)
    if os.path.exists(db_path):
        raise ValueError("База данных уже существует")

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return name[:-3]  # возвращаем имя без .db


def select_database(name):
    """Устанавливает активную БД (имя без .db)"""
    db_path = os.path.join(DB_DIR, name + '.db')
    if not os.path.exists(db_path):
        raise ValueError("База данных не найдена")
    config = _load_config()
    config["current_db"] = name
    _save_config(config)
    return name


def delete_database(name):
    """Удаляет файл БД и, если она была активной, сбрасывает current_db"""
    db_path = os.path.join(DB_DIR, name + '.db')
    if not os.path.exists(db_path):
        raise ValueError("База данных не найдена")
    os.remove(db_path)

    config = _load_config()
    if config.get("current_db") == name:
        config["current_db"] = None
        _save_config(config)


def get_engine():
    """Возвращает SQLAlchemy engine для активной БД"""
    config = _load_config()
    current = config.get("current_db")
    if not current:
        raise RuntimeError("DB_NOT_SELECTED")
    db_path = os.path.join(DB_DIR, current + '.db')
    if not os.path.exists(db_path):
        raise RuntimeError("DB_FILE_MISSING")
    return create_engine(f"sqlite:///{db_path}", echo=False)


def get_db_session():
    """Возвращает сессию SQLAlchemy для текущего запроса (через Flask g)"""
    if 'db_session' not in g:
        engine = get_engine()
        session_factory = sessionmaker(bind=engine)
        g.db_session = scoped_session(session_factory)
    return g.db_session