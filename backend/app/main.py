from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from collections.abc import Generator
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import accounting, fees, security
from app.database import get_engine, get_session
from app.models import (
    Account,
    Child,
    DailyReport,
    AccountingEntry,
    CashOpening,
    Employee,
    FeeAuditLog,
    FeeCharge,
    FeePayment,
    SalaryLine,
    GuardianInvitation,
    LoginAttempt,
    PortalSession,
    RegistrationRequest,
    Role,
    TeacherContent,
    TeacherPost,
    parent_child_links,
    teacher_child_links,
)
logger = logging.getLogger(__name__)
FILE_RE = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|gif|mp4|webm)$")
CONTENT_TYPES = {
    ".pdf": ("document", "application/pdf", b"%PDF-"),
    ".jpg": ("image", "image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image", "image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image", "image/png", b"\x89PNG\r\n\x1a\n"),
    ".webp": ("image", "image/webp", b"RIFF"),
    ".mp4": ("video", "video/mp4", b"ftyp"),
    ".webm": ("video", "video/webm", b"\x1aE\xdf\xa3"),
}
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_OTHER_BYTES = 50 * 1024 * 1024
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".scr", ".msi", ".dll", ".js", ".mjs", ".vbs",
    ".ps1", ".jar", ".sh", ".apk", ".app", ".lnk", ".reg", ".hta", ".html", ".htm", ".svg",
}
MAX_PRIVATE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PRIVATE_VIDEO_BYTES = 25 * 1024 * 1024
MAX_TEACHER_CONTENT_BYTES = 250 * 1024 * 1024
MAX_REPORT_ATTACHMENTS = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
SESSION_TTL_SECONDS = 8 * 60 * 60
PORTAL_LOGIN_WINDOW_SECONDS = 15 * 60
PORTAL_LOGIN_MAX_FAILURES = 5
PASSWORD_HASHER = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash("dummy-password-used-for-timing-only")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,80}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-\s]{6,40}$")
REGISTRATION_CODE_TTL_HOURS = 7 * 24
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_ATTEMPT_LIMIT = 10


def new_registration_code() -> str:
    """Short one-time code like K7QM-4XD9 (no confusing 0/O/1/I characters)."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_invitation_code(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) > 20:
        return cleaned  # long codes issued by staff for a specific child
    return re.sub(r"[\s-]", "", cleaned).upper()


def client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
REGISTRATION_REQUESTS_PER_HOUR = 30
REGISTRATION_REQUESTS_PER_ADDRESS = 5
LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class GitHubError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class GitHubStore:
    def __init__(self) -> None:
        self.owner = os.getenv("GITHUB_OWNER", "Zahra-123hub")
        self.repo = os.getenv("GITHUB_REPO", "Zahra-Almadain")
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents"

    def require_token(self) -> None:
        if not self.token:
            raise HTTPException(503, "لم يتم إعداد اتصال GitHub على الخادم.")

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        raw: bool = False,
    ) -> httpx.Response:
        self.require_token()
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}/{path}",
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise GitHubError(504, "انتهت مهلة الاتصال بـ GitHub. حاول مرة أخرى.") from exc
        except httpx.RequestError as exc:
            raise GitHubError(502, "تعذّر الاتصال بـ GitHub من الخادم.") from exc
        if not response.is_success:
            if response.status_code == 401:
                message = "رمز GitHub المخزن على الخادم غير صالح أو منتهي."
            elif response.status_code == 403:
                message = "رمز GitHub يحتاج صلاحية Contents للقراءة والكتابة."
            elif response.status_code == 404:
                message = "لم يتم العثور على المستودع أو الملف في GitHub."
            else:
                message = "تعذّر إكمال العملية مع GitHub."
            raise GitHubError(response.status_code, message)
        return response

    async def get_content(self) -> tuple[dict[str, Any], str]:
        response = await self.request("GET", "content.json")
        try:
            item = response.json()
            decoded = base64.b64decode(item["content"]).decode("utf-8")
            data = json.loads(decoded)
        except (KeyError, ValueError, UnicodeDecodeError) as exc:
            raise GitHubError(502, "ملف content.json غير صالح أو تعذّر قراءته.") from exc
        if not isinstance(data, dict):
            raise GitHubError(502, "بنية ملف المحتوى غير صالحة.")
        data.setdefault("settings", {})
        data.setdefault("gallery", [])
        data.setdefault("news", [])
        return data, item["sha"]

    async def put_content(
        self, data: dict[str, Any], sha: str, message: str
    ) -> None:
        contents = base64.b64encode(
            json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
        ).decode("ascii")
        await self.request(
            "PUT",
            "content.json",
            {"message": message, "content": contents, "sha": sha},
        )

    async def put_file(self, name: str, contents: bytes, message: str) -> None:
        await self.request(
            "PUT",
            name,
            {
                "message": message,
                "content": base64.b64encode(contents).decode("ascii"),
            },
        )

    async def get_file(self, name: str) -> httpx.Response:
        return await self.request("GET", name, raw=True)

    async def delete_file(self, name: str) -> None:
        response = await self.request("GET", name)
        sha = response.json()["sha"]
        await self.request(
            "DELETE",
            name,
            {"message": f"حذف {name}", "sha": sha},
        )


store = GitHubStore()
# The public API documentation is switched off on the live server.
_LIVE = bool(os.getenv("RENDER"))
app = FastAPI(
    title="Zahrat Al-Madayn API",
    version="1.0.0",
    docs_url=None if _LIVE else "/docs",
    redoc_url=None if _LIVE else "/redoc",
    openapi_url=None if _LIVE else "/openapi.json",
)


@app.middleware("http")
async def security_headers(request: Any, call_next: Any) -> Response:
    """Headers that stop clickjacking, content sniffing and leaking of the address."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response
origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "https://zahra-123hub.github.io,http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class SettingsRequest(BaseModel):
    announce: str = ""
    phone: str = ""
    whatsapp: str = ""
    hours: str = ""
    facebook: str = ""
    instagram: str = ""
    email: str = ""
    hide_default_news: bool = Field(default=False, alias="hideDefaultNews")
    hide_default_gallery: bool = Field(default=False, alias="hideDefaultGallery")

    model_config = {"populate_by_name": True}


class PlatformLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class GuardianSignupRequest(BaseModel):
    invitation_code: str = Field(min_length=6, max_length=64)
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    preferred_language: str = Field(
        default="ar", min_length=2, max_length=35, pattern=LANGUAGE_RE.pattern
    )


class RegistrationRequestCreate(BaseModel):
    guardian_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254, pattern=EMAIL_RE.pattern)
    phone: str = Field(min_length=6, max_length=40, pattern=PHONE_RE.pattern)
    child_name: str = Field(min_length=2, max_length=120)
    child_birth_date: str = Field(default="", max_length=10, pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    relationship_to_child: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=1000)
    preferred_language: str = Field(
        default="ar", min_length=2, max_length=35, pattern=LANGUAGE_RE.pattern
    )
    # Bot traps: humans never fill the hidden field and need a few seconds to fill the form.
    website: str = Field(default="", max_length=200)
    form_age_ms: int | None = Field(default=None, ge=0, le=86_400_000)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=security.PASSWORD_MIN_LENGTH, max_length=256)


class RegistrationDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")


class ChildCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class InvitationCreateRequest(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=168)


class TeacherAssignmentRequest(BaseModel):
    teacher_id: uuid.UUID


class DailyReportRequest(BaseModel):
    child_id: uuid.UUID
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=3000)
    submit_for_review: bool = False


class DailyReportUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=3000)
    submit_for_review: bool = False


class ReportStatusRequest(BaseModel):
    status: str = Field(pattern="^(published|rejected|archived)$")


class PreferredLanguageRequest(BaseModel):
    language: str = Field(min_length=2, max_length=35, pattern=LANGUAGE_RE.pattern)


class TeacherAccountCreateRequest(BaseModel):
    role: str = Field(default="teacher", pattern="^(teacher|accountant|admin|parent)$")
    # Parents only: the child this parent account belongs to (more can be linked later in the children tab).
    child_id: uuid.UUID | None = None
    # Real name and job: saved as the staff member (employee) tied to this account.
    full_name: str = Field(default="", max_length=120)
    job_title: str = Field(default="", max_length=80)
    username: str = Field(min_length=3, max_length=80, pattern=USERNAME_RE.pattern)
    password: str = Field(min_length=12, max_length=256)
    preferred_language: str = Field(
        default="ar", min_length=2, max_length=35, pattern=LANGUAGE_RE.pattern
    )


class AccountApprovalRequest(BaseModel):
    status: str = Field(pattern="^(active|disabled)$")


MANAGED_ROLES = ("parent", "teacher", "accountant", "admin")


class AccountEditRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=80)
    full_name: str | None = Field(default=None, max_length=120)
    job_title: str | None = Field(default=None, max_length=80)
    # An account may hold several of these roles at once; other roles (manager) are untouched.
    roles: list[str] | None = Field(default=None, max_length=4)
    preferred_language: str | None = Field(
        default=None, min_length=2, max_length=35, pattern=LANGUAGE_RE.pattern
    )


class PasswordResetRequest(BaseModel):
    # Leave empty to let the server generate a strong password.
    password: str | None = Field(default=None, min_length=12, max_length=256)


class PlatformPrincipal:
    def __init__(self, account: Account, portal_session: PortalSession) -> None:
        self.account = account
        self.portal_session = portal_session


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def create_session_token(username: str, secret: str, now: int | None = None) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = _b64url(
        json.dumps(
            {"sub": username, "exp": issued_at + SESSION_TTL_SECONDS},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signature = _b64url(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_session_token(
    token: str, secret: str, now: int | None = None
) -> str | None:
    try:
        payload, signature = token.split(".", 1)
        expected = _b64url(
            hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        decoded = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        current_time = int(time.time()) if now is None else now
        if decoded["exp"] <= current_time:
            return None
        return decoded["sub"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def create_portal_session_token(
    account_id: uuid.UUID, token_id: str, secret: str, now: int | None = None
) -> str:
    issued_at = int(time.time()) if now is None else now
    payload = _b64url(
        json.dumps(
            {
                "sub": str(account_id),
                "sid": token_id,
                "typ": "portal",
                "exp": issued_at + SESSION_TTL_SECONDS,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signature = _b64url(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def verify_portal_session_token(
    token: str, secret: str, now: int | None = None
) -> tuple[uuid.UUID, str] | None:
    try:
        payload, signature = token.split(".", 1)
        expected = _b64url(
            hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        decoded = json.loads(
            base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        )
        current_time = int(time.time()) if now is None else now
        if (
            decoded.get("typ") != "portal"
            or not isinstance(decoded.get("sid"), str)
            or not isinstance(decoded.get("exp"), int)
            or decoded["exp"] <= current_time
        ):
            return None
        return uuid.UUID(decoded["sub"]), decoded["sid"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def optional_session() -> Generator[Session | None, None, None]:
    try:
        engine = get_engine()
    except RuntimeError:
        yield None
        return
    with Session(engine) as session:
        yield session


def require_admin(
    authorization: str | None = Header(default=None),
    session: Session | None = Depends(optional_session),
) -> str:
    """The server admin (env credentials) or any platform account holding the admin role."""
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise HTTPException(503, "لم يتم إعداد جلسات المسؤول على الخادم.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "سجّل الدخول إلى لوحة التحكم.")
    token = authorization[7:]
    username = verify_session_token(token, secret)
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    if username and hmac.compare_digest(username, admin_username):
        return username
    verified = verify_portal_session_token(token, secret)
    if verified is not None and session is not None:
        account_id, token_id = verified
        portal_session = session.scalar(
            select(PortalSession).where(
                PortalSession.account_id == account_id,
                PortalSession.token_id == token_id,
                PortalSession.revoked_at.is_(None),
                PortalSession.expires_at > func.now(),
            )
        )
        account = session.scalar(
            select(Account)
            .options(selectinload(Account.roles))
            .where(Account.id == account_id, Account.is_active.is_(True), Account.approval_status == "active")
        )
        if portal_session is not None and account is not None and any(r.name == "admin" for r in account.roles):
            return account.username
    raise HTTPException(401, "انتهت جلسة الدخول. سجّل الدخول مرة أخرى.")


def require_publisher(
    authorization: str | None = Header(default=None),
    session: Session | None = Depends(optional_session),
) -> str:
    """Website content (gallery, news) may be managed by the admin or by teachers."""
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise HTTPException(503, "لم يتم إعداد جلسات المسؤول على الخادم.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "سجّل الدخول إلى لوحة التحكم.")
    token = authorization[7:]
    username = verify_session_token(token, secret)
    if username and hmac.compare_digest(username, os.getenv("ADMIN_USERNAME", "admin")):
        return username
    verified = verify_portal_session_token(token, secret)
    if verified is None:
        raise HTTPException(401, "انتهت جلسة الدخول. سجّل الدخول مرة أخرى.")
    account_id, token_id = verified
    if session is None:
        raise HTTPException(503, "Platform storage is not configured on the server.")
    portal_session = session.scalar(
        select(PortalSession).where(
            PortalSession.account_id == account_id,
            PortalSession.token_id == token_id,
            PortalSession.revoked_at.is_(None),
            PortalSession.expires_at > func.now(),
        )
    )
    account = session.scalar(
        select(Account)
        .options(selectinload(Account.roles))
        .where(
            Account.id == account_id,
            Account.is_active.is_(True),
            Account.approval_status == "active",
        )
    )
    roles = {role.name for role in account.roles} if account is not None else set()
    if portal_session is None or account is None or not roles & {"teacher", "manager", "admin"}:
        raise HTTPException(401, "انتهت جلسة الدخول. سجّل الدخول مرة أخرى.")
    return account.username


def require_fees_user(
    authorization: str | None = Header(default=None),
    session: Session | None = Depends(optional_session),
) -> fees.FeesActor:
    """Fees are only for accountants and admins; everyone else gets 403."""
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise HTTPException(503, "لم يتم إعداد جلسات المسؤول على الخادم.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "سجّل الدخول أولاً.")
    token = authorization[7:]
    username = verify_session_token(token, secret)
    if username and hmac.compare_digest(username, os.getenv("ADMIN_USERNAME", "admin")):
        return fees.FeesActor(None, username, "admin")
    verified = verify_portal_session_token(token, secret)
    if verified is None:
        raise HTTPException(401, "انتهت جلسة الدخول. سجّل الدخول مرة أخرى.")
    if session is None:
        raise HTTPException(503, "Platform storage is not configured on the server.")
    account_id, token_id = verified
    portal_session = session.scalar(
        select(PortalSession).where(
            PortalSession.account_id == account_id,
            PortalSession.token_id == token_id,
            PortalSession.revoked_at.is_(None),
            PortalSession.expires_at > func.now(),
        )
    )
    account = session.scalar(
        select(Account)
        .options(selectinload(Account.roles))
        .where(
            Account.id == account_id,
            Account.is_active.is_(True),
            Account.approval_status == "active",
        )
    )
    if portal_session is None or account is None:
        raise HTTPException(401, "انتهت جلسة الدخول. سجّل الدخول مرة أخرى.")
    roles = {role.name for role in account.roles}
    if "accountant" in roles:
        return fees.FeesActor(account.id, account.username, "accountant")
    if "admin" in roles:
        return fees.FeesActor(account.id, account.username, "admin")
    raise HTTPException(403, "ليس لديك صلاحية الوصول إلى الاشتراكات والرسوم.")


def get_platform_principal(
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> PlatformPrincipal:
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise HTTPException(503, "Platform sessions are not configured on the server.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to the platform.")
    verified = verify_portal_session_token(authorization[7:], secret)
    if verified is None:
        raise HTTPException(401, "Your platform session expired. Sign in again.")
    account_id, token_id = verified
    portal_session = session.scalar(
        select(PortalSession).where(
            PortalSession.account_id == account_id,
            PortalSession.token_id == token_id,
            PortalSession.revoked_at.is_(None),
            PortalSession.expires_at > func.now(),
        )
    )
    account = session.scalar(
        select(Account)
        .options(selectinload(Account.roles).selectinload(Role.permissions))
        .where(
            Account.id == account_id,
            Account.is_active.is_(True),
            Account.approval_status == "active",
        )
    )
    if portal_session is None or account is None:
        raise HTTPException(401, "Your platform session is no longer valid.")
    return PlatformPrincipal(account, portal_session)


def require_platform_role(role_name: str):
    def check_role(
        principal: PlatformPrincipal = Depends(get_platform_principal),
    ) -> PlatformPrincipal:
        if role_name not in {role.name for role in principal.account.roles}:
            raise HTTPException(403, "You do not have permission to perform this action.")
        return principal

    return check_role


def require_any_platform_role(*role_names: str):
    def check_role(
        principal: PlatformPrincipal = Depends(get_platform_principal),
    ) -> PlatformPrincipal:
        if not set(role_names).intersection(
            {role.name for role in principal.account.roles}
        ):
            raise HTTPException(403, "You do not have permission to perform this action.")
        return principal

    return check_role


def portal_session_result(
    account: Account, session: Session, secret: str
) -> dict[str, Any]:
    token_id = secrets.token_hex(16)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
    session.add(
        PortalSession(
            token_id=token_id,
            account_id=account.id,
            expires_at=expires_at,
        )
    )
    return {
        "access_token": create_portal_session_token(
            account.id, token_id, secret
        ),
        "token_type": "bearer",
        "expires_in": SESSION_TTL_SECONDS,
    }


async def update_content(mutator: Any, message: str) -> Any:
    for _ in range(3):
        data, sha = await store.get_content()
        result = mutator(data)
        try:
            await store.put_content(data, sha, message)
            return result
        except GitHubError as exc:
            if exc.status_code not in (409, 422):
                raise
    raise HTTPException(409, "تعارضت تعديلات متزامنة. أعد المحاولة.")


def identify_file(contents: bytes) -> tuple[str, str]:
    if contents.startswith(b"\xff\xd8\xff"):
        return "jpg", "image"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image"
    if contents.startswith((b"GIF87a", b"GIF89a")):
        return "gif", "image"
    if len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP":
        return "webp", "image"
    if len(contents) >= 12 and contents[4:8] == b"ftyp":
        return "mp4", "video"
    if contents.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm", "video"
    raise HTTPException(400, "نوع الملف غير مدعوم.")


async def upload_asset(file: UploadFile, kind: str) -> str:
    limit = MAX_VIDEO_BYTES if kind == "video" else MAX_IMAGE_BYTES
    contents = await file.read(limit + 1)
    if len(contents) > limit:
        raise HTTPException(
            413,
            "حجم الملف يتجاوز الحد المسموح (10 ميغابايت للصورة و25 ميغابايت للفيديو).",
        )
    extension, actual_kind = identify_file(contents)
    if actual_kind != kind:
        raise HTTPException(400, "نوع الملف لا يطابق القسم المحدد.")
    name = f"{secrets.token_hex(16)}.{extension}"
    await store.put_file(name, contents, f"رفع {name}")
    return name


def media_type(name: str) -> str:
    return {
        "jpg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "mp4": "video/mp4",
        "webm": "video/webm",
    }[name.rsplit(".", 1)[1]]


@app.exception_handler(GitHubError)
async def github_error_handler(_request: Any, exc: GitHubError) -> Response:
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code if exc.status_code < 500 else 502,
        content={"detail": exc.message},
    )


app.include_router(fees.build_router(require_fees_user))
app.include_router(accounting.build_router(require_fees_user))


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


ADMIN_LOGIN_LIMIT = 8
ADMIN_THROTTLE = security.MemoryThrottle()


def reject_weak_live_admin_password(password: str) -> None:
    """On the live server (Render) a short ADMIN_PASSWORD is refused instead of silently accepted."""
    if os.getenv("RENDER") and len(password) < security.PASSWORD_MIN_LENGTH:
        raise HTTPException(
            503, "ADMIN_PASSWORD is too weak. Set a password with at least 12 characters on the server."
        )


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, Any]:
    expected_username = os.getenv("ADMIN_USERNAME", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "")
    session_secret = os.getenv("SESSION_SECRET", "")
    if not expected_password or not session_secret:
        raise HTTPException(503, "لم يتم إعداد بيانات دخول المسؤول على الخادم.")
    reject_weak_live_admin_password(expected_password)
    throttle_id = "admin-login:" + client_address(request)
    if ADMIN_THROTTLE.blocked(throttle_id, ADMIN_LOGIN_LIMIT, PORTAL_LOGIN_WINDOW_SECONDS):
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")
    valid_username = secrets.compare_digest(payload.username, expected_username)
    valid_password = secrets.compare_digest(payload.password, expected_password)
    if not (valid_username and valid_password):
        ADMIN_THROTTLE.record(throttle_id)
        raise HTTPException(401, "اسم المستخدم أو كلمة المرور غير صحيحة.")
    return {
        "access_token": create_session_token(payload.username, session_secret),
        "token_type": "bearer",
        "expires_in": SESSION_TTL_SECONDS,
    }


@app.get("/api/content")
async def public_content() -> dict[str, Any]:
    data, _sha = await store.get_content()
    return data


@app.get("/api/assets/{name}")
async def public_asset(name: str) -> Response:
    if not FILE_RE.fullmatch(name):
        raise HTTPException(404, "الملف غير موجود.")
    response = await store.get_file(name)
    return Response(
        content=response.content,
        media_type=media_type(name),
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.get("/api/admin/content")
async def admin_content(_username: str = Depends(require_publisher)) -> dict[str, Any]:
    data, _sha = await store.get_content()
    return data


@app.post("/api/admin/gallery")
async def add_gallery_item(
    file: UploadFile = File(...),
    kind: str = Form(...),
    caption: str = Form(default=""),
    _username: str = Depends(require_publisher),
) -> dict[str, Any]:
    if kind not in ("image", "video"):
        raise HTTPException(400, "نوع العنصر غير صالح.")
    name = await upload_asset(file, kind)
    item = {
        "id": secrets.token_hex(8),
        "kind": kind,
        "asset": name,
        "caption": caption.strip()[:120],
        "ts": int(time.time() * 1000),
    }
    await update_content(lambda data: data["gallery"].append(item), "إضافة إلى المعرض")
    return item


@app.patch("/api/admin/gallery/{item_id}")
async def update_gallery_caption(
    item_id: str,
    payload: dict[str, Any],
    _username: str = Depends(require_publisher),
) -> dict[str, bool]:
    caption = str(payload.get("caption", "")).strip()[:120]

    def update(data: dict[str, Any]) -> None:
        item = next((entry for entry in data["gallery"] if entry["id"] == item_id), None)
        if item is None:
            raise HTTPException(404, "عنصر المعرض غير موجود.")
        item["caption"] = caption

    await update_content(update, "تعديل تعليق")
    return {}


@app.delete("/api/admin/gallery/{item_id}")
async def delete_gallery_item(
    item_id: str, _username: str = Depends(require_publisher)
) -> dict[str, bool]:
    removed: dict[str, Any] = {}

    def update(data: dict[str, Any]) -> None:
        item = next((entry for entry in data["gallery"] if entry["id"] == item_id), None)
        if item is None:
            raise HTTPException(404, "عنصر المعرض غير موجود.")
        removed.update(item)
        data["gallery"] = [entry for entry in data["gallery"] if entry["id"] != item_id]

    await update_content(update, "حذف من المعرض")
    if FILE_RE.fullmatch(str(removed.get("asset", ""))):
        await store.delete_file(removed["asset"])
    return {}


async def news_fields(
    tag: str, title: str, text: str
) -> dict[str, str]:
    title = title.strip()[:120]
    text = text.strip()[:1500]
    if not title or not text:
        raise HTTPException(400, "العنوان والنص مطلوبان.")
    return {"tag": tag.strip()[:30] or "خبر", "title": title, "text": text}


@app.post("/api/admin/news")
async def add_news(
    tag: str = Form(default="خبر"),
    title: str = Form(...),
    text: str = Form(...),
    file: UploadFile | None = File(default=None),
    _username: str = Depends(require_publisher),
) -> dict[str, Any]:
    fields = await news_fields(tag, title, text)
    asset = await upload_asset(file, "image") if file and file.filename else ""
    item = {
        "id": secrets.token_hex(8),
        "asset": asset,
        "ts": int(time.time() * 1000),
        **fields,
    }
    await update_content(lambda data: data["news"].append(item), "خبر جديد")
    return item


@app.post("/api/admin/news/{item_id}")
async def update_news(
    item_id: str,
    tag: str = Form(default="خبر"),
    title: str = Form(...),
    text: str = Form(...),
    file: UploadFile | None = File(default=None),
    remove_image: str = Form(default="0"),
    _username: str = Depends(require_publisher),
) -> dict[str, bool]:
    fields = await news_fields(tag, title, text)
    new_asset = await upload_asset(file, "image") if file and file.filename else None
    removed: dict[str, Any] = {}

    def update(data: dict[str, Any]) -> None:
        item = next((entry for entry in data["news"] if entry["id"] == item_id), None)
        if item is None:
            raise HTTPException(404, "الخبر غير موجود.")
        removed["asset"] = item.get("asset", "")
        item.update(fields)
        if new_asset is not None:
            item["asset"] = new_asset
        elif remove_image == "1":
            item["asset"] = ""

    await update_content(update, "تعديل خبر")
    if removed.get("asset") and (new_asset is not None or remove_image == "1"):
        await store.delete_file(removed["asset"])
    return {}


@app.delete("/api/admin/news/{item_id}")
async def delete_news(
    item_id: str, _username: str = Depends(require_publisher)
) -> dict[str, bool]:
    removed: dict[str, Any] = {}

    def update(data: dict[str, Any]) -> None:
        item = next((entry for entry in data["news"] if entry["id"] == item_id), None)
        if item is None:
            raise HTTPException(404, "الخبر غير موجود.")
        removed.update(item)
        data["news"] = [entry for entry in data["news"] if entry["id"] != item_id]

    await update_content(update, "حذف خبر")
    if FILE_RE.fullmatch(str(removed.get("asset", ""))):
        await store.delete_file(removed["asset"])
    return {}


@app.put("/api/admin/settings")
async def update_settings(
    payload: SettingsRequest, _username: str = Depends(require_admin)
) -> dict[str, Any]:
    settings = {
        "announce": payload.announce.strip()[:200],
        "phone": payload.phone.strip()[:300],
        "whatsapp": re.sub(r"\D", "", payload.whatsapp),
        "hours": payload.hours.strip()[:200],
        "facebook": payload.facebook.strip()[:300],
        "instagram": payload.instagram.strip()[:300],
        "email": payload.email.strip()[:300],
        "hideDefaultNews": payload.hide_default_news,
        "hideDefaultGallery": payload.hide_default_gallery,
    }
    if settings["whatsapp"] and not 8 <= len(settings["whatsapp"]) <= 15:
        raise HTTPException(400, "رقم الواتساب غير صالح.")
    for key in ("facebook", "instagram"):
        if settings[key] and not settings[key].lower().startswith("https://"):
            raise HTTPException(400, "يجب أن يبدأ الرابط بـ https://")
    await update_content(lambda data: data.update(settings=settings), "تعديل الإعدادات")
    return settings


def admin_account_data(account: Account) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "username": account.username,
        "roles": sorted(role.name for role in account.roles),
        "approval_status": account.approval_status,
        "preferred_language": account.preferred_language,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


@app.get("/api/admin/platform/accounts")
def list_platform_accounts(
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    accounts = session.scalars(
        select(Account)
        .options(selectinload(Account.roles))
        .join(Account.roles)
        .where(Role.name.in_(MANAGED_ROLES))
        .order_by(Account.created_at.desc())
    ).unique().all()
    details = {
        item.account_id: item
        for item in session.scalars(
            select(RegistrationRequest).where(
                RegistrationRequest.account_id.in_([account.id for account in accounts])
            )
        )
    }
    people = {
        person.account_id: person
        for person in session.scalars(
            select(Employee).where(Employee.account_id.in_([account.id for account in accounts]))
        )
    }
    result = []
    for account in accounts:
        data = admin_account_data(account)
        person = people.get(account.id)
        data.update(full_name=person.name if person else "", job_title=person.job_title if person else "")
        request_item = details.get(account.id)
        if request_item is not None:
            data.update(
                guardian_name=request_item.guardian_name,
                email=request_item.email,
                phone=request_item.phone,
                child_name=request_item.child_name,
            )
        result.append(data)
    return result


@app.post("/api/admin/platform/teacher-accounts", status_code=201)
def create_platform_teacher_account(
    payload: TeacherAccountCreateRequest,
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    username = payload.username.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(422, "Username contains unsupported characters.")
    if session.scalar(select(Account.id).where(Account.username == username)) is not None:
        raise HTTPException(409, "That username is already in use.")
    weak = security.password_problem(payload.password, username)
    if weak:
        raise HTTPException(422, weak)
    teacher_role = session.scalar(select(Role).where(Role.name == payload.role))
    if teacher_role is None:
        raise HTTPException(503, "Platform roles are not initialized. Run database migrations.")
    linked_child = None
    if payload.role == "parent" and payload.child_id is not None:
        linked_child = session.scalar(select(Child).where(Child.id == payload.child_id, Child.is_active.is_(True)))
        if linked_child is None:
            raise HTTPException(404, "Child profile not found.")
    account = Account(
        username=username,
        password_hash=PASSWORD_HASHER.hash(payload.password),
        preferred_language=payload.preferred_language,
        is_active=True,
        approval_status="active",
        roles=[teacher_role],
    )
    session.add(account)
    try:
        session.flush()
        if payload.role != "parent":  # staff names are saved as employees; parents are not staff
            attach_person_to_account(session, account, payload.full_name, payload.job_title)
        if linked_child is not None:
            session.execute(
                parent_child_links.insert().values(
                    account_id=account.id, child_id=linked_child.id, confirmed_at=datetime.now(timezone.utc)
                )
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "That username is already in use.") from exc
    session.refresh(account)
    data = admin_account_data(account)
    person = employee_of_account(session, account.id)
    data.update(full_name=person.name if person else "", job_title=person.job_title if person else "")
    return data


@app.patch("/api/admin/platform/accounts/{account_id}/status")
def update_platform_account_status(
    account_id: uuid.UUID,
    payload: AccountApprovalRequest,
    response: Response,
    acting_username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    account = session.scalar(
        select(Account)
        .options(selectinload(Account.roles))
        .where(Account.id == account_id)
        .with_for_update()
    )
    if account is None or not set(MANAGED_ROLES).intersection(role.name for role in account.roles):
        raise HTTPException(404, "Parent or teacher account not found.")
    if payload.status != "active" and account.username == acting_username:
        raise HTTPException(409, "لا يمكنك تعطيل حسابك الخاص.")
    account.approval_status = payload.status
    account.is_active = payload.status == "active"
    if payload.status != "active":
        session.execute(
            update(PortalSession)
            .where(
                PortalSession.account_id == account.id,
                PortalSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
    session.commit()
    session.refresh(account)
    return admin_account_data(account)


PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def employee_of_account(session: Session, account_id: uuid.UUID) -> Employee | None:
    return session.scalar(select(Employee).where(Employee.account_id == account_id))


def attach_person_to_account(
    session: Session, account: Account, full_name: str, job_title: str | None
) -> None:
    """Saves the person's name as an employee tied to the account (one person, one account)."""
    name = full_name.strip()
    if not name:
        return
    employee = employee_of_account(session, account.id)
    other = session.scalar(
        select(Employee).where(
            func.lower(Employee.name) == name.lower(),
            Employee.id != (employee.id if employee else uuid.UUID(int=0)),
        ).order_by(Employee.is_active.desc(), Employee.created_at)
    )
    if other is not None and not other.is_active and employee is not None:
        other = None  # a removed person with the same name does not block this one
    if other is not None:
        if other.account_id is not None and other.account_id != account.id:
            raise HTTPException(409, "يوجد موظف بهذا الاسم مرتبط بحساب آخر.")
        if employee is None:
            employee = other  # an unlinked person saved earlier: tie that one to the account
            employee.account_id = account.id
        else:
            raise HTTPException(409, "يوجد موظف بهذا الاسم.")
    if employee is None:
        employee = Employee(name=name, job_title=(job_title or "").strip(), account_id=account.id)
        session.add(employee)
    else:
        employee.name = name
        employee.is_active = True
    if job_title is not None:
        employee.job_title = job_title.strip()


def managed_account(session: Session, account_id: uuid.UUID) -> Account:
    account = session.scalar(
        select(Account)
        .options(selectinload(Account.roles))
        .where(Account.id == account_id)
        .with_for_update()
    )
    if account is None or not set(MANAGED_ROLES).intersection(role.name for role in account.roles):
        raise HTTPException(404, "الحساب غير موجود.")
    return account


def revoke_sessions(session: Session, account_id: uuid.UUID) -> None:
    session.execute(
        update(PortalSession)
        .where(PortalSession.account_id == account_id, PortalSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


@app.patch("/api/admin/platform/accounts/{account_id}")
def edit_platform_account(
    account_id: uuid.UUID,
    payload: AccountEditRequest,
    response: Response,
    acting_username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Change the username or language of a parent, teacher or accountant account."""
    response.headers["Cache-Control"] = "no-store"
    account = managed_account(session, account_id)
    if payload.username is not None:
        username = payload.username.strip().lower()
        if not USERNAME_RE.fullmatch(username):
            raise HTTPException(422, "اسم المستخدم يحتوي على أحرف غير مدعومة.")
        if username != account.username:
            taken = session.scalar(
                select(Account.id).where(Account.username == username, Account.id != account.id)
            )
            if taken is not None:
                raise HTTPException(409, "اسم المستخدم مستخدم بالفعل.")
            account.username = username
            revoke_sessions(session, account.id)  # the old name is no longer valid for open sessions
    if payload.preferred_language is not None:
        account.preferred_language = payload.preferred_language
    if payload.full_name is not None and payload.full_name.strip():
        attach_person_to_account(session, account, payload.full_name, payload.job_title)
    elif payload.job_title is not None:
        person = employee_of_account(session, account.id)
        if person is not None:
            person.job_title = payload.job_title.strip()
    if payload.roles is not None:
        wanted = set(payload.roles)
        if not wanted or not wanted <= set(MANAGED_ROLES):
            raise HTTPException(422, "اختر دوراً واحداً على الأقل من: مدير، معلمة، محاسب، ولي أمر.")
        if account.username == acting_username and "admin" not in wanted:
            raise HTTPException(409, "لا يمكنك إزالة دور المدير عن حسابك الخاص.")
        found = {r.name: r for r in session.scalars(select(Role).where(Role.name.in_(MANAGED_ROLES)))}
        if wanted - set(found):
            raise HTTPException(503, "Platform roles are not initialized. Run database migrations.")
        kept = [role for role in account.roles if role.name not in MANAGED_ROLES]
        account.roles = kept + [found[name] for name in sorted(wanted)]
    session.commit()
    session.refresh(account)
    return admin_account_data(account)


@app.post("/api/admin/platform/accounts/{account_id}/reset-password")
def reset_platform_account_password(
    account_id: uuid.UUID,
    payload: PasswordResetRequest,
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Set a new password (given or generated). Existing passwords can never be read: they are
    stored as one-way hashes. The new password is returned once and is not stored in clear."""
    response.headers["Cache-Control"] = "no-store"
    account = managed_account(session, account_id)
    if payload.password:
        weak = security.password_problem(payload.password, account.username)
        if weak:
            raise HTTPException(422, weak)
    password = payload.password or "".join(
        secrets.choice(PASSWORD_ALPHABET) for _ in range(14)
    )
    account.password_hash = PASSWORD_HASHER.hash(password)
    revoke_sessions(session, account.id)
    session.execute(
        delete(LoginAttempt).where(
            LoginAttempt.username_hash
            == hmac.new(
                os.getenv("SESSION_SECRET", "").encode(), account.username.encode(), hashlib.sha256
            ).hexdigest()
        )
    )
    session.commit()
    return {"username": account.username, "password": password, "generated": payload.password is None}


@app.post("/api/platform/auth/login")
def platform_login(
    payload: PlatformLoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise HTTPException(503, "Platform sessions are not configured on the server.")

    username = payload.username.strip().lower()
    username_hash = hmac.new(
        secret.encode(), username.encode(), hashlib.sha256
    ).hexdigest()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=PORTAL_LOGIN_WINDOW_SECONDS)
    failures = session.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.username_hash == username_hash,
            LoginAttempt.attempted_at >= cutoff,
        )
    )
    if failures is not None and failures >= PORTAL_LOGIN_MAX_FAILURES:
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")

    session.execute(
        delete(LoginAttempt).where(
            LoginAttempt.attempted_at < now - timedelta(days=1)
        )
    )
    session.execute(
        delete(PortalSession).where(PortalSession.expires_at < now)
    )
    account = session.scalar(
        select(Account)
        .options(selectinload(Account.roles).selectinload(Role.permissions))
        .where(Account.username == username)
    )
    password_hash = account.password_hash if account is not None else DUMMY_PASSWORD_HASH
    password_matches = PASSWORD_HASHER.verify(payload.password, password_hash)
    if account is None or not password_matches:
        session.add(LoginAttempt(username_hash=username_hash, attempted_at=now))
        session.commit()
        raise HTTPException(401, "Incorrect username or password.")

    session.execute(
        delete(LoginAttempt).where(LoginAttempt.username_hash == username_hash)
    )
    if account.approval_status == "pending":
        session.commit()
        raise HTTPException(403, "Your account is awaiting administrator approval.")
    if account.approval_status != "active" or not account.is_active:
        session.commit()
        raise HTTPException(403, "Your account has been disabled. Contact the kindergarten.")
    result = portal_session_result(account, session, secret)
    session.commit()
    return result


class FinanceResetRequest(BaseModel):
    confirm: str = Field(max_length=20)


@app.post("/api/admin/accounting/reset")
def reset_financial_data(
    payload: FinanceResetRequest,
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    """Admin only: wipes every fee, payment, payroll line and sheet row so all totals start at 0.
    Children, staff names and accounts stay. Needs the confirmation word."""
    response.headers["Cache-Control"] = "no-store"
    if payload.confirm.strip() != "RESET":
        raise HTTPException(422, "اكتب كلمة RESET للتأكيد.")
    counts = {
        "payments": session.execute(delete(FeePayment)).rowcount or 0,
        "fees": session.execute(delete(FeeCharge)).rowcount or 0,
        "salaries": session.execute(delete(SalaryLine)).rowcount or 0,
        "sheet_rows": session.execute(delete(AccountingEntry)).rowcount or 0,
        "cash": session.execute(delete(CashOpening)).rowcount or 0,
    }
    session.add(
        FeeAuditLog(actor_name="admin", action="finance.reset", entity_id="all", details=str(counts)[:1000])
    )
    session.commit()
    return counts


@app.post("/api/auth/entry")
def unified_login(
    payload: PlatformLoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Single sign-in: the account's role decides which portal the user lands on.

    Wrong passwords are throttled per user name (in platform_login) and per address (here),
    for platform accounts and for the admin alike."""
    response.headers["Cache-Control"] = "no-store"
    secret = os.getenv("SESSION_SECRET", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    address_key = security.throttle_key(secret or "unset", "signin-ip", client_address(request))
    if security.failures_since(session, address_key, PORTAL_LOGIN_WINDOW_SECONDS) >= PORTAL_LOGIN_MAX_FAILURES * 4:
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")
    name_key = security.throttle_key(secret or "unset", "signin-name", payload.username.strip().lower())
    if secret and admin_password and security.failures_since(session, name_key, PORTAL_LOGIN_WINDOW_SECONDS) >= PORTAL_LOGIN_MAX_FAILURES:
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")
    if secret and admin_password:
        reject_weak_live_admin_password(admin_password)
        same_user = secrets.compare_digest(
            payload.username.strip(), os.getenv("ADMIN_USERNAME", "admin")
        )
        same_password = secrets.compare_digest(payload.password, admin_password)
        if same_user and same_password:
            return {
                "role": "admin",
                "portals": ["admin"],
                "access_token": create_session_token(payload.username.strip(), secret),
                "token_type": "bearer",
                "expires_in": SESSION_TTL_SECONDS,
            }
    try:
        result = platform_login(payload, response, session)
    except HTTPException as exc:
        if exc.status_code == 401:
            security.record_attempt(session, address_key)
            security.record_attempt(session, name_key)
            session.commit()
        raise
    account = session.scalar(
        select(Account)
        .options(selectinload(Account.roles))
        .where(Account.username == payload.username.strip().lower())
    )
    names = {role.name for role in account.roles} if account is not None else set()
    portals = []
    if "admin" in names:
        portals.append("admin")
    if names & {"teacher", "manager"}:
        portals.append("teacher")
    if "accountant" in names:
        portals.append("accountant")
    if "parent" in names:
        portals.append("parent")
    if not portals:
        raise HTTPException(403, "You do not have permission to perform this action.")
    # One role: go straight to its portal. Several roles: the client lets the user choose.
    result["role"] = portals[0]
    result["portals"] = portals
    return result


@app.post("/api/platform/auth/redeem-invitation", status_code=202)
def redeem_guardian_invitation(
    payload: GuardianSignupRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise HTTPException(503, "Platform sessions are not configured on the server.")
    username = payload.username.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(422, "Username contains unsupported characters.")
    weak = security.password_problem(payload.password, username)
    if weak:
        raise HTTPException(422, weak)
    code = normalize_invitation_code(payload.invitation_code)
    token_hash = hashlib.sha256(code.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    attempt_key = hmac.new(
        secret.encode(), ("redeem:" + client_address(request)).encode(), hashlib.sha256
    ).hexdigest()
    recent_failures = session.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.username_hash == attempt_key,
            LoginAttempt.attempted_at >= now - timedelta(seconds=PORTAL_LOGIN_WINDOW_SECONDS),
        )
    )
    if recent_failures is not None and recent_failures >= CODE_ATTEMPT_LIMIT:
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")
    invitation = session.scalar(
        select(GuardianInvitation)
        .where(
            GuardianInvitation.token_hash == token_hash,
            GuardianInvitation.redeemed_at.is_(None),
            GuardianInvitation.expires_at > now,
        )
        .with_for_update()
    )
    if invitation is None:
        session.add(LoginAttempt(username_hash=attempt_key, attempted_at=now))
        session.commit()
        raise HTTPException(400, "The invitation is invalid, expired, or already used.")
    if session.scalar(select(Account.id).where(Account.username == username)) is not None:
        raise HTTPException(409, "That username is already in use.")
    parent_role = session.scalar(select(Role).where(Role.name == "parent"))
    if parent_role is None:
        raise HTTPException(503, "Platform roles are not initialized. Run database migrations.")

    approved_in_advance = invitation.auto_approve
    account = Account(
        username=username,
        password_hash=PASSWORD_HASHER.hash(payload.password),
        preferred_language=payload.preferred_language,
        is_active=approved_in_advance,
        approval_status="active" if approved_in_advance else "pending",
        roles=[parent_role],
    )
    session.add(account)
    try:
        session.flush()
        session.execute(
            parent_child_links.insert().values(
                account_id=account.id,
                child_id=invitation.child_id,
                confirmed_at=now,
            )
        )
        invitation.redeemed_at = now
        linked_request = session.scalar(
            select(RegistrationRequest).where(
                RegistrationRequest.invitation_id == invitation.id
            )
        )
        if linked_request is not None:
            linked_request.account_id = account.id
            linked_request.registered_at = now
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "The invitation could not be redeemed.") from exc
    return {
        "account_id": str(account.id),
        "approval_status": account.approval_status,
        "message": (
            "Your account is ready. You can sign in now."
            if approved_in_advance
            else "Your account is awaiting administrator approval."
        ),
    }


def registration_request_data(item: RegistrationRequest) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "guardian_name": item.guardian_name,
        "email": item.email,
        "phone": item.phone,
        "child_name": item.child_name,
        "child_birth_date": item.child_birth_date,
        "relationship_to_child": item.relationship_to_child,
        "notes": item.notes,
        "status": item.status,
        "email_sent": item.email_sent,
        "registered": item.account_id is not None,
        "registered_at": item.registered_at.isoformat() if item.registered_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
    }


def send_registration_code_email(item: RegistrationRequest, code: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    if not host or not sender:
        return False
    base_url = os.getenv(
        "PORTAL_BASE_URL", "https://zahra-123hub.github.io/Zahra-Almadain"
    ).rstrip("/")
    link = f"{base_url}/login/?code={quote(code)}"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = item.email
    message["Subject"] = "روضة زهرة المدائن – تمت الموافقة على طلبك / Your request was approved"
    message.set_content(
        f"مرحباً {item.guardian_name}،\n"
        "تمت الموافقة على طلب التسجيل. أكملي/أكمل إنشاء الحساب عبر الرابط التالي "
        f"(صالح لمرة واحدة ولمدة 7 أيام):\n{link}\n\nرمز التسجيل: {code}\n\n"
        f"Hello {item.guardian_name},\n"
        "Your registration request was approved. Finish creating your account with the "
        f"one-time link (valid for 7 days):\n{link}\nRegistration code: {code}\n"
    )
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
            smtp.starttls()
            user = os.getenv("SMTP_USER", "")
            if user:
                smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
        return True
    except (OSError, ValueError, smtplib.SMTPException):
        logger.exception("Could not send registration code email")
        return False


@app.post("/api/platform/registration-requests", status_code=202)
def create_registration_request(
    payload: RegistrationRequestCreate,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    received = {"message": "Your request was received. The kindergarten will review it."}
    # Bots fill hidden fields and submit within a moment: answer as if it worked, store nothing.
    if payload.website.strip() or (payload.form_age_ms is not None and payload.form_age_ms < 2500):
        return received
    secret = os.getenv("SESSION_SECRET", "") or "unset"
    address_key = security.throttle_key(secret, "registration-ip", client_address(request))
    if security.failures_since(session, address_key, 3600) >= REGISTRATION_REQUESTS_PER_ADDRESS:
        raise HTTPException(429, "Too many requests. Try again later.")
    security.record_attempt(session, address_key)
    email = payload.email.strip().lower()
    recent = session.scalar(
        select(func.count())
        .select_from(RegistrationRequest)
        .where(
            RegistrationRequest.created_at
            >= datetime.now(timezone.utc) - timedelta(hours=1)
        )
    )
    if recent is not None and recent >= REGISTRATION_REQUESTS_PER_HOUR:
        raise HTTPException(429, "Too many requests. Try again later.")
    if (
        session.scalar(
            select(RegistrationRequest.id).where(
                RegistrationRequest.email == email,
                RegistrationRequest.status == "pending",
            )
        )
        is not None
    ):
        raise HTTPException(409, "A request for this email is already awaiting review.")
    session.add(
        RegistrationRequest(
            guardian_name=payload.guardian_name.strip(),
            email=email,
            phone=payload.phone.strip(),
            child_name=payload.child_name.strip(),
            child_birth_date=payload.child_birth_date,
            relationship_to_child=payload.relationship_to_child.strip(),
            notes=payload.notes.strip(),
            preferred_language=payload.preferred_language,
        )
    )
    session.commit()
    return {"message": "Your request was received. The kindergarten will review it."}


@app.get("/api/admin/platform/registration-requests")
def list_registration_requests(
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    items = session.scalars(
        select(RegistrationRequest)
        .order_by(RegistrationRequest.created_at.desc())
        .limit(200)
    ).all()
    return [registration_request_data(item) for item in items]


def locked_registration_request(session: Session, request_id: uuid.UUID) -> RegistrationRequest:
    item = session.scalar(
        select(RegistrationRequest)
        .where(RegistrationRequest.id == request_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Registration request not found.")
    return item


@app.patch("/api/admin/platform/registration-requests/{request_id}")
def edit_registration_request(
    request_id: uuid.UUID,
    payload: RegistrationRequestCreate,
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    item = locked_registration_request(session, request_id)
    email = payload.email.strip().lower()
    if email != item.email and item.status == "pending":
        clash = session.scalar(
            select(RegistrationRequest.id).where(
                RegistrationRequest.email == email,
                RegistrationRequest.status == "pending",
                RegistrationRequest.id != item.id,
            )
        )
        if clash is not None:
            raise HTTPException(409, "A request for this email is already awaiting review.")
    item.guardian_name = payload.guardian_name.strip()
    item.email = email
    item.phone = payload.phone.strip()
    item.child_name = payload.child_name.strip()
    item.child_birth_date = payload.child_birth_date
    item.relationship_to_child = payload.relationship_to_child.strip()
    item.notes = payload.notes.strip()
    if item.invitation_id is not None:
        invitation = session.get(GuardianInvitation, item.invitation_id)
        child = session.get(Child, invitation.child_id) if invitation is not None else None
        if child is not None:
            child.display_name = item.child_name
    session.commit()
    return registration_request_data(item)


@app.delete("/api/admin/platform/registration-requests/{request_id}", status_code=204)
def delete_registration_request(
    request_id: uuid.UUID,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Response:
    item = locked_registration_request(session, request_id)
    if item.account_id is not None:
        raise HTTPException(409, "This request already has a registered account.")
    if item.invitation_id is not None:
        invitation = session.get(GuardianInvitation, item.invitation_id)
        item.invitation_id = None
        session.flush()
        if invitation is not None:
            child_id = invitation.child_id
            session.delete(invitation)
            session.flush()
            has_links = session.scalar(
                select(func.count()).select_from(parent_child_links).where(
                    parent_child_links.c.child_id == child_id
                )
            )
            child = session.get(Child, child_id)
            if child is not None and not has_links:
                session.delete(child)
    session.delete(item)
    session.commit()
    return Response(status_code=204)


@app.post("/api/admin/platform/registration-requests/{request_id}/new-code")
def reissue_registration_code(
    request_id: uuid.UUID,
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    item = locked_registration_request(session, request_id)
    if item.status != "approved" or item.account_id is not None or item.invitation_id is None:
        raise HTTPException(409, "A new code can only be issued for approved requests that are not registered yet.")
    old = session.get(GuardianInvitation, item.invitation_id)
    if old is None:
        raise HTTPException(409, "The original invitation no longer exists.")
    now = datetime.now(timezone.utc)
    old.expires_at = now
    code = new_registration_code()
    while session.scalar(
        select(GuardianInvitation.id).where(
            GuardianInvitation.token_hash
            == hashlib.sha256(normalize_invitation_code(code).encode()).hexdigest()
        )
    ) is not None:
        code = new_registration_code()
    invitation = GuardianInvitation(
        child_id=old.child_id,
        token_hash=hashlib.sha256(normalize_invitation_code(code).encode()).hexdigest(),
        auto_approve=True,
        expires_at=now + timedelta(hours=REGISTRATION_CODE_TTL_HOURS),
    )
    session.add(invitation)
    session.flush()
    item.invitation_id = invitation.id
    item.email_sent = send_registration_code_email(item, code)
    session.commit()
    return {
        "request": registration_request_data(item),
        "registration_code": code,
        "expires_at": invitation.expires_at.isoformat(),
    }


@app.post("/api/admin/platform/registration-requests/{request_id}/decision")
def decide_registration_request(
    request_id: uuid.UUID,
    payload: RegistrationDecision,
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    item = session.scalar(
        select(RegistrationRequest)
        .where(RegistrationRequest.id == request_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Registration request not found.")
    if item.status != "pending":
        raise HTTPException(409, "This request has already been decided.")
    item.decided_at = datetime.now(timezone.utc)
    if payload.decision == "reject":
        item.status = "rejected"
        session.commit()
        return {"request": registration_request_data(item)}

    child = Child(display_name=item.child_name)
    session.add(child)
    session.flush()
    code = new_registration_code()
    while session.scalar(
        select(GuardianInvitation.id).where(
            GuardianInvitation.token_hash
            == hashlib.sha256(normalize_invitation_code(code).encode()).hexdigest()
        )
    ) is not None:
        code = new_registration_code()
    invitation = GuardianInvitation(
        child_id=child.id,
        token_hash=hashlib.sha256(normalize_invitation_code(code).encode()).hexdigest(),
        auto_approve=True,
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=REGISTRATION_CODE_TTL_HOURS),
    )
    session.add(invitation)
    session.flush()
    item.status = "approved"
    item.invitation_id = invitation.id
    item.email_sent = send_registration_code_email(item, code)
    session.commit()
    return {
        "request": registration_request_data(item),
        "registration_code": code,
        "expires_at": invitation.expires_at.isoformat(),
    }


@app.post("/api/platform/auth/logout")
def platform_logout(
    response: Response,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    principal.portal_session.revoked_at = datetime.now(timezone.utc)
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}


@app.get("/api/platform/auth/me")
def platform_me(
    response: Response,
    principal: PlatformPrincipal = Depends(get_platform_principal),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    account = principal.account
    roles = sorted(role.name for role in account.roles)
    permissions = sorted(
        {
            permission.name
            for role in account.roles
            for permission in role.permissions
        }
    )
    return {
        "id": str(account.id),
        "username": account.username,
        "preferred_language": account.preferred_language,
        "roles": roles,
        "permissions": permissions,
    }


@app.post("/api/platform/auth/change-password")
def change_own_password(
    payload: PasswordChangeRequest,
    response: Response,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    """A signed-in user changes their own password; all their other sessions end."""
    response.headers["Cache-Control"] = "no-store"
    account = principal.account
    secret = os.getenv("SESSION_SECRET", "") or "unset"
    key = security.throttle_key(secret, "password-change", str(account.id))
    if security.failures_since(session, key, PORTAL_LOGIN_WINDOW_SECONDS) >= PORTAL_LOGIN_MAX_FAILURES:
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")
    if not PASSWORD_HASHER.verify(payload.current_password, account.password_hash):
        security.record_attempt(session, key)
        session.commit()
        raise HTTPException(400, "The current password is incorrect.")
    if payload.new_password == payload.current_password:
        raise HTTPException(422, "Choose a new password that differs from the current one.")
    weak = security.password_problem(payload.new_password, account.username)
    if weak:
        raise HTTPException(422, weak)
    account.password_hash = PASSWORD_HASHER.hash(payload.new_password)
    session.execute(
        update(PortalSession)
        .where(
            PortalSession.account_id == account.id,
            PortalSession.revoked_at.is_(None),
            PortalSession.id != principal.portal_session.id,
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    session.commit()
    return {"ok": True}


@app.patch("/api/platform/auth/language")
def update_platform_language(
    payload: PreferredLanguageRequest,
    response: Response,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    principal.account.preferred_language = payload.language
    session.commit()
    return {"preferred_language": principal.account.preferred_language}


@app.post("/api/platform/children", status_code=201)
def create_child_profile(
    payload: ChildCreateRequest,
    principal: PlatformPrincipal = Depends(require_platform_role("admin")),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(422, "A child display name is required.")
    child = Child(display_name=display_name, created_by_id=principal.account.id)
    session.add(child)
    session.commit()
    return {"id": str(child.id), "display_name": child.display_name}


@app.post("/api/platform/children/{child_id}/guardian-invitations", status_code=201)
def create_guardian_invitation(
    child_id: uuid.UUID,
    payload: InvitationCreateRequest,
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("admin")),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    child = session.scalar(
        select(Child).where(Child.id == child_id, Child.is_active.is_(True))
    )
    if child is None:
        raise HTTPException(404, "Child profile not found.")

    code = secrets.token_urlsafe(32)
    invitation = GuardianInvitation(
        child_id=child.id,
        token_hash=hashlib.sha256(code.encode()).hexdigest(),
        created_by_id=principal.account.id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(hours=payload.expires_in_hours),
    )
    session.add(invitation)
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    return {
        "invitation_code": code,
        "expires_at": invitation.expires_at.isoformat(),
    }


@app.get("/api/platform/children")
def list_platform_children(
    response: Response,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_session),
) -> list[dict[str, str]]:
    response.headers["Cache-Control"] = "no-store"
    role_names = {role.name for role in principal.account.roles}
    if "parent" not in role_names and "admin" in role_names:
        children = session.scalars(
            select(Child)
            .where(Child.is_active.is_(True))
            .order_by(Child.display_name)
        ).all()
    elif "parent" in role_names:  # a parent who is also admin sees only their own children here
        children = session.scalars(
            select(Child)
            .join(parent_child_links, parent_child_links.c.child_id == Child.id)
            .where(
                parent_child_links.c.account_id == principal.account.id,
                Child.is_active.is_(True),
            )
            .order_by(Child.display_name)
        ).all()
    else:
        raise HTTPException(403, "This account cannot view child profiles.")
    return [{"id": str(child.id), "display_name": child.display_name} for child in children]


def report_data(report: DailyReport) -> dict[str, Any]:
    return {
        "id": str(report.id),
        "child_id": str(report.child_id),
        "title": report.title,
        "body": report.body,
        "language": report.language,
        "status": report.status,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "published_at": report.published_at.isoformat() if report.published_at else None,
    }


def teacher_content_data(content: TeacherContent) -> dict[str, Any]:
    return teacher_content_metadata(
        content.id,
        content.report_id,
        content.category,
        content.original_name,
        content.media_type,
        content.byte_size,
        content.created_at,
    )


def teacher_content_metadata(
    content_id: uuid.UUID,
    report_id: uuid.UUID | None,
    category: str,
    filename: str,
    media_type: str,
    size: int,
    created_at: datetime | None,
) -> dict[str, Any]:
    return {
        "id": str(content_id),
        "report_id": str(report_id) if report_id else None,
        "category": category,
        "filename": filename,
        "media_type": media_type,
        "size": size,
        "created_at": created_at.isoformat() if created_at else None,
    }


def private_content_media(filename: str, contents: bytes, category: str) -> tuple[str, int]:
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if category not in {"document", "image", "video", "other", "report_attachment"}:
        raise HTTPException(422, "Unsupported upload category.")
    if extension in BLOCKED_EXTENSIONS:
        raise HTTPException(415, "Executable and web-page files are not allowed.")
    file_info = CONTENT_TYPES.get(extension)
    if file_info is None:
        if category not in {"other", "report_attachment"}:
            raise HTTPException(422, "The selected upload category does not match the file type.")
        return "application/octet-stream", MAX_OTHER_BYTES
    file_category, media_type, signature = file_info
    if category not in {"report_attachment", "other"} and category != file_category:
        raise HTTPException(422, "The selected upload category does not match the file type.")
    if extension == ".webp":
        valid_file = contents.startswith(signature) and contents[8:12] == b"WEBP"
    elif extension == ".mp4":
        valid_file = len(contents) >= 12 and contents[4:8] == signature
    else:
        valid_file = contents.startswith(signature)
    if not valid_file:
        raise HTTPException(415, "The uploaded file contents do not match its file type.")
    max_size = {
        "document": MAX_DOCUMENT_BYTES,
        "image": MAX_PRIVATE_IMAGE_BYTES,
        "video": MAX_PRIVATE_VIDEO_BYTES,
    }[file_category]
    return media_type, max_size


def private_content_response(content: TeacherContent, response: Response) -> Response:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = (
        "attachment; filename*=UTF-8''" + quote(content.original_name, safe="")
    )
    return Response(
        content=content.contents,
        media_type=content.media_type,
        headers=response.headers,
    )


@app.post("/api/platform/children/{child_id}/teachers", status_code=201)
def assign_teacher_to_child(
    child_id: uuid.UUID,
    payload: TeacherAssignmentRequest,
    principal: PlatformPrincipal = Depends(require_platform_role("admin")),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    child = session.scalar(select(Child).where(Child.id == child_id, Child.is_active.is_(True)))
    teacher = session.scalar(
        select(Account)
        .join(Account.roles)
        .where(Account.id == payload.teacher_id, Account.is_active.is_(True), Role.name == "teacher")
    )
    if child is None or teacher is None:
        raise HTTPException(404, "Active child or teacher account not found.")
    if session.execute(
        select(teacher_child_links.c.account_id).where(
            teacher_child_links.c.account_id == teacher.id,
            teacher_child_links.c.child_id == child.id,
        )
    ).first():
        raise HTTPException(409, "Teacher is already assigned to this child.")
    session.execute(
        teacher_child_links.insert().values(
            account_id=teacher.id,
            child_id=child.id,
            assigned_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    return {"ok": True}


@app.get("/api/admin/platform/children")
def admin_list_children(
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    children = session.scalars(
        select(Child).where(Child.is_active.is_(True)).order_by(Child.display_name)
    ).all()
    teacher_rows = session.execute(
        select(teacher_child_links.c.child_id, Account.id, Account.username).join(
            Account, Account.id == teacher_child_links.c.account_id
        )
    ).all()
    parent_rows = session.execute(
        select(parent_child_links.c.child_id, Account.username, Account.id).join(
            Account, Account.id == parent_child_links.c.account_id
        )
    ).all()
    result = []
    for child in children:
        result.append(
            {
                "id": str(child.id),
                "display_name": child.display_name,
                "teachers": [
                    {"id": str(row[1]), "username": row[2]}
                    for row in teacher_rows
                    if row[0] == child.id
                ],
                "parents": [row[1] for row in parent_rows if row[0] == child.id],
                "parent_accounts": [{"id": str(row[2]), "username": row[1]} for row in parent_rows if row[0] == child.id],
            }
        )
    return result


@app.post("/api/admin/platform/children/{child_id}/teachers", status_code=201)
def admin_assign_teacher(
    child_id: uuid.UUID,
    payload: TeacherAssignmentRequest,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    child = session.scalar(select(Child).where(Child.id == child_id, Child.is_active.is_(True)))
    teacher = session.scalar(
        select(Account)
        .join(Account.roles)
        .where(Account.id == payload.teacher_id, Account.is_active.is_(True), Role.name == "teacher")
    )
    if child is None or teacher is None:
        raise HTTPException(404, "Active child or teacher account not found.")
    if session.execute(
        select(teacher_child_links.c.account_id).where(
            teacher_child_links.c.account_id == teacher.id,
            teacher_child_links.c.child_id == child.id,
        )
    ).first():
        raise HTTPException(409, "Teacher is already assigned to this child.")
    session.execute(
        teacher_child_links.insert().values(
            account_id=teacher.id,
            child_id=child.id,
            assigned_at=datetime.now(timezone.utc),
        )
    )
    session.commit()
    return {"ok": True}


@app.delete("/api/admin/platform/children/{child_id}/teachers/{teacher_id}", status_code=204)
def admin_unassign_teacher(
    child_id: uuid.UUID,
    teacher_id: uuid.UUID,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Response:
    session.execute(
        delete(teacher_child_links).where(
            teacher_child_links.c.account_id == teacher_id,
            teacher_child_links.c.child_id == child_id,
        )
    )
    session.commit()
    return Response(status_code=204)


class ParentAssignmentRequest(BaseModel):
    parent_id: uuid.UUID


@app.post("/api/admin/platform/children/{child_id}/parents", status_code=201)
def admin_link_parent(
    child_id: uuid.UUID,
    payload: ParentAssignmentRequest,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, bool]:
    """Link an existing parent account to a child so the parent sees that child's reports and private posts."""
    child = session.scalar(select(Child).where(Child.id == child_id, Child.is_active.is_(True)))
    parent = session.scalar(
        select(Account)
        .join(Account.roles)
        .where(Account.id == payload.parent_id, Account.is_active.is_(True), Role.name == "parent")
    )
    if child is None or parent is None:
        raise HTTPException(404, "Active child or parent account not found.")
    if session.execute(
        select(parent_child_links.c.account_id).where(
            parent_child_links.c.account_id == parent.id, parent_child_links.c.child_id == child.id
        )
    ).first():
        raise HTTPException(409, "Parent is already linked to this child.")
    session.execute(
        parent_child_links.insert().values(
            account_id=parent.id, child_id=child.id, confirmed_at=datetime.now(timezone.utc)
        )
    )
    session.commit()
    return {"ok": True}


@app.delete("/api/admin/platform/children/{child_id}/parents/{parent_id}", status_code=204)
def admin_unlink_parent(
    child_id: uuid.UUID,
    parent_id: uuid.UUID,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Response:
    session.execute(
        delete(parent_child_links).where(
            parent_child_links.c.account_id == parent_id, parent_child_links.c.child_id == child_id
        )
    )
    session.commit()
    return Response(status_code=204)


@app.get("/api/admin/platform/reports")
def admin_list_reports(
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """Reports waiting for review (submitted by teachers)."""
    response.headers["Cache-Control"] = "no-store"
    rows = session.execute(
        select(DailyReport, Child.display_name, Account.username)
        .join(Child, Child.id == DailyReport.child_id)
        .join(Account, Account.id == DailyReport.author_id)
        .where(DailyReport.status == "submitted")
        .order_by(DailyReport.created_at.asc())
    ).all()
    return [
        {**report_data(row[0]), "child_name": row[1], "author": row[2]} for row in rows
    ]


@app.patch("/api/admin/platform/reports/{report_id}")
def admin_review_report(
    report_id: uuid.UUID,
    payload: ReportStatusRequest,
    response: Response,
    _username: str = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    report = session.scalar(
        select(DailyReport).where(
            DailyReport.id == report_id, DailyReport.status == "submitted"
        )
    )
    if report is None:
        raise HTTPException(404, "Submitted report not found.")
    report.status = payload.status
    if payload.status == "published":
        report.published_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(report)
    return report_data(report)


@app.get("/api/platform/teacher/children")
def list_teacher_children(
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> list[dict[str, str]]:
    response.headers["Cache-Control"] = "no-store"
    children = session.scalars(
        select(Child)
        .join(teacher_child_links, teacher_child_links.c.child_id == Child.id)
        .where(
            teacher_child_links.c.account_id == principal.account.id,
            Child.is_active.is_(True),
        )
        .order_by(Child.display_name)
    ).all()
    return [{"id": str(child.id), "display_name": child.display_name} for child in children]


@app.get("/api/platform/teacher/content")
def list_teacher_content(
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    contents = session.execute(
        select(
            TeacherContent.id,
            TeacherContent.report_id,
            TeacherContent.category,
            TeacherContent.original_name,
            TeacherContent.media_type,
            TeacherContent.byte_size,
            TeacherContent.created_at,
        )
        .where(TeacherContent.owner_id == principal.account.id, TeacherContent.post_id.is_(None))
        .order_by(TeacherContent.created_at.desc())
    ).all()
    return [
        teacher_content_metadata(
            content.id,
            content.report_id,
            content.category,
            content.original_name,
            content.media_type,
            content.byte_size,
            content.created_at,
        )
        for content in contents
    ]


@app.get("/api/platform/admin/teacher-content")
def list_all_teacher_content(
    response: Response,
    _principal: PlatformPrincipal = Depends(require_platform_role("admin")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    contents = session.execute(
        select(
            TeacherContent.id,
            TeacherContent.report_id,
            TeacherContent.category,
            TeacherContent.original_name,
            TeacherContent.media_type,
            TeacherContent.byte_size,
            TeacherContent.created_at,
            Account.username,
        )
        .join(Account, Account.id == TeacherContent.owner_id)
        .where(TeacherContent.post_id.is_(None))
        .order_by(TeacherContent.created_at.desc())
    ).all()
    return [
        {
            **teacher_content_metadata(
                content.id,
                content.report_id,
                content.category,
                content.original_name,
                content.media_type,
                content.byte_size,
                content.created_at,
            ),
            "owner_username": content.username,
        }
        for content in contents
    ]


@app.post("/api/platform/teacher/content", status_code=201)
async def upload_teacher_content(
    response: Response,
    file: UploadFile = File(...),
    category: str = Form(...),
    report_id: uuid.UUID | None = Form(default=None),
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    filename = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not filename or len(filename) > 180:
        raise HTTPException(422, "A filename of up to 180 characters is required.")
    if category == "report_attachment":
        if report_id is None:
            raise HTTPException(422, "Select a report for its attachment.")
        report = session.scalar(
            select(DailyReport).where(
                DailyReport.id == report_id,
                DailyReport.author_id == principal.account.id,
                DailyReport.status.in_(("draft", "rejected")),
            ).with_for_update()
        )
        if report is None:
            raise HTTPException(404, "Editable report not found.")
        attachment_count = session.scalar(
            select(func.count()).select_from(TeacherContent).where(
                TeacherContent.report_id == report.id
            )
        )
        if attachment_count is not None and attachment_count >= MAX_REPORT_ATTACHMENTS:
            raise HTTPException(409, "A report can have up to five attachments.")
    elif report_id is not None:
        raise HTTPException(422, "Only report attachments can be linked to a report.")

    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    known = CONTENT_TYPES.get(extension)
    if known is None:
        _, max_size = private_content_media(filename, b"", category)
    else:
        max_size = {
            "document": MAX_DOCUMENT_BYTES,
            "image": MAX_PRIVATE_IMAGE_BYTES,
            "video": MAX_PRIVATE_VIDEO_BYTES,
        }[known[0]]
    contents = await file.read(max_size + 1)
    await file.close()
    if not contents:
        raise HTTPException(422, "The uploaded file is empty.")
    if len(contents) > max_size:
        raise HTTPException(413, "The file exceeds the size limit for its type.")
    media_type, _ = private_content_media(filename, contents, category)
    session.scalar(
        select(Account.id)
        .where(Account.id == principal.account.id)
        .with_for_update()
    )
    used_bytes = session.scalar(
        select(func.coalesce(func.sum(TeacherContent.byte_size), 0)).where(
            TeacherContent.owner_id == principal.account.id
        )
    )
    if (used_bytes or 0) + len(contents) > MAX_TEACHER_CONTENT_BYTES:
        raise HTTPException(413, "The teacher account has reached its 250 MB storage limit.")
    content = TeacherContent(
        owner_id=principal.account.id,
        report_id=report_id,
        category=category,
        original_name=filename,
        media_type=media_type,
        byte_size=len(contents),
        contents=contents,
    )
    session.add(content)
    session.commit()
    session.refresh(content)
    return teacher_content_data(content)


@app.get("/api/platform/teacher/content/{content_id}/download")
@app.get("/api/platform/admin/teacher-content/{content_id}/download")
def download_teacher_content(
    content_id: uuid.UUID,
    response: Response,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_session),
) -> Response:
    content = session.get(TeacherContent, content_id)
    if content is None:
        raise HTTPException(404, "Private upload not found.")
    roles = {role.name for role in principal.account.roles}
    if content.owner_id != principal.account.id and "admin" not in roles:
        raise HTTPException(404, "Private upload not found.")
    return private_content_response(content, response)


@app.delete("/api/platform/teacher/content/{content_id}", status_code=204)
@app.delete("/api/platform/admin/teacher-content/{content_id}", status_code=204)
def delete_teacher_content(
    content_id: uuid.UUID,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_session),
) -> Response:
    owner_id = session.scalar(
        select(TeacherContent.owner_id).where(TeacherContent.id == content_id)
    )
    if owner_id is None:
        raise HTTPException(404, "Private upload not found.")
    roles = {role.name for role in principal.account.roles}
    if owner_id != principal.account.id and "admin" not in roles:
        raise HTTPException(404, "Private upload not found.")
    session.execute(delete(TeacherContent).where(TeacherContent.id == content_id))
    session.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@app.get("/api/platform/teacher/reports/{report_id}/attachments")
def list_teacher_report_attachments(
    report_id: uuid.UUID,
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    report = session.scalar(
        select(DailyReport).where(
            DailyReport.id == report_id, DailyReport.author_id == principal.account.id
        )
    )
    if report is None:
        raise HTTPException(404, "Report not found.")
    contents = session.execute(
        select(
            TeacherContent.id,
            TeacherContent.report_id,
            TeacherContent.category,
            TeacherContent.original_name,
            TeacherContent.media_type,
            TeacherContent.byte_size,
            TeacherContent.created_at,
        )
        .where(TeacherContent.report_id == report.id, TeacherContent.owner_id == principal.account.id)
        .order_by(TeacherContent.created_at.asc())
    ).all()
    return [
        teacher_content_metadata(
            content.id,
            content.report_id,
            content.category,
            content.original_name,
            content.media_type,
            content.byte_size,
            content.created_at,
        )
        for content in contents
    ]


@app.get("/api/platform/teacher/reports")
def list_teacher_reports(
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    reports = session.scalars(
        select(DailyReport)
        .where(DailyReport.author_id == principal.account.id)
        .order_by(DailyReport.created_at.desc())
    ).all()
    return [report_data(report) for report in reports]


@app.post("/api/platform/teacher/reports", status_code=201)
def create_teacher_report(
    payload: DailyReportRequest,
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    assigned = session.execute(
        select(teacher_child_links.c.child_id).where(
            teacher_child_links.c.account_id == principal.account.id,
            teacher_child_links.c.child_id == payload.child_id,
        )
    ).first()
    if assigned is None:
        raise HTTPException(404, "Assigned child not found.")
    title, body = payload.title.strip(), payload.body.strip()
    if not title or not body:
        raise HTTPException(422, "Report title and text are required.")
    report = DailyReport(
        child_id=payload.child_id,
        author_id=principal.account.id,
        title=title,
        body=body,
        language=principal.account.preferred_language,
        status="submitted" if payload.submit_for_review else "draft",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report_data(report)


@app.patch("/api/platform/teacher/reports/{report_id}")
def update_teacher_report(
    report_id: uuid.UUID,
    payload: DailyReportUpdateRequest,
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    report = session.scalar(
        select(DailyReport).where(
            DailyReport.id == report_id,
            DailyReport.author_id == principal.account.id,
            DailyReport.status.in_(("draft", "rejected")),
        )
    )
    if report is None:
        raise HTTPException(404, "Editable report not found.")
    title, body = payload.title.strip(), payload.body.strip()
    if not title or not body:
        raise HTTPException(422, "Report title and text are required.")
    report.title = title
    report.body = body
    report.language = principal.account.preferred_language
    report.status = "submitted" if payload.submit_for_review else "draft"
    report.published_at = None
    session.commit()
    session.refresh(report)
    return report_data(report)


@app.get("/api/platform/review/reports")
def list_reports_for_review(
    response: Response,
    _principal: PlatformPrincipal = Depends(require_any_platform_role("manager", "admin")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    reports = session.scalars(
        select(DailyReport)
        .where(DailyReport.status == "submitted")
        .order_by(DailyReport.created_at.asc())
    ).all()
    return [report_data(report) for report in reports]


@app.patch("/api/platform/review/reports/{report_id}")
def update_report_status(
    report_id: uuid.UUID,
    payload: ReportStatusRequest,
    response: Response,
    _principal: PlatformPrincipal = Depends(require_any_platform_role("manager", "admin")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    report = session.scalar(
        select(DailyReport).where(
            DailyReport.id == report_id, DailyReport.status == "submitted"
        )
    )
    if report is None:
        raise HTTPException(404, "Submitted report not found.")
    report.status = payload.status
    if payload.status == "published":
        report.published_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(report)
    response.headers["Cache-Control"] = "no-store"
    return report_data(report)


# ----------------------------------------------------------------------------- teacher posts
# Two kinds: "general" (every parent sees it) and "child" (only the parents of that one child:
# grades, remarks...). Posts are visible to the families immediately; the author or an admin can delete them.
MAX_POST_FILES = 5
POST_SCOPES = ("general", "child")


def post_attachments(session: Session, post_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    result: dict[uuid.UUID, list[dict[str, Any]]] = {post_id: [] for post_id in post_ids}
    if not post_ids:
        return result
    rows = session.execute(
        select(
            TeacherContent.id, TeacherContent.post_id, TeacherContent.original_name,
            TeacherContent.media_type, TeacherContent.byte_size,
        )
        .where(TeacherContent.post_id.in_(post_ids))
        .order_by(TeacherContent.created_at.asc())
    ).all()
    for row in rows:
        result[row.post_id].append(
            {"id": str(row.id), "filename": row.original_name, "media_type": row.media_type, "size": row.byte_size}
        )
    return result


def posts_payload(session: Session, posts: list[TeacherPost]) -> list[dict[str, Any]]:
    files = post_attachments(session, [post.id for post in posts])
    child_ids = {post.child_id for post in posts if post.child_id}
    child_names = (
        {row.id: row.display_name for row in session.execute(select(Child.id, Child.display_name).where(Child.id.in_(child_ids)))}
        if child_ids else {}
    )
    author_ids = {post.author_id for post in posts}
    author_names = (
        {row.account_id: row.name for row in session.execute(select(Employee.account_id, Employee.name).where(Employee.account_id.in_(author_ids)))}
        if author_ids else {}
    )
    usernames = (
        {row.id: row.username for row in session.execute(select(Account.id, Account.username).where(Account.id.in_(author_ids)))}
        if author_ids else {}
    )
    return [
        {
            "id": str(post.id),
            "scope": post.scope,
            "child_id": str(post.child_id) if post.child_id else None,
            "child_name": child_names.get(post.child_id, ""),
            "title": post.title,
            "body": post.body,
            "author": author_names.get(post.author_id) or "",
            "author_username": usernames.get(post.author_id, ""),
            "created_at": post.created_at.isoformat() if post.created_at else None,
            "files": files.get(post.id, []),
        }
        for post in posts
    ]


@app.post("/api/platform/teacher/posts", status_code=201)
async def create_teacher_post(
    response: Response,
    scope: str = Form(...),
    title: str = Form(..., max_length=120),
    body: str = Form(default="", max_length=3000),
    child_id: uuid.UUID | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    title = title.strip()
    body = body.strip()
    uploads = [item for item in files if item.filename]
    if scope not in POST_SCOPES:
        raise HTTPException(422, "Choose a general or a private post.")
    if not title:
        raise HTTPException(422, "A title is required.")
    if not body and not uploads:
        raise HTTPException(422, "Write a message or attach a file.")
    if len(uploads) > MAX_POST_FILES:
        raise HTTPException(409, "A post can have up to five files.")
    if scope == "child":
        if child_id is None:
            raise HTTPException(422, "Select the child this private post is for.")
        assigned = session.scalar(
            select(Child.id)
            .join(teacher_child_links, teacher_child_links.c.child_id == Child.id)
            .where(
                Child.id == child_id, Child.is_active.is_(True),
                teacher_child_links.c.account_id == principal.account.id,
            )
        )
        if assigned is None:
            raise HTTPException(404, "Child profile not found.")
    else:
        child_id = None

    prepared: list[tuple[str, str, bytes]] = []
    for upload in uploads:
        filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename or len(filename) > 180:
            raise HTTPException(422, "A filename of up to 180 characters is required.")
        extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        known = CONTENT_TYPES.get(extension)
        if known is None:
            _, max_size = private_content_media(filename, b"", "other")
        else:
            max_size = {"document": MAX_DOCUMENT_BYTES, "image": MAX_PRIVATE_IMAGE_BYTES, "video": MAX_PRIVATE_VIDEO_BYTES}[known[0]]
        contents = await upload.read(max_size + 1)
        await upload.close()
        if not contents:
            raise HTTPException(422, "The uploaded file is empty.")
        if len(contents) > max_size:
            raise HTTPException(413, "The file exceeds the size limit for its type.")
        media_type, _ = private_content_media(filename, contents, "other")
        prepared.append((filename, media_type, contents))

    new_bytes = sum(len(item[2]) for item in prepared)
    if new_bytes:
        session.scalar(select(Account.id).where(Account.id == principal.account.id).with_for_update())
        used_bytes = session.scalar(
            select(func.coalesce(func.sum(TeacherContent.byte_size), 0)).where(
                TeacherContent.owner_id == principal.account.id
            )
        )
        if (used_bytes or 0) + new_bytes > MAX_TEACHER_CONTENT_BYTES:
            raise HTTPException(413, "The teacher account has reached its 250 MB storage limit.")
    post = TeacherPost(author_id=principal.account.id, scope=scope, child_id=child_id, title=title, body=body)
    session.add(post)
    session.flush()
    for filename, media_type, contents in prepared:
        session.add(TeacherContent(
            owner_id=principal.account.id, post_id=post.id, category="post_attachment",
            original_name=filename, media_type=media_type, byte_size=len(contents), contents=contents,
        ))
    session.commit()
    session.refresh(post)
    return posts_payload(session, [post])[0]


@app.get("/api/platform/teacher/posts")
def list_teacher_posts(
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("teacher")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    posts = session.scalars(
        select(TeacherPost).where(TeacherPost.author_id == principal.account.id)
        .order_by(TeacherPost.created_at.desc()).limit(100)
    ).all()
    return posts_payload(session, list(posts))


@app.get("/api/platform/admin/posts")
def list_all_posts(
    response: Response,
    _principal: PlatformPrincipal = Depends(require_platform_role("admin")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    posts = session.scalars(select(TeacherPost).order_by(TeacherPost.created_at.desc()).limit(200)).all()
    return posts_payload(session, list(posts))


@app.delete("/api/platform/teacher/posts/{post_id}", status_code=204)
@app.delete("/api/platform/admin/posts/{post_id}", status_code=204)
def delete_teacher_post(
    post_id: uuid.UUID,
    principal: PlatformPrincipal = Depends(get_platform_principal),
    session: Session = Depends(get_session),
) -> Response:
    post = session.get(TeacherPost, post_id)
    roles = {role.name for role in principal.account.roles}
    if post is None or (post.author_id != principal.account.id and "admin" not in roles):
        raise HTTPException(404, "Post not found.")
    session.execute(delete(TeacherContent).where(TeacherContent.post_id == post.id))
    session.delete(post)
    session.commit()
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


def visible_post_for_parent(session: Session, account_id: uuid.UUID, post_id: uuid.UUID) -> TeacherPost:
    post = session.get(TeacherPost, post_id)
    if post is None:
        raise HTTPException(404, "Post not found.")
    if post.scope == "child":
        linked = session.execute(
            select(parent_child_links.c.child_id).where(
                parent_child_links.c.account_id == account_id, parent_child_links.c.child_id == post.child_id
            )
        ).first()
        if linked is None:
            raise HTTPException(404, "Post not found.")
    return post


@app.get("/api/platform/parent/posts")
def list_parent_posts(
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("parent")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    """General posts for everyone, plus the private posts for this parent's own children only."""
    response.headers["Cache-Control"] = "no-store"
    own_children = select(parent_child_links.c.child_id).where(parent_child_links.c.account_id == principal.account.id)
    posts = session.scalars(
        select(TeacherPost)
        .where((TeacherPost.scope == "general") | ((TeacherPost.scope == "child") & TeacherPost.child_id.in_(own_children)))
        .order_by(TeacherPost.created_at.desc()).limit(100)
    ).all()
    data = posts_payload(session, list(posts))
    for item in data:
        item.pop("author_username", None)
    return data


@app.get("/api/platform/parent/posts/{post_id}/files/{content_id}")
def download_parent_post_file(
    post_id: uuid.UUID,
    content_id: uuid.UUID,
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("parent")),
    session: Session = Depends(get_session),
) -> Response:
    post = visible_post_for_parent(session, principal.account.id, post_id)
    content = session.get(TeacherContent, content_id)
    if content is None or content.post_id != post.id:
        raise HTTPException(404, "File not found.")
    return private_content_response(content, response)


@app.get("/api/platform/children/{child_id}/reports")
def list_parent_child_reports(
    child_id: uuid.UUID,
    response: Response,
    principal: PlatformPrincipal = Depends(require_platform_role("parent")),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    linked = session.execute(
        select(parent_child_links.c.child_id).where(
            parent_child_links.c.account_id == principal.account.id,
            parent_child_links.c.child_id == child_id,
        )
    ).first()
    if linked is None:
        raise HTTPException(404, "Child profile not found.")
    reports = session.scalars(
        select(DailyReport)
        .where(DailyReport.child_id == child_id, DailyReport.status == "published")
        .order_by(DailyReport.published_at.desc())
    ).all()
    return [report_data(report) for report in reports]
