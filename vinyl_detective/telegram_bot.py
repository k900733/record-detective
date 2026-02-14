"""Telegram bot: alert formatting and command handlers."""

from __future__ import annotations

import logging
import sqlite3
from html import escape

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from vinyl_detective.scorer import Deal
from vinyl_detective import db


def format_deal_message(deal: Deal, affiliate_url: str) -> str:
    """Format a Deal into an HTML message for Telegram."""
    priority_tag = deal.priority.upper()
    artist = escape(deal.match.artist)
    title = escape(deal.match.title)

    savings_pct = int(deal.deal_score * 100)
    match_pct = int(deal.match.score * 100)
    method = escape(deal.match.method)

    lines = [
        f"<b>DEAL FOUND</b> [{priority_tag}]",
        "",
        f"<b>{artist} - {title}</b>",
        f"Price: ${deal.ebay_price:.2f} + ${deal.shipping:.2f} shipping",
        f"Discogs Median: ${deal.match.median_price:.2f}",
        f"<b>You Save: {savings_pct}%</b>",
    ]

    if deal.condition is not None:
        lines.append(f"Condition: {escape(deal.condition)}")

    lines.append(f"Match: {method} ({match_pct}%)")
    lines.append("")
    lines.append(f'<a href="{escape(affiliate_url)}">View on eBay</a>')

    return "\n".join(lines)


async def send_deal_alerts(
    bot,
    conn: sqlite3.Connection,
    deals: list[Deal],
    affiliate_campaign_id: str = "",
) -> None:
    """Send deal alerts to all matching saved searches.

    For each deal, find active searches whose min_deal_score <= deal.deal_score,
    skip already-alerted (chat_id, item_id) pairs, send formatted messages,
    and log alerts.
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    searches = db.get_active_searches(conn)
    for deal in deals:
        matching = [
            s for s in searches
            if s["min_deal_score"] <= deal.deal_score
        ]
        sent_any = False
        for search in matching:
            chat_id = search["chat_id"]
            if db.was_alerted(conn, chat_id, deal.item_id):
                continue
            if affiliate_campaign_id:
                parsed = urlparse(deal.item_web_url)
                existing = parse_qs(parsed.query, keep_blank_values=True)
                epn_params = {
                    "mkevt": "1",
                    "mkcid": "1",
                    "mkrid": "711-53200-19255-0",
                    "campid": affiliate_campaign_id,
                    "toolid": "10001",
                }
                existing.update(epn_params)
                flat = {
                    k: v if isinstance(v, str) else v[0]
                    for k, v in existing.items()
                }
                affiliate_url = urlunparse(
                    parsed._replace(query=urlencode(flat))
                )
            else:
                affiliate_url = deal.item_web_url
            message = format_deal_message(deal, affiliate_url)
            try:
                await bot.send_message(
                    chat_id=chat_id, text=message, parse_mode="HTML"
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to send alert to chat %s for item %s",
                    chat_id,
                    deal.item_id,
                )
                continue
            db.log_alert(conn, chat_id, deal.item_id, deal.deal_score)
            sent_any = True
        if sent_any:
            db.mark_notified(conn, deal.item_id)


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to Vinyl Detective!\n\n"
        "I find underpriced vinyl, CD, and cassette deals on eBay "
        "by comparing against Discogs median prices.\n\n"
        "Commands:\n"
        "/add_search <query> - Add a search\n"
        "/my_searches - List your searches\n"
        "/remove_search <id> - Remove a search\n"
        "/set_threshold <value> - Set minimum deal score (0-1)\n"
        "/help - Show this help"
    )


async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Welcome message\n"
        "/add_search <query> - Add a saved search\n"
        "/my_searches - List your saved searches\n"
        "/remove_search <id> - Remove a search by ID\n"
        "/set_threshold <value> - Set minimum deal score (0.0 to 1.0)\n"
        "/help - Show this help"
    )


async def _add_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add_search <query> command."""
    if not context.args:
        await update.message.reply_text("Usage: /add_search <query>")
        return
    query = " ".join(context.args)
    chat_id = update.effective_chat.id
    conn = context.bot_data["db"]
    search_id = db.add_search(conn, chat_id, query)
    await update.message.reply_text(
        f"Search added (ID: {search_id}): {query}"
    )


async def _my_searches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /my_searches command."""
    chat_id = update.effective_chat.id
    conn = context.bot_data["db"]
    searches = db.get_searches_for_chat(conn, chat_id)
    if not searches:
        await update.message.reply_text("No saved searches.")
        return
    lines = []
    for s in searches:
        status = "active" if s["active"] else "inactive"
        lines.append(f"[{s['id']}] {s['query']} ({status})")
    await update.message.reply_text("\n".join(lines))


async def _remove_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /remove_search <id> command."""
    if not context.args:
        await update.message.reply_text("Usage: /remove_search <id>")
        return
    try:
        search_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid search ID.")
        return
    conn = context.bot_data["db"]
    db.toggle_search(conn, search_id, False)
    await update.message.reply_text(f"Search {search_id} removed.")


async def _set_threshold(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /set_threshold <value> command."""
    if not context.args:
        await update.message.reply_text("Usage: /set_threshold <value>")
        return
    try:
        value = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid threshold value.")
        return
    if not 0.0 <= value <= 1.0:
        await update.message.reply_text("Threshold must be between 0.0 and 1.0.")
        return
    chat_id = update.effective_chat.id
    conn = context.bot_data["db"]
    searches = db.get_searches_for_chat(conn, chat_id)
    for s in searches:
        conn.execute(
            "UPDATE saved_searches SET min_deal_score = ? WHERE id = ?",
            (value, s["id"]),
        )
    conn.commit()
    await update.message.reply_text(
        f"Threshold set to {value:.2f} for all your searches."
    )


def create_bot(token: str, conn: sqlite3.Connection) -> Application:
    """Build and return a configured Application."""
    app = Application.builder().token(token).build()
    app.bot_data["db"] = conn
    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))
    app.add_handler(CommandHandler("add_search", _add_search))
    app.add_handler(CommandHandler("my_searches", _my_searches))
    app.add_handler(CommandHandler("remove_search", _remove_search))
    app.add_handler(CommandHandler("set_threshold", _set_threshold))
    return app
