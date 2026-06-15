import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

from database.db import SessionLocal
from services.network_tree_service import NetworkTreeService

logger = logging.getLogger(__name__)


async def show_network(update, context):

    query = update.callback_query
    await query.answer()

    data = query.data
    partner_id = int(data.split(":")[1])

    session = SessionLocal()

    service = NetworkTreeService(session)

    partners = service.get_direct_partners(partner_id)

    session.close()

    if not partners:
        await query.edit_message_text(
            "У этого партнёра нет партнёров."
        )
        return

    keyboard = []

    for p in partners:

        name = p["first_name"] or "Без имени"

        if p["username"]:
            name += f" (@{p['username']})"

        button = InlineKeyboardButton(
            name,
            callback_data=f"net:{p['id']}"
        )

        keyboard.append([button])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text="👥 Партнёры:",
        reply_markup=reply_markup
    )


def get_handler():
    return CallbackQueryHandler(show_network, pattern="^net:")