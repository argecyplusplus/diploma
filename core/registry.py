from typing import Any

class ServiceError(Exception):
    """Базовое исключение для сервисов"""
    pass

class ServiceNotFoundError(ServiceError):
    """Сервис не найден"""
    pass

class ServiceRegistry:
    """Реестр сервисов с поддержкой зависимостей"""
    
    _instance = None
    _services: dict[str, Any] = {}
    _dependencies: dict[str, list[str]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, service: Any, dependencies: list[str] | None = None):
        """Регистрация сервиса с опциональными зависимостями"""
        print(f"📦 Регистрируем сервис: {name}")
        self._services[name] = service
        
        if dependencies:
            self._dependencies[name] = dependencies
    
    def get(self, name: str) -> Any:
        """Получение сервиса по имени"""
        match self._services.get(name):
            case service if service is not None:
                return service
            case None:
                # Проверяем, есть ли зависимости
                if name in self._dependencies:
                    missing = [dep for dep in self._dependencies[name] 
                              if dep not in self._services]
                    if missing:
                        raise ServiceNotFoundError(
                            f"Сервис '{name}' требует: {', '.join(missing)}"
                        )
                raise ServiceNotFoundError(f"Сервис '{name}' не найден")
    
    def list_services(self) -> list[str]:
        """Список всех зарегистрированных сервисов"""
        return list(self._services.keys())
    
    def get_with_dependencies(self, name: str) -> dict[str, Any]:
        """Получение сервиса и его зависимостей"""
        service = self.get(name)
        result = {name: service}
        
        if name in self._dependencies:
            for dep in self._dependencies[name]:
                result[dep] = self.get(dep)
        
        return result
    
    def health_check(self) -> dict[str, dict]:
        """Проверка здоровья всех сервисов"""
        health = {}
        for name, service in self._services.items():
            try:
                if hasattr(service, 'health_check'):
                    health[name] = service.health_check()
                else:
                    health[name] = {"status": "unknown"}
            except Exception as e:
                health[name] = {"status": "error", "error": str(e)}
        return health

# Глобальный экземпляр
registry = ServiceRegistry()