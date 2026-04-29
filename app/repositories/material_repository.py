from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from ..models.material import Material, AlloyComposition, ChemicalElement, ElValue

class MaterialRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> List[Material]:
        return self.session.scalars(select(Material)).all()

    def get_elements(self) -> List[Material]:
        # Элементы — это материалы, которые НЕ являются сплавами (is_alloy=False)
        # И у которых есть связь с ChemicalElement (опционально, для чистоты)
        return self.session.scalars(
            select(Material).where(Material.is_alloy == False)
        ).all()

    def get_alloys(self) -> List[Material]:
        # Сплавы — это материалы, которые ЯВЛЯЮТСЯ сплавами (is_alloy=True)
        return self.session.scalars(
            select(Material).where(Material.is_alloy == True)
        ).all()

    def get_by_id(self, material_id: int) -> Optional[Material]:
        return self.session.get(Material, material_id)

    def create(self, **kwargs) -> Material:
        mat = Material(**kwargs)
        self.session.add(mat)
        self.session.flush()
        return mat

    def update(self, material: Material) -> Material:
        self.session.merge(material)
        return material

    def delete(self, material: Material):
        self.session.delete(material)

    def get_alloy_components(self, alloy_id: int) -> List[AlloyComposition]:
        return self.session.scalars(
            select(AlloyComposition).where(AlloyComposition.alloy_id == alloy_id)
        ).all()

    def get_alloys_using_component(self, material_id: int) -> List[AlloyComposition]:
        """Находит все сплавы, где материал используется как компонент"""
        return self.session.scalars(
            select(AlloyComposition).where(AlloyComposition.component_material_id == material_id)
        ).all()

    def update_alloy_composition(self, alloy_id: int, components_data: List[dict]):
        """Полностью заменяет состав сплава"""
        self.session.execute(
            select(AlloyComposition).where(AlloyComposition.alloy_id == alloy_id)
        ).delete()
        self.session.flush()
        for comp in components_data:
            self.session.add(AlloyComposition(alloy_id=alloy_id, **comp))
        self.session.flush()

    def get_elements_with_type(self) -> List[ChemicalElement]:
        """Получить все химические элементы с их типом и свойствами материала"""
        return self.session.scalars(
            select(ChemicalElement)
            .join(Material, ChemicalElement.material_id == Material.material_id)
            .options(
                joinedload(ChemicalElement.material)
            )
        ).all()

    def get_element_by_id_with_type(self, element_id: int) -> Optional[ChemicalElement]:
        """Получить химический элемент по ID с типом и свойствами материала"""
        return self.session.scalars(
            select(ChemicalElement)
            .where(ChemicalElement.chemical_element_id == element_id)
            .join(Material, ChemicalElement.material_id == Material.material_id)
            .options(
                joinedload(ChemicalElement.material)
            )
        ).first()

    def get_element_by_id(self, element_id: int) -> Optional[ChemicalElement]:
        """Получить химический элемент по ID без eager loading"""
        return self.session.get(ChemicalElement, element_id)

    def create_chemical_element(self, name: str, type: str, material_id: int) -> ChemicalElement:
        """Создать запись химического элемента"""
        element = ChemicalElement(
            name=name,
            type=type,
            material_id=material_id
        )
        self.session.add(element)
        self.session.flush()
        return element