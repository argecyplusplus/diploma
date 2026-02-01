from app import create_app

app = create_app()

if __name__ == "__main__":
    print("🚀 Запуск модульной системы на Flask 3.0")
    print("📁 Структура: модульная архитектура с общей БД")
    print("🔗 API: RESTful endpoints для каждого модуля")
    print("👉 Главная страница: http://localhost:5000")
    print("👉 Health check: http://localhost:5000/health")
    print("👉 Список модулей: http://localhost:5000/modules")
    print("\n" + "="*50)
    
    app.run(
        debug=app.config["DEBUG"],
        host="0.0.0.0",
        port=5000,
        use_reloader=True
    )