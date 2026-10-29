from __future__ import annotations

import argparse
import getpass
import re

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Account, Role

PASSWORD_HASHER = PasswordHash.recommended()
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,80}$")


def create_account(username: str, role_name: str, password: str) -> None:
    normalized_username = username.strip().lower()
    if not USERNAME_RE.fullmatch(normalized_username):
        raise ValueError("Username must contain 3–80 letters, digits, dots, underscores, or hyphens.")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long.")

    with Session(get_engine()) as session:
        role = session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            raise ValueError(f"Unknown role: {role_name}. Run database migrations first.")
        account = Account(
            username=normalized_username,
            password_hash=PASSWORD_HASHER.hash(password),
            roles=[role],
        )
        session.add(account)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ValueError(f"Account already exists: {normalized_username}.") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage platform accounts.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-account", help="Create an account with a platform role.")
    create.add_argument("--username", required=True)
    create.add_argument("--role", required=True, choices=("admin", "manager", "teacher", "accountant", "parent"))
    args = parser.parse_args()

    password = getpass.getpass("New password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("Passwords do not match.")
    try:
        create_account(args.username, args.role, password)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Created {args.role} account: {args.username.strip().lower()}")


if __name__ == "__main__":
    main()
