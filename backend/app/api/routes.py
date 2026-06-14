from fastapi import APIRouter

from backend.app.api.endpoints.analytics import router as analytics_router
from backend.app.api.endpoints.chat import router as chat_router
from backend.app.api.endpoints.documents import router as documents_router
from backend.app.api.endpoints.evaluation import router as evaluation_router
from backend.app.api.endpoints.feedback import router as feedback_router
from backend.app.api.endpoints.health import router as health_router
from backend.app.api.endpoints.knowledge_bases import router as knowledge_bases_router

router = APIRouter()
router.include_router(health_router)
router.include_router(analytics_router, prefix="/api")
router.include_router(chat_router, prefix="/api")
router.include_router(knowledge_bases_router, prefix="/api")
router.include_router(documents_router, prefix="/api")
router.include_router(evaluation_router, prefix="/api")
router.include_router(feedback_router, prefix="/api")
