from sqlalchemy import text

from backend.app.models.chunk import Chunk
from backend.app.models.conversation import Conversation
from backend.app.models.conversation_message import ConversationMessage
from backend.app.db.session import Base, engine
from backend.app.models.document import Document
from backend.app.models.evaluation_question import EvaluationQuestion
from backend.app.models.evaluation_result import EvaluationResult
from backend.app.models.evaluation_set import EvaluationSet
from backend.app.models.feedback import Feedback
from backend.app.models.knowledge_base import KnowledgeBase
from backend.app.models.message_retrieval_log import MessageRetrievalLog
from backend.app.models.retrieval_log import RetrievalLog


def initialize_database() -> None:
    with engine.begin() as connection:
        extension_exists = connection.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        if not extension_exists:
            connection.execute(text("CREATE EXTENSION vector"))
        connection.execute(
            text(
                "ALTER TABLE IF EXISTS conversation_messages "
                "ADD COLUMN IF NOT EXISTS rewritten_query TEXT"
            )
        )
    Base.metadata.create_all(bind=engine)
