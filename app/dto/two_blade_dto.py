from pydantic import BaseModel, Field
from typing import Optional

class TwoBladeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)   # название расчёта
    blade_id: int                                          # ID основной лопатки
    blade_id_small: int                                    # ID малой лопатки
    chord: float = Field(..., gt=0)                        # хорда большой лопатки
    chord2: float = Field(..., gt=0)                       # хорда малой лопатки
    dely_offset: float = 0.0                               # смещение по Y (можно сделать опциональным)
    t_gas: float                                           # температура газа, K
    t_cool: float                                          # температура охлаждения, K
    t_blade: float                                         # начальная температура лопатки, K
    press0: float                                          # давление торможения, Па
    u0: float                                              # скорость набегающего потока, м/с
    beta: float                                            # угол атаки, градусы
    houter: float                                          # коэффициент теплоотдачи снаружи
    hinner: float                                          # коэффициент теплоотдачи внутри
    rgas: float                                            # газовая постоянная
    cpgas: float                                           # теплоёмкость газа при пост. давлении
    kgas: float                                            # теплопроводность газа
    rhosteel: float                                        # плотность стали
    cpsteel: float                                         # теплоёмкость стали
    ksteel: float                                          # теплопроводность стали