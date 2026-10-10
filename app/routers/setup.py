from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db import get_db
from app.models import User, Workshop
from app.services.env_settings import set_env_value
from app.services.images import save_brand_logo
from app.services.setup_state import is_setup_completed, mark_setup_completed
from app.utils import slugify
from app.view_context import render

router = APIRouter()


@router.get('/setup')
def setup_page(request: Request, db: Session = Depends(get_db)):
    if is_setup_completed(db):
        raise HTTPException(status_code=404)
    return render(request, 'setup.html', {'setup_error': '', 'form_values': {}})


@router.post('/setup')
async def setup_submit(
    request: Request,
    admin_username: str = Form(''),
    admin_password: str = Form(''),
    confirm_admin_password: str = Form(''),
    workshop_name: str = Form(''),
    app_display_name: str = Form(''),
    organization_name: str = Form(''),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    if is_setup_completed(db):
        raise HTTPException(status_code=404)

    username = admin_username.strip()
    workshop_label = workshop_name.strip()
    form_values = {
        'admin_username': username,
        'workshop_name': workshop_label,
        'app_display_name': app_display_name.strip(),
        'organization_name': organization_name.strip(),
    }
    if not username or not admin_password or not confirm_admin_password or not workshop_label:
        return render(
            request,
            'setup.html',
            {'setup_error': 'Tous les champs obligatoires doivent etre remplis.', 'form_values': form_values},
            status_code=400,
        )
    if admin_password != confirm_admin_password:
        return render(
            request,
            'setup.html',
            {'setup_error': 'La confirmation du mot de passe ne correspond pas.', 'form_values': form_values},
            status_code=400,
        )

    workshop_slug = slugify(workshop_label) or 'atelier'
    existing_slug = db.query(Workshop).filter(Workshop.slug == workshop_slug).first()
    if existing_slug:
        workshop_slug = f'{workshop_slug}-1'

    workshop = Workshop(name=workshop_label, slug=workshop_slug, is_active=True)
    db.add(workshop)
    db.flush()

    admin = User(
        username=username,
        password_hash=hash_password(admin_password),
        role='admin',
        is_active=True,
        active_workshop_id=workshop.id,
    )
    db.add(admin)
    db.commit()

    display_name = app_display_name.strip()
    organization = organization_name.strip()
    if display_name:
        set_env_value('APP_DISPLAY_NAME', display_name)
    if organization:
        set_env_value('APP_ORGANIZATION_NAME', organization)
    if logo and logo.filename:
        set_env_value('APP_LOGO_PATH', save_brand_logo(logo))

    mark_setup_completed()
    return RedirectResponse(url='/login?notice=setup-complete', status_code=303)
