from typing import Any
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func
from datetime import datetime

# Базовый класс для моделей (SQLAlchemy 2.0)
class Base(DeclarativeBase):
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    def to_dict(self) -> dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

# Инициализируем SQLAlchemy с новой базовой моделью
db = SQLAlchemy(model_class=Base)