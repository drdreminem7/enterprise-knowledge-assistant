from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


class EvaluationQuestion(Base):
    __tablename__ = "evaluation_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[int] = mapped_column(ForeignKey("evaluation_sets.id"), index=True)
    question: Mapped[str] = mapped_column(Text())
    expected_answer: Mapped[str] = mapped_column(Text())
    document_scope: Mapped[str | None] = mapped_column(Text(), nullable=True)

    evaluation_set = relationship("EvaluationSet", back_populates="questions")
    results = relationship("EvaluationResult", back_populates="evaluation_question", cascade="all, delete-orphan")

