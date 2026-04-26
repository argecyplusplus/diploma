# app/__init__.py
import os
from flask import Flask, redirect, url_for, request, jsonify, g
from .controllers.settings_api import settings_api_bp
from .controllers.main_views import main_bp
from .utils.database import get_db_list


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

    # Регистрация Blueprints
    app.register_blueprint(settings_api_bp, url_prefix='/api/settings')
    app.register_blueprint(main_bp)

    # Middleware: проверка выбора БД
    @app.before_request
    def check_db_selected():
        # Разрешаем доступ к API настроек, статике и странице выбора БД
        allowed_paths = ['/api/settings', '/static', '/select-db']
        if any(request.path.startswith(p) for p in allowed_paths):
            return

        dbs, current = get_db_list()
        if not current:
            # Если API запрос -> возвращаем ошибку, если страница -> редирект
            if request.path.startswith('/api/'):
                return jsonify({"error": "DB_NOT_SELECTED"}), 403
            return redirect(url_for('main.select_db_page'))

    # Очистка сессии SQLAlchemy после запроса
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session = g.pop('db_session', None)
        if db_session is not None:
            db_session.remove()

    return app