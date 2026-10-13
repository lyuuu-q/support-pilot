from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from support_pilot.domain.enums import UserRole


class StrictAuthContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictAuthContract):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    # Browsers use cookie sessions; scripts and API clients may opt into a bearer token.
    session_mode: Literal["cookie", "token"] = "cookie"


class TokenResponse(StrictAuthContract):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class CurrentUserResponse(StrictAuthContract):
    id: UUID
    tenant_id: UUID | None
    email: EmailStr
    display_name: str
    role: UserRole


class LoginResponse(StrictAuthContract):
    user: CurrentUserResponse
    csrf_token: str
    expires_in: int
