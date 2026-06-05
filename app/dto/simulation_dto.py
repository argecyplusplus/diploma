from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

class TaskType(str, Enum):
    TASK1 = "task1"          # газодинамика
    TASK2 = "task2"          # тепловое поле
    TASK3 = "task3"          # термоупругость
    TASK4 = "task4"          # переходные тепловые процессы


class SimulationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    blade_id: Optional[int] = None
    assembly_id: Optional[int] = None
    material_ids: List[int] = Field(..., min_length=1)
    initial_conditions_id: int
    task_type: TaskType


class TimeParamRequest(BaseModel):
    time: float
    dt: float
    nbT: float
    Nplot: float


class PotentialFlowRequest(BaseModel):
    beta: float
    B: float


class BoundaryIdRequest(BaseModel):
    name: str
    value: float


class ConstructionParamRequest(BaseModel):
    NC: int
    NSp: int
    NSm: int
    NSpn: int
    NSpm: int


class InitialTempRequest(BaseModel):
    material_id: int
    value: float


class ElasticityParamRequest(BaseModel):
    b: float
    nu: float
    KLT: float


class StressOutParamRequest(BaseModel):
    coef: float
    delt: float
    Npt: float


class BladeChordRequest(BaseModel):
    name: str
    value: float


class EiValueRequest(BaseModel):
    material_id: int
    value: float


# Новые DTO для задачи 4
class GasFlowParamsRequest(BaseModel):
    """Параметры газового потока для задачи 4"""
    Tgas: float = Field(..., description="Температура газа, °C")
    Tcool: float = Field(..., description="Температура охладителя, °C")
    U0: float = Field(1.0, description="Скорость потока, м/с")
    beta: float = Field(-10.0, description="Угол атаки, градусы")
    Press0: float = Field(1.5e6, description="Давление на входе, Па")
    houter: float = Field(15000.0, description="Коэф. теплоотдачи внешней поверхности, Вт/(м²·K)")
    hinner: float = Field(15.0, description="Коэф. теплоотдачи внутренней поверхности, Вт/(м²·K)")


class MaterialPropertiesRequest(BaseModel):
    """Свойства материала лопатки для задачи 4"""
    rhosteel: float = Field(8200.0, description="Плотность, кг/м³")
    cpsteel: float = Field(500.0, description="Удельная теплоемкость, Дж/(кг·К)")
    ksteel: float = Field(90.5, description="Теплопроводность, Вт/(м·К)")
    a_steel: Optional[float] = Field(None, description="Температуропроводность стали, мм²/с")
    a_air: Optional[float] = Field(None, description="Температуропроводность воздуха, мм²/с")


class GasPropertiesRequest(BaseModel):
    """Свойства газа для задачи 4"""
    Rgas: float = Field(287.0, description="Газовая постоянная, Дж/(кг·К)")
    cpgas: float = Field(1150.0, description="Удельная теплоемкость газа, Дж/(кг·К)")
    kgas: float = Field(0.08, description="Теплопроводность газа, Вт/(м·К)")


# Расширяем InitialConditionCreateRequest
class InitialConditionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    time_parameters: TimeParamRequest
    potential_flow: PotentialFlowRequest
    boundaries: List[BoundaryIdRequest] = []
    construction: ConstructionParamRequest
    initial_temps: List[InitialTempRequest] = []
    elasticity: ElasticityParamRequest
    stress_output: StressOutParamRequest
    chords: List[BladeChordRequest] = []
    ei_values: List[EiValueRequest] = []
    gas_flow_params: Optional[GasFlowParamsRequest] = None
    material_properties: Optional[MaterialPropertiesRequest] = None
    gas_properties: Optional[GasPropertiesRequest] = None
    model_config = ConfigDict(from_attributes=True)


class SimulationResponse(BaseModel):
    simulation_id: int
    name: str
    status: str = "created"
    model_config = ConfigDict(from_attributes=True)