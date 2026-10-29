from __future__ import annotations

import uuid
from datetime import date, datetime

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    LargeBinary,
    String,
    Table,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

account_roles = Table(
    "account_roles",
    Base.metadata,
    Column(
        "account_id",
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    preferred_language: Mapped[str] = mapped_column(String(35), default="ar", server_default="ar")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    approval_status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    roles: Mapped[list[Role]] = relationship(
        secondary=account_roles, back_populates="accounts", lazy="selectin"
    )


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    display_name: Mapped[str] = mapped_column(String(120))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    class_name: Mapped[str] = mapped_column(String(60), default="", server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


parent_child_links = Table(
    "parent_child_links",
    Base.metadata,
    Column(
        "account_id",
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "child_id",
        Uuid(as_uuid=True),
        ForeignKey("children.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("confirmed_at", DateTime(timezone=True), nullable=False),
)

teacher_child_links = Table(
    "teacher_child_links",
    Base.metadata,
    Column(
        "account_id",
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "child_id",
        Uuid(as_uuid=True),
        ForeignKey("children.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(3000))
    language: Mapped[str] = mapped_column(String(35), default="ar", server_default="ar")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)


class TeacherPost(Base):
    """A teacher's post: scope "general" is seen by every parent, scope "child" only by that child's parents."""

    __tablename__ = "teacher_posts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(10))
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(3000), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)


class TeacherContent(Base):
    __tablename__ = "teacher_content"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("daily_reports.id", ondelete="SET NULL"), index=True, nullable=True
    )
    post_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teacher_posts.id", ondelete="CASCADE"), index=True, nullable=True
    )
    category: Mapped[str] = mapped_column(String(30))
    original_name: Mapped[str] = mapped_column(String(180))
    media_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int]
    contents: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class GuardianInvitation(Base):
    __tablename__ = "guardian_invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    expires_at: Mapped[datetime] = mapped_column()
    redeemed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    guardian_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str] = mapped_column(String(40))
    child_name: Mapped[str] = mapped_column(String(120))
    child_birth_date: Mapped[str] = mapped_column(String(10), default="", server_default="")
    relationship_to_child: Mapped[str] = mapped_column(String(40), default="", server_default="")
    notes: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    preferred_language: Mapped[str] = mapped_column(String(35), default="ar", server_default="ar")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("guardian_invitations.id", ondelete="SET NULL"), nullable=True
    )
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    registered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class FeeCharge(Base):
    """Amount a child owes for one month, in one currency (USD or SYP)."""

    __tablename__ = "fee_charges"
    __table_args__ = (
        UniqueConstraint("child_id", "year", "month", "currency", name="uq_fee_charge_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    raw_text: Mapped[str] = mapped_column(String(300), default="", server_default="")
    source: Mapped[str] = mapped_column(String(120), default="", server_default="")
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    payments: Mapped[list[FeePayment]] = relationship(
        back_populates="charge", cascade="all, delete-orphan", lazy="selectin",
        order_by="FeePayment.paid_on",
    )


class FeePayment(Base):
    __tablename__ = "fee_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    charge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fee_charges.id", ondelete="CASCADE"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    receipt_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    created_by_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    payer_name: Mapped[str] = mapped_column(String(120), default="", server_default="")  # who handed the money over
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    charge: Mapped[FeeCharge] = relationship(back_populates="payments")
    __table_args__ = (
        Index(
            "uq_fee_payment_receipt_active",
            "receipt_no",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND receipt_no IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND receipt_no IS NOT NULL"),
        ),
    )


class Employee(Base):
    """Staff master data (teachers and other employees on the payroll)."""

    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    job_title: Mapped[str] = mapped_column(String(80), default="", server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # The platform account of this person (teacher / accountant), if they have one.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    # Usual monthly salary, saved once and used to pre-fill / generate the monthly payroll.
    salary: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    salary_currency: Mapped[str] = mapped_column(String(3), default="SYP", server_default="SYP")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SalaryLine(Base):
    """One employee's pay for one month. Net pay is calculated, never stored."""

    __tablename__ = "salary_lines"
    __table_args__ = (
        UniqueConstraint("employee_id", "year", "month", "currency", name="uq_salary_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    base: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    bonus: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    advance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    deduction: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    raw_text: Mapped[str] = mapped_column(String(300), default="", server_default="")
    source: Mapped[str] = mapped_column(String(120), default="", server_default="")
    paid_by: Mapped[str] = mapped_column(String(120), default="", server_default="")  # who handed the salary out
    recorded_by: Mapped[str] = mapped_column(String(80), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    employee: Mapped[Employee] = relationship(lazy="joined")


class AccountingEntry(Base):
    """A row of the monthly or weekly accounting sheet.

    Standard items (item_key) may be filled automatically; a stored row with
    manual=True overrides the automatic value."""

    __tablename__ = "accounting_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    period_type: Mapped[str] = mapped_column(String(5), index=True)  # "month" | "week"
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    week_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    item_key: Mapped[str] = mapped_column(String(20))  # standard key or "custom"
    item_label: Mapped[str] = mapped_column(String(120), default="", server_default="")
    details: Mapped[str] = mapped_column(String(500), default="", server_default="")
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    income: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    expense: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    manual: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    person: Mapped[str] = mapped_column(String(120), default="", server_default="")  # who spent / received the money
    entered_by: Mapped[str] = mapped_column(String(80), default="", server_default="")  # who typed the row in
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ExchangeRate(Base):
    """How many Syrian pounds one US dollar was worth from a given day on (set by the accountant)."""

    __tablename__ = "exchange_rates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    effective_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    syp_per_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    created_by: Mapped[str] = mapped_column(String(80), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CashOpening(Base):
    """The money the kindergarten had when the books start (one row per currency).
    From that month on, the cash balance = opening + every income - every expense."""

    __tablename__ = "cash_openings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    currency: Mapped[str] = mapped_column(String(3), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    start_year: Mapped[int] = mapped_column(Integer)
    start_month: Mapped[int] = mapped_column(Integer)
    updated_by: Mapped[str] = mapped_column(String(80), default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class FeeAuditLog(Base):
    __tablename__ = "fee_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(40))
    details: Mapped[str] = mapped_column(String(1000), default="", server_default="")


class PortalSession(Base):
    __tablename__ = "portal_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_id: Mapped[str] = mapped_column(String(64), unique=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column()
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username_hash: Mapped[str] = mapped_column(String(64), index=True)
    attempted_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(40), unique=True)
    accounts: Mapped[list[Account]] = relationship(
        secondary=account_roles, back_populates="roles"
    )
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(80), unique=True)
    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )
