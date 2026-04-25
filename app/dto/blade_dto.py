from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


# --------------------------------------------------------------------------
# 1. DTO для Лопаток (Blades)
# --------------------------------------------------------------------------

class BladeCreateRequest(BaseModel):
    """DTO для создания новой лопатки (входящие данные)"""
    name: str = Field(..., min_length=1, max_length=100, description="Название лопатки")


class BladeResponse(BaseModel):
    """DTO для ответа на запрос (исходящие данные)"""
    blade_id: int
    name: str

    # Настройка для автоматического преобразования из SQLAlchemy модели в JSON
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 2. DTO для Сборок лопаток (BladeAssemblies)
# --------------------------------------------------------------------------

class BladeAssemblyCreateRequest(BaseModel):
    """DTO для создания сборки"""
    name: str = Field(..., min_length=1, max_length=100, description="Название сборки")


class BladeAssemblyResponse(BaseModel):
    """DTO для ответа со списком сборок"""
    blade_assembly_id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 3. DTO для Геометрии (Profile Coordinates)
# --------------------------------------------------------------------------

class CoordinatePointDTO(BaseModel):
    """DTO для одной точки координат"""
    x: float
    y: float
    # profile_name и profile_type могут быть общими для всего списка,
    # но если они отличаются для каждой точки, можно добавить их сюда.
    # В текущей архитектуре репозитория bulk_create принимает словарь,
    # поэтому здесь мы валидируем структуру точек.


class ProfileUploadRequest(BaseModel):
    """DTO для массовой загрузки профиля лопатки"""
    blade_id: int
    profile_name: str
    profile_type: str
    # Список точек для массового сохранения
    points: List[CoordinatePointDTO]

    def to_repository_format(self) -> List[dict]:
        """Метод-маппер: преобразует DTO в формат, ожидаемый репозиторием"""
        return [
            {
                "blade_id": self.blade_id,
                "profile_name": self.profile_name,
                "profile_type": self.profile_type,
                "x": point.x,
                "y": point.y
            }
            for point in self.points
        ]


# --------------------------------------------------------------------------
# 4. DTO для Аппроксимации (Math Results)
# --------------------------------------------------------------------------
# Эти DTO используются, когда Сервис вычисляет математику и передает результат в Репозиторий

class ApproximationResultDTO(BaseModel):
    """DTO с результатами вычисления аппроксимации"""
    profile_type: str
    r_squared: float
    max_profile_value: float
    x_coordinate_max: float

    # Коэффициенты Лежандра (верхнее и нижнее значения)
    legendre_coefficients: List[dict]
    # Формат: [{"upper_value": 1.2, "lower_value": 0.5}, ...]

    # Преобразованные координаты
    transformed_coordinates: List[dict]
    # Формат: [{"profile_type": "root", "x_transformed": 0.1, "y_transformed": 0.2}, ...]