from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


# --------------------------------------------------------------------------
# 1. DTO для Материалов (Materials)
# --------------------------------------------------------------------------

class MaterialCreateRequest(BaseModel):
    """DTO для создания нового материала или сплава"""
    name: str = Field(..., min_length=1, max_length=100, description="Название материала")
    type: str = Field(..., description="Тип: 'element' или 'alloy'")

    # Обязательные физические свойства
    density: float = Field(..., gt=0, description="Плотность (кг/м³)")
    thermal_conductivity: float = Field(..., gt=0, description="Теплопроводность")
    heat_capacity: float = Field(..., gt=0, description="Теплоемкость")
    thermal_expansion_coef: float = Field(..., gt=0, description="Коэффициент теплового расширения")

    # Необязательные свойства
    hardness: Optional[float] = Field(None, description="Твердость")
    melting_point: Optional[float] = Field(None, description="Температура плавления")

    def to_repository_kwargs(self) -> dict:
        """Преобразует DTO в аргументы для метода create репозитория"""
        return {
            "name": self.name,
            "type": self.type,
            "density": self.density,
            "thermal_conductivity": self.thermal_conductivity,
            "heat_capacity": self.heat_capacity,
            "thermal_expansion_coef": self.thermal_expansion_coef,
            "hardness": self.hardness,
            "melting_point": self.melting_point
        }


class MaterialResponse(BaseModel):
    """DTO для отображения материала в интерфейсе"""
    material_id: int
    name: str
    type: str
    density: float
    hardness: Optional[float]
    thermal_conductivity: float
    heat_capacity: float
    melting_point: Optional[float]
    thermal_expansion_coef: float

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 2. DTO для Сплавов (Alloy Compositions)
# --------------------------------------------------------------------------
# Эти DTO используются, когда мы редактируем состав конкретного сплава

class AlloyComponentRequest(BaseModel):
    """DTO для добавления компонента в сплав"""
    component_material_id: int = Field(..., description="ID материала-компонента")
    mass_fraction: float = Field(..., ge=0, le=1, description="Массовая доля (от 0.0 до 1.0)")


class AlloyComponentResponse(BaseModel):
    """DTO для отображения состава сплава"""
    alloy_composition_id: int
    component_material_id: int
    mass_fraction: float

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 3. DTO для Химических элементов (Chemical Elements)
# --------------------------------------------------------------------------

class ChemicalElementRequest(BaseModel):
    """DTO для добавления химического элемента к материалу"""
    symbol: str = Field(..., min_length=1, max_length=3, description="Символ (напр. Fe)")
    name: str = Field(..., description="Полное название")


class ChemicalElementResponse(BaseModel):
    """DTO для отображения списка элементов"""
    chemical_element_id: int
    symbol: str
    name: str

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 4. DTO для Значений упругости (Elasticity Values)
# --------------------------------------------------------------------------

class ElValueRequest(BaseModel):
    """DTO для привязки параметра упругости к материалу"""
    elasticity_parameters_id: int
    value: float


class ElValueResponse(BaseModel):
    """DTO для отображения значений упругости"""
    el_values_id: int
    elasticity_parameters_id: int
    value: float

    model_config = ConfigDict(from_attributes=True)