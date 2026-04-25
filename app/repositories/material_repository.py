from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select, delete as sql_delete

# Импорт моделей
from ..models.material import (
    Material, AlloyComposition, ChemicalElement, ElValue
)
# Импорт модели из модуля симуляций (для связи ElValue)
from ..models.simulation import ElasticityParameter


class MaterialRepository:
    """
    Репозиторий для управления материалами, сплавами и их свойствами.
    """

    def __init__(self, session: Session):
        self.session = session

    # --- Базовые операции (CRUD) ---

    def get_by_id(self, material_id: int) -> Optional[Material]:
        return self.session.get(Material, material_id)

    def get_by_name(self, name: str) -> Optional[Material]:
        return self.session.scalar(select(Material).where(Material.name == name))

    def get_all(self) -> List[Material]:
        return self.session.scalars(select(Material)).all()

    def create(self, name: str, type: str, density: float, thermal_conductivity: float,
               heat_capacity: float, thermal_expansion_coef: float,
               hardness: Optional[float] = None, melting_point: Optional[float] = None) -> Material:

        new_material = Material(
            name=name,
            type=type,
            density=density,
            thermal_conductivity=thermal_conductivity,
            heat_capacity=heat_capacity,
            thermal_expansion_coef=thermal_expansion_coef,
            hardness=hardness,
            melting_point=melting_point
        )
        self.session.add(new_material)
        self.session.flush()
        return new_material

    def update(self, material: Material) -> Material:
        self.session.merge(material)
        return material

    def delete(self, material: Material):
        # Примечание: Если материал используется как компонент в сплаве,
        # SQLAlchemy выбросит IntegrityError из-за ON DELETE RESTRICT.
        # Это ожидаемое поведение для защиты целостности данных.
        self.session.delete(material)

    # --- Управление сплавами (Alloy Compositions) ---
    # Поскольку AlloyComposition связывает Material сам с собой,
    # нужны методы для управления этой связью.

    def add_component_to_alloy(self, alloy_id: int, component_id: int, mass_fraction: float) -> AlloyComposition:
        """
        Добавляет компонент в сплав.
        alloy_id: ID материала, который является сплавом.
        component_id: ID материала, который добавляется как компонент.
        """
        # Проверка на дубликат (нельзя добавить один компонент дважды)
        exists = self.session.scalar(
            select(AlloyComposition).where(
                AlloyComposition.alloy_id == alloy_id,
                AlloyComposition.component_material_id == component_id
            )
        )
        if exists:
            # Обновляем массовую долю, если компонент уже есть
            exists.mass_fraction = mass_fraction
            self.session.flush()
            return exists

        composition = AlloyComposition(
            alloy_id=alloy_id,
            component_material_id=component_id,
            mass_fraction=mass_fraction
        )
        self.session.add(composition)
        self.session.flush()
        return composition

    def get_alloy_components(self, alloy_id: int) -> List[AlloyComposition]:
        """Получает список всех компонентов для конкретного сплава"""
        alloy = self.get_by_id(alloy_id)
        if not alloy:
            return []
        return alloy.alloy_compositions_as_alloy

    def get_material_usage_in_alloys(self, material_id: int) -> List[AlloyComposition]:
        """
        Показывает, в каких сплавах данный материал используется как компонент.
        Полезно перед удалением материала (проверка RESTRICT).
        """
        return self.session.scalars(
            select(AlloyComposition).where(AlloyComposition.component_material_id == material_id)
        ).all()

    # --- Управление химическими элементами ---

    def add_chemical_element(self, material_id: int, symbol: str, name: str) -> ChemicalElement:
        element = ChemicalElement(material_id=material_id, symbol=symbol, name=name)
        self.session.add(element)
        self.session.flush()
        return element

    def get_chemical_elements(self, material_id: int) -> List[ChemicalElement]:
        return self.session.scalars(
            select(ChemicalElement).where(ChemicalElement.material_id == material_id)
        ).all()

    # --- Управление значениями упругости (Связь с модулем Simulation) ---
    # ElValue связывает Material и ElasticityParameter

    def add_elasticity_value(self, material_id: int, elasticity_param_id: int, value: float) -> ElValue:
        """
        Привязывает значение упругости к материалу для конкретного набора параметров.
        """
        el_value = ElValue(
            material_id=material_id,
            elasticity_parameters_id=elasticity_param_id,
            value=value
        )
        self.session.add(el_value)
        self.session.flush()
        return el_value

    def get_elasticity_values(self, material_id: int) -> List[ElValue]:
        """Получает все значения упругости для материала"""
        return self.session.scalars(
            select(ElValue).where(ElValue.material_id == material_id)
        ).all()