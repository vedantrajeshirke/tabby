"""Load or remove synthetic data for one user. Local use: docker compose exec api python -m scripts.seed_synthetic"""
import argparse
from datetime import date

from core import db, demo
from core.config import LOCAL_USER_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default=LOCAL_USER_ID)
    parser.add_argument("--remove", action="store_true", help="remove synthetic rows instead of adding them")
    args = parser.parse_args()
    with db.connect() as conn:
        db.act_as(conn, args.user_id)
        if args.remove:
            print(f"Removed {db.delete_synthetic(conn, args.user_id)} synthetic expenses.")
        else:
            print(f"Loaded {demo.load(conn, args.user_id, date.today())} synthetic expenses.")


if __name__ == "__main__":
    main()
