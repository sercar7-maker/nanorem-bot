from telegram.ext import Application, CommandHandler

from tg_handlers.handlers import setup_handlers


def test_telegram_handlers_do_not_expose_financial_test_order():
    application = (
        Application.builder()
        .token("123456:TEST_ONLY_NOT_A_REAL_TOKEN")
        .build()
    )

    setup_handlers(application)

    registered_commands = {
        command
        for handlers in application.handlers.values()
        for handler in handlers
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }

    assert "test_order" not in registered_commands
