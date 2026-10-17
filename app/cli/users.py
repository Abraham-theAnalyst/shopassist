"""Promote a user to admin, or demote an admin back to customer.

Usage:
    python -m app.cli.users promote <email>
    python -m app.cli.users demote <email>
    python -m app.cli.users promote <email> --yes   # skip the confirmation

Only changes users who already exist; it never creates accounts. Before
changing anything it shows which database it is connected to and asks for
confirmation. For running it against production, see the README.
"""

import argparse
import sys

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import User
from app.models.user import ROLE_ADMIN, ROLE_CUSTOMER


def database_label() -> str:
    """Host and database name, never the user name or password."""
    url = make_url(settings.database_url)
    port = f":{url.port}" if url.port else ""
    return f"{url.host}{port}/{url.database}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote or demote a ShopAssist user.")
    parser.add_argument("action", choices=["promote", "demote"])
    parser.add_argument("email")
    parser.add_argument("--yes", action="store_true", help="Don't ask for confirmation")
    args = parser.parse_args()

    email = args.email.strip().lower()  # emails are stored in lowercase
    new_role = ROLE_ADMIN if args.action == "promote" else ROLE_CUSTOMER

    print(f"Database: {database_label()}")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No user with the email {email}. Nothing was changed.")
            print("Accounts are never created by this command: register first, then promote.")
            return 1
        if user.role == new_role:
            print(f"{email} is already {'an admin' if new_role == ROLE_ADMIN else 'a customer'}. Nothing was changed.")
            return 0

        if not args.yes:
            answer = input(f"Change {email} from {user.role} to {new_role}? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                print("Cancelled. Nothing was changed.")
                return 1

        user.role = new_role
        db.commit()
        print(f"Done: {email} is now {'an admin' if new_role == ROLE_ADMIN else 'a customer'}. "
              "It takes effect on their next request; no new login is needed.")

        admins = db.scalar(select(func.count()).select_from(User).where(User.role == ROLE_ADMIN))
        if admins == 0:
            print("Warning: there are no admins left. Promote someone with: "
                  "python -m app.cli.users promote <email>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
