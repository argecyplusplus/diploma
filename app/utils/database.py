import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from flask import g
from ..models.base import Base

# Важно: импортируем все модели, чтобы Base.metadata знал о них
from ..models import blade, material, simulation

CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'db_config.json')
DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'databases')


def _load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config({"current_db": None, "databases": []})
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def get_db_list():
    config = _load_config()
    # Фильтруем только существующие файлы
    valid_dbs = [db for db in config["databases"] if os.path.exists(os.path.join(DB_DIR, db))]
    if len(valid_dbs) != len(config["databases"]):
        config["databases"] = valid_dbs
        save_config(config)
    return valid_dbs, config["current_db"]


def create_database(name):
    if not name.endswith('.db'):
        name += '.db'
    config = _load_config()
    if name in config["databases"]:
        raise ValueError("База данных уже существует")

    os.makedirs(DB_DIR, exist_ok=True)
    db_path = os.path.join(DB_DIR, name)

    # Создаем файл и инициализируем таблицы через SQLAlchemy
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    config["databases"].append(name)
    config["current_db"] = name
    save_config(config)
    return name


def select_database(name):
    config = _load_config()
    if name not in config["databases"]:
        raise ValueError("База данных не найдена")
    config["current_db"] = name
    save_config(config)
    return name


def delete_database(name):
    config = _load_config()
    if name not in config["databases"]:
        raise ValueError("База данных не найдена")

    db_path = os.path.join(DB_DIR, name)
    if os.path.exists(db_path):
        os.remove(db_path)

    config["databases"].remove(name)
    if config["current_db"] == name:
        config["current_db"] = None
    save_config(config)


def get_engine():
    config = _load_config()
    if not config["current_db"]:
        raise RuntimeError("DB_NOT_SELECTED")
    db_path = os.path.join(DB_DIR, config["current_db"])
    if not os.path.exists(db_path):
        raise RuntimeError("DB_FILE_MISSING")
    return create_engine(f"sqlite:///{db_path}", echo=False)


def get_db_session():
    if 'db_session' not in g:
        engine = get_engine()
        session_factory = sessionmaker(bind=engine)
        g.db_session = scoped_session(session_factory)
    return g.db_session