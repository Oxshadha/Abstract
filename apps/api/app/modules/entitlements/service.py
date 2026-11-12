"""Entitlements (AGENTS rule 6): every plan-gated limit is read here, never hard-coded.

Until plans exist (spec 012) every user gets the defaults from settings (D87); spec 012 replaces
`limits_for` with a per-plan lookup without changing its callers.
"""

from uuid import UUID

from pydantic import BaseModel

from app.core.config import Settings


class Limits(BaseModel):
    fields_per_template: int
    custom_templates: int
    label_chars: int
    instruction_chars: int


def limits_for(settings: Settings, user_id: UUID) -> Limits:
    _ = user_id  # per-plan limits arrive with spec 012
    return Limits(
        fields_per_template=settings.template_max_fields,
        custom_templates=settings.template_max_custom,
        label_chars=60,
        instruction_chars=500,
    )
