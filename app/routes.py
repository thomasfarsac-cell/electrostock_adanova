from __future__ import annotations

from fastapi import APIRouter
from app.routers.admin_users import router as admin_users_router
from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.component_label_api import router as component_label_api_router
from app.routers.components import router as components_router
from app.routers.dashboard import router as dashboard_router
from app.routers.imports import router as imports_router
from app.routers.labels import component_labels_router, location_labels_router
from app.routers.locations import router as locations_router
from app.routers.references import router as references_router
from app.routers.scan import router as scan_router_module
from app.routers.settings import router as settings_router
from app.routers.setup import router as setup_router
from app.routers.workshops import router as workshops_router
router = APIRouter()
router.include_router(setup_router)
router.include_router(auth_router)
router.include_router(admin_users_router)
router.include_router(workshops_router)
router.include_router(settings_router)
router.include_router(scan_router_module)


router.include_router(component_labels_router)
router.include_router(component_label_api_router)
router.include_router(dashboard_router)

router.include_router(components_router)

router.include_router(locations_router)

router.include_router(location_labels_router)

router.include_router(categories_router)
router.include_router(references_router)

router.include_router(imports_router)

