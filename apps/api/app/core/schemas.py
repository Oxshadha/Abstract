"""Request-schema building blocks (spec 002 AC16, AC17, D75).

Every request body model subclasses StrictModel: unknown fields are rejected (no mass
assignment), strings are bounded. Free text uses CleanStr: Unicode NFC normalization and removal
of control characters (except newline and tab). Identity, org, ownership and role fields must
never appear in request schemas; they come from the verified token and the database.
"""

import re
import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

MAX_STRING_LENGTH = 10_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f​‪-‮⁦-⁩]")

# Field names the server derives itself and never accepts from a client (AC17).
FORBIDDEN_CLIENT_FIELDS = frozenset(
    {
        "org_id",
        "owner_id",
        "user_id",
        "tenant_id",
        "role",
        "platform_role",
        "created_by",
        "is_admin",
    }
)


def clean_text(value: str) -> str:
    """NFC-normalize and strip control and bidi-override characters (keeps \\n and \\t)."""
    return _CONTROL.sub("", unicodedata.normalize("NFC", value))


CleanStr = Annotated[str, AfterValidator(clean_text)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=MAX_STRING_LENGTH)
