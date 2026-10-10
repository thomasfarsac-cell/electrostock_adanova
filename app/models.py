from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base, TimestampMixin):
    __tablename__ = 'users'
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'stock_manager', 'viewer')", name='ck_users_role'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    theme_id: Mapped[str] = mapped_column(String(40), default='sober_dark')
    active_workshop_id: Mapped[int | None] = mapped_column(ForeignKey('workshops.id', ondelete='SET NULL'), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    active_workshop: Mapped['Workshop | None'] = relationship('Workshop')


class Workshop(Base, TimestampMixin):
    __tablename__ = 'workshops'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    ai_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    categories: Mapped[list['Category']] = relationship('Category', back_populates='workshop')
    locations: Mapped[list['Location']] = relationship('Location', back_populates='workshop')
    custom_fields: Mapped[list['CustomField']] = relationship('CustomField', back_populates='workshop')
    manufacturers: Mapped[list['Manufacturer']] = relationship('Manufacturer', back_populates='workshop')
    packages: Mapped[list['Package']] = relationship('Package', back_populates='workshop')
    components: Mapped[list['Component']] = relationship('Component', back_populates='workshop')


class Category(Base, TimestampMixin):
    __tablename__ = 'categories'
    __table_args__ = (
        UniqueConstraint('workshop_id', 'parent_id', 'name', name='uq_categories_workshop_parent_name'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey('workshops.id', ondelete='SET NULL'), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    workshop: Mapped['Workshop | None'] = relationship('Workshop', back_populates='categories')
    parent: Mapped['Category | None'] = relationship('Category', remote_side=[id], back_populates='children')
    children: Mapped[list['Category']] = relationship('Category', back_populates='parent', cascade='save-update')
    components: Mapped[list['Component']] = relationship('Component', back_populates='category')


class Manufacturer(Base, TimestampMixin):
    __tablename__ = 'manufacturers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey('workshops.id', ondelete='SET NULL'), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    workshop: Mapped['Workshop | None'] = relationship('Workshop', back_populates='manufacturers')
    components: Mapped[list['Component']] = relationship('Component', back_populates='manufacturer')


class Package(Base, TimestampMixin):
    __tablename__ = 'packages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey('workshops.id', ondelete='SET NULL'), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    workshop: Mapped['Workshop | None'] = relationship('Workshop', back_populates='packages')
    components: Mapped[list['Component']] = relationship('Component', back_populates='package')


class Location(Base, TimestampMixin):
    __tablename__ = 'locations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey('workshops.id', ondelete='SET NULL'), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(300), nullable=True)

    workshop: Mapped['Workshop | None'] = relationship('Workshop', back_populates='locations')
    components: Mapped[list['Component']] = relationship('Component', back_populates='location')


class CustomField(Base, TimestampMixin):
    __tablename__ = 'custom_fields'
    __table_args__ = (
        UniqueConstraint('workshop_id', 'name', name='uq_custom_fields_workshop_name'),
        UniqueConstraint('workshop_id', 'slug', name='uq_custom_fields_workshop_slug'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey('workshops.id', ondelete='SET NULL'), nullable=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(20), default='text')
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    workshop: Mapped['Workshop | None'] = relationship('Workshop', back_populates='custom_fields')
    values: Mapped[list['ComponentCustomFieldValue']] = relationship(
        'ComponentCustomFieldValue',
        back_populates='custom_field',
        cascade='all, delete-orphan',
    )


class Component(Base, TimestampMixin):
    __tablename__ = 'components'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    part_number: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    workshop_id: Mapped[int | None] = mapped_column(ForeignKey('workshops.id', ondelete='SET NULL'), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id', ondelete='SET NULL'), nullable=True)
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey('manufacturers.id', ondelete='SET NULL'), nullable=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey('packages.id', ondelete='SET NULL'), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey('locations.id', ondelete='SET NULL'), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    minimum_quantity: Mapped[int] = mapped_column(Integer, default=0)
    datasheet_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[str | None] = mapped_column(String(300), nullable=True)

    workshop: Mapped['Workshop | None'] = relationship('Workshop', back_populates='components')
    category: Mapped['Category | None'] = relationship('Category', back_populates='components')
    manufacturer: Mapped['Manufacturer | None'] = relationship('Manufacturer', back_populates='components')
    package: Mapped['Package | None'] = relationship('Package', back_populates='components')
    location: Mapped['Location | None'] = relationship('Location', back_populates='components')
    custom_values: Mapped[list['ComponentCustomFieldValue']] = relationship(
        'ComponentCustomFieldValue',
        back_populates='component',
        cascade='all, delete-orphan',
    )
    stock_movements: Mapped[list['StockMovement']] = relationship(
        'StockMovement',
        back_populates='component',
        cascade='all, delete-orphan'
    )


class ComponentCustomFieldValue(Base, TimestampMixin):
    __tablename__ = 'component_custom_field_values'
    __table_args__ = (UniqueConstraint('component_id', 'custom_field_id', name='uq_component_custom_field'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey('components.id', ondelete='CASCADE'))
    custom_field_id: Mapped[int] = mapped_column(ForeignKey('custom_fields.id', ondelete='CASCADE'))
    value: Mapped[str | None] = mapped_column(Text, nullable=True)

    component: Mapped['Component'] = relationship('Component', back_populates='custom_values')
    custom_field: Mapped['CustomField'] = relationship('CustomField', back_populates='values')


class StockMovement(Base):
    __tablename__ = 'stock_movements'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    component_id: Mapped[int] = mapped_column(ForeignKey('components.id', ondelete='CASCADE'), index=True)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    resulting_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    component: Mapped['Component'] = relationship('Component', back_populates='stock_movements')
