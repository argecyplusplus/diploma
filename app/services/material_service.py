from typing import List, Dict
from sqlalchemy.orm import Session
from ..repositories.material_repository import MaterialRepository
from ..dto.material_dto import (
    MaterialCreateRequest, MaterialUpdateRequest, AlloyCreateRequest,
    ChemicalElementCreateRequest
)

class MaterialService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = MaterialRepository(session)

    def _calculate_properties(self, components: List[dict]) -> Dict:
        """Расчёт свойств сплава по правилу смесей (Rule of Mixtures)"""
        inv_density = 0.0
        conductivity = 0.0
        heat_cap = 0.0
        expansion = 0.0
        hardness_sum = 0.0
        melting_sum = 0.0

        for comp in components:
            mat = self.repo.get_by_id(comp["component_material_id"])
            if not mat: continue
            w = comp["mass_fraction"]

            inv_density += w / mat.density
            conductivity += w * mat.thermal_conductivity
            heat_cap += w * mat.heat_capacity
            expansion += w * mat.thermal_expansion_coef
            if mat.hardness is not None: hardness_sum += w * mat.hardness
            if mat.melting_point is not None: melting_sum += w * mat.melting_point

        return {
            "density": 1.0 / inv_density if inv_density > 0 else 0.0,
            "thermal_conductivity": conductivity,
            "heat_capacity": heat_cap,
            "thermal_expansion_coef": expansion,
            "hardness": hardness_sum if hardness_sum > 0 else None,
            "melting_point": melting_sum if melting_sum > 0 else None,
        }

    def create_element(self, data: ChemicalElementCreateRequest):
        """Создание химического элемента + материала"""
        # 1. Создаём материал
        material = self.repo.create(
            name=data.name,
            # is_alloy=False, # Если в модели есть такой флаг
            density=data.density,
            hardness=data.hardness,
            thermal_conductivity=data.thermal_conductivity,
            heat_capacity=data.heat_capacity,
            melting_point=data.melting_point,
            thermal_expansion_coef=data.thermal_expansion_coef
        )
        # 2. Создаём запись химического элемента
        element = self.repo.create_chemical_element(
            symbol=data.symbol,
            name=data.name,
            type=data.type,
            material_id=material.material_id
        )
        return element

    def create_alloy(self, data: AlloyCreateRequest):
        """Создание сплава через правило смесей"""
        # 1. Считаем свойства
        props = self._calculate_properties([c.model_dump() for c in data.components])

        # 2. Создаём материал-сплав
        alloy = self.repo.create(
            name=data.name,
            is_alloy=True,
            **props
        )
        # 3. Сохраняем состав
        self.repo.update_alloy_composition(
            alloy.material_id,
            [c.model_dump() for c in data.components]
        )
        return alloy

    def update_element(self, element_id: int, data: ChemicalElementCreateRequest):
        """Обновление химического элемента"""
        element = self.repo.get_element_by_id(element_id)
        if not element:
            raise ValueError("Элемент не найден")

        # Обновляем связанные свойства материала
        material = element.material
        for field in ['density', 'hardness', 'thermal_conductivity',
                      'heat_capacity', 'melting_point', 'thermal_expansion_coef']:
            value = getattr(data, field)
            if value is not None:
                setattr(material, field, value)

        # Обновляем type и name элемента
        if data.type: element.type = data.type
        if data.name:
            element.name = data.name
            material.name = data.name  # синхронизируем имя

        self.repo.update(material)
        self.repo.update(element)

        # Авто-пересчёт зависимых сплавов
        self._recalculate_dependent_alloys(material.material_id)
        return element

    def _recalculate_dependent_alloys(self, material_id: int):
        usages = self.repo.get_alloys_using_component(material_id)
        alloy_ids = {u.alloy_id for u in usages}

        for aid in alloy_ids:
            comps = self.repo.get_alloy_components(aid)
            props = self._calculate_properties(
                [{"component_material_id": c.component_material_id, "mass_fraction": c.mass_fraction} for c in comps])

            alloy = self.repo.get_by_id(aid)
            for k, v in props.items():
                setattr(alloy, k, v)
            self.repo.update(alloy)