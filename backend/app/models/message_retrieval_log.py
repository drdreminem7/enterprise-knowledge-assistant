from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base


class MessageRetrievalLog(Base):
    __tablename__ = "message_retrieval_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_message_id: Mapped[int] = mapped_column(
        ForeignKey("conversation_messages.id"),
        index=True,
    )
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id"), index=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)

    message = relationship("ConversationMessage", back_populates="retrieval_logs")
    chunk = relationship("Chunk")
