from vinyl_detective.config import load_config
from vinyl_detective.db import init_db


def main():
    config = load_config()
    conn = init_db(config.db_path)
    print(f"Vinyl Detective started. DB initialized at {config.db_path}")
    conn.close()


main()
