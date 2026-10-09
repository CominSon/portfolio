from app.api.routes.employers import router as employers_router
from app.api.routes.interviews import router as interviews_router
from app.api.routes.templates import router as templates_router

__all__ = ["employers_router", "interviews_router", "templates_router"]
