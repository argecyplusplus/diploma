"""Инициализация базы данных начальными данными (материалы, параметры)"""
import logging
from sqlalchemy.orm import Session
from ..models.material import Material, ChemicalElement
from ..models.simulation import (
    InitialCondition, TimeParameter, PotentialFlowParameter,
    ConstructionParameter, BoundaryIdentifier, BladeChord,
    InitialTemperature, ElasticityParameter, StressOutputParameter,
    MaterialProperty, GasProperty, GasFlowParameter
)

logger = logging.getLogger(__name__)


def init_materials(session: Session):
    """Добавляет материалы и химические элементы, если их нет"""

    # Данные материалов (элементов) из таблицы materials
    materials_data = [
        {
            "material_id": 1,
            "name": "Ni",
            "is_alloy": False,
            "density": 8900.0,
            "hardness": 638.0,
            "thermal_conductivity": 90.9,
            "heat_capacity": 460.0,
            "melting_point": 1455.0,
            "thermal_expansion_coef": 13.4
        },
        {
            "material_id": 2,
            "name": "Al",
            "is_alloy": False,
            "density": 2700.0,
            "hardness": 167.0,
            "thermal_conductivity": 237.0,
            "heat_capacity": 904.0,
            "melting_point": 660.0,
            "thermal_expansion_coef": 23.1
        },
        {
            "material_id": 3,
            "name": "Cr",
            "is_alloy": False,
            "density": 7150.0,
            "hardness": 1120.0,
            "thermal_conductivity": 93.9,
            "heat_capacity": 461.0,
            "melting_point": 1907.0,
            "thermal_expansion_coef": 4.9
        },
        {
            "material_id": 4,
            "name": "Mo",
            "is_alloy": False,
            "density": 10200.0,
            "hardness": 1530.0,
            "thermal_conductivity": 138.0,
            "heat_capacity": 244.0,
            "melting_point": 2623.0,
            "thermal_expansion_coef": 4.8
        },
        {
            "material_id": 5,
            "name": "W",
            "is_alloy": False,
            "density": 19300.0,
            "hardness": 3500.0,
            "thermal_conductivity": 173.0,
            "heat_capacity": 138.0,
            "melting_point": 3422.0,
            "thermal_expansion_coef": 4.5
        },
        {
            "material_id": 6,
            "name": "Ti",
            "is_alloy": False,
            "density": 4500.0,
            "hardness": 716.0,
            "thermal_conductivity": 21.9,
            "heat_capacity": 528.0,
            "melting_point": 1668.0,
            "thermal_expansion_coef": 8.6
        },
        {
            "material_id": 7,
            "name": "Hf",
            "is_alloy": False,
            "density": 13310.0,
            "hardness": 176.0,
            "thermal_conductivity": 23.0,
            "heat_capacity": 144.0,
            "melting_point": 2233.0,
            "thermal_expansion_coef": 5.9
        },
        {
            "material_id": 8,
            "name": "C",
            "is_alloy": False,
            "density": 1900.0,
            "hardness": 19.0,
            "thermal_conductivity": 140.0,
            "heat_capacity": 710.0,
            "melting_point": 3550.0,
            "thermal_expansion_coef": 0.8
        }
    ]

    # Данные химических элементов (связь с материалами)
    chemical_elements_data = [
        {"chemical_element_id": 1, "name": "Ni", "type": "Металл", "material_id": 1},
        {"chemical_element_id": 2, "name": "Al", "type": "Металл", "material_id": 2},
        {"chemical_element_id": 3, "name": "Cr", "type": "Металл", "material_id": 3},
        {"chemical_element_id": 4, "name": "Mo", "type": "Металл", "material_id": 4},
        {"chemical_element_id": 5, "name": "W", "type": "Металл", "material_id": 5},
        {"chemical_element_id": 6, "name": "Ti", "type": "Металл", "material_id": 6},
        {"chemical_element_id": 7, "name": "Hf", "type": "Металл", "material_id": 7},
        {"chemical_element_id": 8, "name": "C", "type": "Неметалл", "material_id": 8},
    ]

    added_materials = 0
    added_elements = 0

    # Добавляем материалы
    for m in materials_data:
        existing = session.get(Material, m["material_id"])
        if not existing:
            material = Material(
                material_id=m["material_id"],
                name=m["name"],
                is_alloy=m["is_alloy"],
                density=m["density"],
                hardness=m["hardness"],
                thermal_conductivity=m["thermal_conductivity"],
                heat_capacity=m["heat_capacity"],
                melting_point=m["melting_point"],
                thermal_expansion_coef=m["thermal_expansion_coef"]
            )
            session.add(material)
            added_materials += 1
            logger.info(f"Добавлен материал: {m['name']}")
        else:
            logger.debug(f"Материал уже существует: {m['name']}")

    session.flush()

    # Добавляем химические элементы
    for ce in chemical_elements_data:
        existing = session.get(ChemicalElement, ce["chemical_element_id"])
        if not existing:
            chemical_element = ChemicalElement(
                chemical_element_id=ce["chemical_element_id"],
                name=ce["name"],
                type=ce["type"],
                material_id=ce["material_id"]
            )
            session.add(chemical_element)
            added_elements += 1
            logger.info(f"Добавлен химический элемент: {ce['name']}")
        else:
            logger.debug(f"Химический элемент уже существует: {ce['name']}")

    session.flush()
    logger.info(f"Материалов добавлено: {added_materials}, химических элементов добавлено: {added_elements}")
    return added_materials


def init_default_initial_conditions(session: Session):
    """Создаёт наборы начальных условий по умолчанию"""

    # Убедимся, что материалы существуют
    steel_material = session.get(Material, 1)  # Ni
    if not steel_material:
        logger.error("Материал Ni (id=1) не найден! Сначала добавьте материалы.")
        return

    # Для воздуха используем Al как заглушку (material_id=2)
    air_material = session.get(Material, 2)  # Al

    # ========== Задача 1: Газодинамика ==========
    ic1_name = "Task1 Default (Газодинамика)"
    ic1 = session.query(InitialCondition).filter(InitialCondition.name == ic1_name).first()
    if not ic1:
        ic1 = InitialCondition(name=ic1_name)
        session.add(ic1)
        session.flush()
        ic_id = ic1.initial_conditions_id

        session.add(TimeParameter(initial_conditions_id=ic_id, time=0.125, dt=0.005, nbT=25, Nplot=10))
        session.add(PotentialFlowParameter(initial_conditions_id=ic_id, beta=-10.0, B=10.0))
        session.add(ConstructionParameter(initial_conditions_id=ic_id, NC=50, NSp=70, NSm=70, NSpn=10, NSpm=2))
        session.add(BoundaryIdentifier(initial_conditions_id=ic_id, name="S", value=99.0))
        session.add(BladeChord(initial_conditions_id=ic_id, name="Chord1", value=1.0))
        session.add(InitialTemperature(initial_conditions_id=ic_id, material_id=1, value=0.0))  # Ni
        session.add(ElasticityParameter(initial_conditions_id=ic_id, b=1.0, nu=0.28, KLT=10.5e-6))
        session.add(StressOutputParameter(initial_conditions_id=ic_id, coef=100.0, delt=0.4, Npt=200.0))
        logger.info(f"Создан набор: {ic1_name}")

    # ========== Задача 2-3: Тепловое поле и термоупругость ==========
    ic23_name = "Task23 Default (Тепловое поле + Термоупругость)"
    ic23 = session.query(InitialCondition).filter(InitialCondition.name == ic23_name).first()
    if not ic23:
        ic23 = InitialCondition(name=ic23_name)
        session.add(ic23)
        session.flush()
        ic_id = ic23.initial_conditions_id

        session.add(TimeParameter(initial_conditions_id=ic_id, time=1.0, dt=0.05, nbT=20, Nplot=10))
        session.add(PotentialFlowParameter(initial_conditions_id=ic_id, beta=0.0, B=1.0))
        session.add(ConstructionParameter(initial_conditions_id=ic_id, NC=100, NSp=200, NSm=200, NSpn=10, NSpm=10))
        session.add(BoundaryIdentifier(initial_conditions_id=ic_id, name="S", value=99.0))
        session.add(BladeChord(initial_conditions_id=ic_id, name="Chord1", value=21.7))
        session.add(BladeChord(initial_conditions_id=ic_id, name="Chord2", value=9.0))
        session.add(InitialTemperature(initial_conditions_id=ic_id, material_id=1, value=250.0))  # Ni (сталь)
        if air_material:
            session.add(InitialTemperature(initial_conditions_id=ic_id, material_id=2, value=25.0))  # Al (воздух)
        session.add(ElasticityParameter(initial_conditions_id=ic_id, b=1.0, nu=0.28, KLT=10.5e-6))
        session.add(StressOutputParameter(initial_conditions_id=ic_id, coef=100.0, delt=0.4, Npt=200.0))

        # Добавляем температуропроводность для задачи 2-3
        session.add(MaterialProperty(
            initial_conditions_id=ic_id,
            rhosteel=8200.0, cpsteel=500.0, ksteel=90.5,
            a_steel=12.54, a_air=21.02
        ))
        logger.info(f"Создан набор: {ic23_name}")

    # ========== Задача 4: Переходные процессы ==========
    ic4_name = "Task4 Default (Переходные процессы)"
    ic4 = session.query(InitialCondition).filter(InitialCondition.name == ic4_name).first()
    if not ic4:
        ic4 = InitialCondition(name=ic4_name)
        session.add(ic4)
        session.flush()
        ic_id = ic4.initial_conditions_id

        session.add(TimeParameter(initial_conditions_id=ic_id, time=2.0, dt=0.1, nbT=20, Nplot=10))
        session.add(PotentialFlowParameter(initial_conditions_id=ic_id, beta=0.0, B=1.0))
        session.add(ConstructionParameter(
            initial_conditions_id=ic_id, NC=100, NSp=200, NSm=200, NSpn=10, NSpm=10,
            dely_offset=0.003  # смещение для задачи 4
        ))
        session.add(BoundaryIdentifier(initial_conditions_id=ic_id, name="S", value=99.0))
        session.add(BladeChord(initial_conditions_id=ic_id, name="outer", value=0.217))
        session.add(BladeChord(initial_conditions_id=ic_id, name="inner", value=0.09))
        session.add(InitialTemperature(initial_conditions_id=ic_id, material_id=1, value=1223.0))  # Ni
        session.add(ElasticityParameter(initial_conditions_id=ic_id, b=1.0, nu=0.28, KLT=10.5e-6))
        session.add(StressOutputParameter(initial_conditions_id=ic_id, coef=1.0, delt=0.0004, Npt=180.0))

        # Параметры для задачи 4
        session.add(GasFlowParameter(
            initial_conditions_id=ic_id,
            Tgas=673.0, Tcool=1223.0, U0=1.0, beta=-10.0,
            Press0=1.5e6, houter=15000.0, hinner=15.0
        ))
        session.add(MaterialProperty(
            initial_conditions_id=ic_id,
            rhosteel=8200.0, cpsteel=500.0, ksteel=90.5,
            a_steel=12.54, a_air=21.02
        ))
        session.add(GasProperty(
            initial_conditions_id=ic_id,
            Rgas=287.0, cpgas=1150.0, kgas=0.08
        ))
        logger.info(f"Создан набор: {ic4_name}")

    session.commit()
    logger.info("Все наборы начальных условий созданы")


def init_database(session: Session):
    """Главная функция инициализации БД"""
    logger.info("Начинаем инициализацию базы данных...")
    init_materials(session)
    init_default_initial_conditions(session)
    logger.info("Инициализация базы данных завершена")