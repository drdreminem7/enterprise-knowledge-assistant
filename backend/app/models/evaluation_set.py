from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


class EvaluationSet(Base):
    __tablename__ = "evaluation_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    questions = relationship("EvaluationQuestion", back_populates="evaluation_set", cascade="all, delete-orphan")

