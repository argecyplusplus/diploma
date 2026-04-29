from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# ================= МАТЕРИАЛЫ (Базовые) =================

class MaterialCreateRequest(BaseModel):
    """DTO для создания материала/элемента"""
    name: str = Field(..., min_length=1, max_length=100)
    # type удален, так как тип определяется контекстом (элемент или сплав)
    density: float = Field(..., gt=0)
    thermal_conductivity: float = Field(..., gt=0)
    heat_capacity: float = Field(..., gt=0)
    thermal_expansion_coef: float = Field(..., gt=0)
    hardness: Optional[float] = None
    melting_point: Optional[float] = None


class MaterialUpdateRequest(BaseModel):
    """DTO для обновления свойств материала"""
    density: Optional[float] = None
    hardness: Optional[float] = None
    thermal_conductivity: Optional[float] = None
    heat_capacity: Optional[float] = None
    melting_point: Optional[float] = None
    thermal_expansion_coef: Optional[float] = None


class MaterialResponse(BaseModel):
    """Ответ API с данными материала"""
    material_id: int
    name: str
    # type: str # Можно оставить, если нужно различать element/alloy в ответе
    density: float
    hardness: Optional[float]
    thermal_conductivity: float
    heat_capacity: float
    melting_point: Optional[float]
    thermal_expansion_coef: float
    model_config = ConfigDict(from_attributes=True)


# ================= ХИМИЧЕСКИЕ ЭЛЕМЕНТЫ =================

class ChemicalElementCreateRequest(BaseModel):
    """Создание химического элемента + базового материала"""
    name: str = Field(..., min_length=1, max_length=100)
    # Тип элемента из старой программы
    type: Literal['Металл', 'Неметалл', 'Оксид', 'Нитрид', 'Карбид', 'Композит', 'Газ']

    # Свойства материала (дублируются для удобства единого вызова API)
    density: float = Field(..., gt=0)
    thermal_conductivity: float = Field(..., gt=0)
    heat_capacity: float = Field(..., gt=0)
    thermal_expansion_coef: float = Field(..., gt=0)
    hardness: Optional[float] = None
    melting_point: Optional[float] = None


class ChemicalElementUpdateRequest(BaseModel):
    """Обновление химического элемента"""
    name: Optional[str] = None
    type: Optional[Literal['Металл', 'Неметалл', 'Оксид', 'Нитрид', 'Карбид', 'Композит', 'Газ']] = None

    density: Optional[float] = None
    thermal_conductivity: Optional[float] = None
    heat_capacity: Optional[float] = None
    thermal_expansion_coef: Optional[float] = None
    hardness: Optional[float] = None
    melting_point: Optional[float] = None


class ChemicalElementResponse(BaseModel):
    """Ответ с данными химического элемента и его свойств"""
    chemical_element_id: int
    name: str
    type: str
    material_id: int
    density: float
    hardness: Optional[float]
    thermal_conductivity: float
    heat_capacity: float
    melting_point: Optional[float]
    thermal_expansion_coef: float
    model_config = ConfigDict(from_attributes=True)


# ================= СПЛАВЫ =================

class AlloyComponentRequest(BaseModel):
    """Компонент сплава для создания"""
    component_material_id: int
    mass_fraction: float = Field(..., ge=0, le=1, description="От 0.0 до 1.0")


class AlloyComponentResponse(BaseModel):
    """Ответ с данными компонента сплава"""
    alloy_composition_id: int
    component_material_id: int
    mass_fraction: float
    model_config = ConfigDict(from_attributes=True)


class AlloyCreateRequest(BaseModel):
    """Создание сплава с компонентами"""
    name: str = Field(..., min_length=1, max_length=100)
    components: List[AlloyComponentRequest] = Field(..., min_length=2)