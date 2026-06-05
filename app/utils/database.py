import os
import json
import logging
import time
import gc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from flask import g
from ..models.base import Base

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'databases')
CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'db_config.json')

_engine_cache = None

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
            dbs.append(f[:-3])

    config = _load_config()
    current = config.get("current_db")
    if current and not os.path.exists(os.path.join(DB_DIR, current + '.db')):
        current = None
        config["current_db"] = None
        _save_config(config)

    return dbs, current


def get_current_db():
    _, current = get_db_list()
    return current


def close_all_connections(db_name=None):
    """
    Закрывает все соединения к БД.
    Если указан db_name и он совпадает с текущей активной БД, сбрасывает активную.
    """
    global _engine_cache
    config = _load_config()
    current = config.get("current_db")
    if db_name and current == db_name:
        config["current_db"] = None
        _save_config(config)

    try:
        if 'db_session' in g:
            g.db_session.close()
            g.db_session.remove()
            delattr(g, 'db_session')
    except Exception as e:
        logger.debug(f"Ошибка при закрытии сессии Flask: {e}")

    if _engine_cache:
        try:
            _engine_cache.dispose()
        except Exception as e:
            logger.debug(f"Ошибка при dispose движка: {e}")
        _engine_cache = None

    gc.collect()
    time.sleep(0.1)


def create_database(name):
    """Создаёт новый файл .db и инициализирует его данными"""
    if not name.endswith('.db'):
        name += '.db'
    os.makedirs(DB_DIR, exist_ok=True)
    db_path = os.path.join(DB_DIR, name)
    if os.path.exists(db_path):
        raise ValueError("База данных уже существует")

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    from .init_db_data import init_database
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        init_database(session)
        session.commit()
        logger.info(f"База данных {name} создана и инициализирована")
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка инициализации БД: {e}")
        raise e
    finally:
        session.close()
        engine.dispose()  

    return name[:-3]


def select_database(name):
    """Устанавливает активную БД (БЕЗ автоматической инициализации)"""
    db_path = os.path.join(DB_DIR, name + '.db')
    if not os.path.exists(db_path):
        raise ValueError("База данных не найдена")

    close_all_connections()

    config = _load_config()
    config["current_db"] = name
    _save_config(config)

    logger.info(f"Выбрана база данных: {name}")
    return name


def delete_database(name):
    db_path = os.path.join(DB_DIR, name + '.db')
    if not os.path.exists(db_path):
        raise ValueError("База данных не найдена")

    close_all_connections(name)
    for _ in range(3):
        try:
            os.remove(db_path)
            break
        except PermissionError:
            time.sleep(0.5)
    else:
        raise RuntimeError(f"Не удалось удалить файл БД {db_path}")

    sim_dir = os.path.join(os.getcwd(), 'uploads', 'simulations', name)
    if os.path.exists(sim_dir):
        import shutil
        shutil.rmtree(sim_dir)
        logger.info(f"Удалена папка симуляций БД: {sim_dir}")

    config = _load_config()
    if config.get("current_db") == name:
        config["current_db"] = None
        _save_config(config)
    logger.info(f"База данных {name} полностью удалена")


def get_engine():
    """Возвращает SQLAlchemy engine для активной БД (с кешированием)"""
    global _engine_cache
    config = _load_config()
    current = config.get("current_db")
    if not current:
        raise RuntimeError("DB_NOT_SELECTED")
    db_path = os.path.join(DB_DIR, current + '.db')
    if not os.path.exists(db_path):
        raise RuntimeError("DB_FILE_MISSING")

    if _engine_cache is None:
        _engine_cache = create_engine(f"sqlite:///{db_path}", echo=False)
    return _engine_cache


def get_db_session():
    """Возвращает сессию SQLAlchemy для текущего запроса (через Flask g)"""
    if 'db_session' not in g:
        engine = get_engine()
        session_factory = sessionmaker(bind=engine)
        g.db_session = scoped_session(session_factory)
    return g.db_session