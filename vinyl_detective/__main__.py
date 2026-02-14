import asyncio
import logging
import signal

from vinyl_detective.config import load_config
from vinyl_detective.db import init_db
from vinyl_detective.discogs import DiscogsClient
from vinyl_detective.ebay import EbayClient
from vinyl_detective.pipeline import (
    cleanup_stale_loop,
    poll_ebay_loop,
    refresh_discogs_loop,
)
from vinyl_detective.rate_limiter import RateLimiter
from vinyl_detective.telegram_bot import create_bot

log = logging.getLogger("vinyl_detective")


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    config = load_config()
    conn = init_db(config.db_path)
    log.info("DB initialized at %s", config.db_path)

    discogs_limiter = RateLimiter(calls_per_minute=60)
    ebay_limiter = RateLimiter(calls_per_minute=5000 // (24 * 60))

    app = create_bot(config.telegram_token, conn)

    async with (
        DiscogsClient(config.discogs_token, discogs_limiter) as discogs_client,
        EbayClient(config.ebay_app_id, config.ebay_cert_id, ebay_limiter) as ebay_client,
    ):
        async with app:
            await app.start()
            await app.updater.start_polling()
            log.info("Vinyl Detective started")

            stop = asyncio.Event()
            tasks = [
                asyncio.create_task(
                    poll_ebay_loop(ebay_client, conn, app.bot, config, shutdown_event=stop),
                    name="poll_ebay",
                ),
                asyncio.create_task(
                    refresh_discogs_loop(discogs_client, conn, config, shutdown_event=stop),
                    name="refresh_discogs",
                ),
                asyncio.create_task(
                    cleanup_stale_loop(conn, shutdown_event=stop),
                    name="cleanup",
                ),
            ]

            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)

            await stop.wait()
            log.info("Shutdown signal received")

            await asyncio.gather(*tasks, return_exceptions=True)

            await app.updater.stop()
            await app.stop()

        conn.close()
        log.info("Vinyl Detective stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
