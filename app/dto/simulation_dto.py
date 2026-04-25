from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


# --------------------------------------------------------------------------
# 1. DTO для Начальных Условий (Иерархическая структура)
# --------------------------------------------------------------------------
# Начальные условия состоят из множества групп параметров.
# Мы создаем вложенные DTO для каждой группы.

class TimeParamsRequest(BaseModel):
    """Параметры времени"""
    time: float = Field(..., gt=0, description="Общее время моделирования")
    dt: float = Field(..., gt=0, description="Шаг по времени")
    nbT: float = Field(..., gt=0, description="Коэффициент nbT")
    Nplot: float = Field(..., gt=0, description="Частота вывода графиков")


class BladeChordRequest(BaseModel):
    """Параметры хорды лопатки"""
    name: str = Field(..., description="Наименование (напр. 'Root')")
    value: float = Field(..., gt=0, description="Значение хорды")


class PotentialFlowRequest(BaseModel):
    """Параметры потенциального потока"""
    beta: float = Field(..., description="Угол атаки")
    B: float = Field(..., description="Коэффициент B")


class BoundaryIdentifierRequest(BaseModel):
    """Одно граничное условие"""
    name: str = Field(..., description="Имя границы (напр. 'Inlet')")
    value: float = Field(..., description="Значение")


class ElasticityParamsRequest(BaseModel):
    """Параметры упругости"""
    b: float = Field(..., description="Параметр b")
    nu: float = Field(..., ge=0, le=0.5, description="Коэффициент Пуассона")
    KLT: float = Field(..., description="Параметр KLT")


class ConstructionParamsRequest(BaseModel):
    """Конструктивные параметры сетки/модели"""
    NC: int = Field(..., gt=0, description="Количество ячеек C")
    NSp: int = Field(..., gt=0, description="Количество узлов Sp")
    NSm: int = Field(..., gt=0, description="Количество узлов Sm")
    NSpn: int = Field(..., gt=0, description="Количество узлов Spn")
    NSpm: int = Field(..., gt=0, description="Количество узлов Spm")


class InitialTemperatureRequest(BaseModel):
    """Начальная температура для материала"""
    material_id: int = Field(..., description="ID материала")
    value: float = Field(..., gt=0, description="Температура в Кельвинах")


class StressOutputRequest(BaseModel):
    """Параметры вывода напряжений"""
    coef: float = Field(..., description="Коэффициент coef")
    delt: float = Field(..., description="Параметр delt")
    Npt: float = Field(..., description="Параметр Npt")


# АГРЕГАТОР: Полный запрос на создание Начальных Условий
class InitialConditionsCreateRequest(BaseModel):
    """
    Полный набор конфигурации для симуляции.
    Позволяет создать "пакет" начальных условий со всеми подпараметрами.
    """
    name: str = Field(..., min_length=1, description="Название набора условий")

    # Опциональные блоки параметров. Если блок не передан, он не создается в БД.
    time_params: Optional[TimeParamsRequest] = None
    blade_chord: Optional[BladeChordRequest] = None
    flow_params: Optional[PotentialFlowRequest] = None
    boundaries: List[BoundaryIdentifierRequest] = []  # Массив границ
    elasticity_params: Optional[ElasticityParamsRequest] = None
    construction_params: Optional[ConstructionParamsRequest] = None
    initial_temperatures: List[InitialTemperatureRequest] = []  # Массив температур
    stress_output: Optional[StressOutputRequest] = None


# --------------------------------------------------------------------------
# 2. DTO для Симуляции (Simulation)
# --------------------------------------------------------------------------

class SimulationCreateRequest(BaseModel):
    """DTO для запуска новой симуляции"""
    name: str = Field(..., min_length=1, max_length=100, description="Название симуляции")
    blade_assembly_id: int = Field(..., gt=0, description="ID сборки лопаток")
    blade_id: int = Field(..., gt=0, description="ID конкретной лопатки")
    initial_conditions_id: int = Field(..., gt=0, description="ID созданного набора начальных условий")


class SimulationResponse(BaseModel):
    """DTO для отображения списка симуляций"""
    simulation_id: int
    name: str
    blade_assembly_id: int
    blade_id: int
    initial_conditions_id: int

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 3. DTO для Задач, Результатов и Материалов
# --------------------------------------------------------------------------

class SimulationTaskRequest(BaseModel):
    """Добавление вычислительной задачи"""
    task_value: float = Field(..., description="Значение параметра задачи")
    description: Optional[str] = None


class SimulationMaterialRequest(BaseModel):
    """Привязка материала к симуляции"""
    material_id: int = Field(..., gt=0, description="ID материала из справочника")


class SimulationResultResponse(BaseModel):
    """Информация о файле результата"""
    result_id: int
    file_type: str
    file_path: str
    description: Optional[str]
    created_at: str

    model_config = ConfigDict(from_attributes=True)