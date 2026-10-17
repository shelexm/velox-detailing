"""Management commands:  python -m app.cli <command>

seed            create the studio and the starting catalog from the design (idempotent)
create-admin    create the first panel user (or reset a password); the password is asked interactively
                or read from the ADMIN_PASSWORD environment variable, it is never printed
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_sessionmaker
from app.models.enums import Role


async def _with_session(action):
    engine = create_engine(get_settings())
    try:
        async with create_sessionmaker(engine)() as session:
            return await action(session)
    finally:
        await engine.dispose()


async def _seed(slug: str) -> None:
    from app.seed.run import seed_all

    media_root = get_settings().media_root
    studio = await _with_session(lambda session: seed_all(session, slug, media_root=media_root))
    print(f"Studio '{studio.slug}' is ready (id={studio.id})")


def _read_password() -> str:
    from_env = os.environ.get("ADMIN_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("Пароль (не короче 12 символов): ")
    second = getpass.getpass("Повторите пароль: ")
    if first != second:
        raise SystemExit("Пароли не совпадают")
    return first


async def _create_admin(args: argparse.Namespace, slug: str) -> None:
    from app.services.auth import create_or_update_admin

    password = _read_password()
    try:
        user, created = await _with_session(
            lambda session: create_or_update_admin(
                session,
                email=args.email,
                full_name=args.name,
                password=password,
                studio_slug=slug,
                role=Role(args.role),
                reset_password=args.reset_password,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"{'Created' if created else 'Updated'} {args.role} {user.email} for studio '{slug}'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed", help="create the studio and starting catalog if missing")
    seed.add_argument("--studio", default=None, help="studio slug (default: DEFAULT_STUDIO_SLUG)")
    admin = commands.add_parser("create-admin", help="create a panel user with a role in a studio")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True, help="full name shown in the panel")
    admin.add_argument("--role", choices=[r.value for r in Role], default=Role.OWNER.value)
    admin.add_argument("--studio", default=None, help="studio slug (default: DEFAULT_STUDIO_SLUG)")
    admin.add_argument("--reset-password", action="store_true", help="set a new password for an existing user")

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    slug = args.studio or settings.default_studio_slug
    if args.command == "seed":
        asyncio.run(_seed(slug))
    elif args.command == "create-admin":
        asyncio.run(_create_admin(args, slug))
    return 0


if __name__ == "__main__":
    sys.exit(main())
