"""Management commands:  python -m app.cli <command>

seed                         create the studio and the starting catalog from the design (idempotent)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_sessionmaker


async def _seed(slug: str) -> None:
    from app.seed.run import seed_all

    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            studio = await seed_all(session, slug)
            print(f"Studio '{studio.slug}' is ready (id={studio.id})")
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed", help="create the studio and starting catalog if missing")
    seed.add_argument("--studio", default=None, help="studio slug (default: DEFAULT_STUDIO_SLUG)")

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    if args.command == "seed":
        asyncio.run(_seed(args.studio or settings.default_studio_slug))
    return 0


if __name__ == "__main__":
    sys.exit(main())
