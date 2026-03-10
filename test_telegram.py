from telegram.ext import Application

app = Application.builder().token("TEST").build()

print("Бот создаётся нормально")