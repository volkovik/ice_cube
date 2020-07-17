import discord
import json
import sqlalchemy
import os
from discord.ext import commands
from sqlalchemy.orm import sessionmaker

from core.templates import Help
from core.database import Base, Server

# Загрузка настроек бота
with open("config.json") as f:
    CONFIG = json.load(f)

engine_db = sqlalchemy.create_engine("sqlite:///ice_cube")
Base.metadata.create_all(bind=engine_db)


def get_prefix(bot, message):
    """
    Возвращение префикса из базы данных, стандартного или при упоминание

    :param bot: класс бота
    :param message: сообщение
    :return: конечный префикс
    """

    prefix = "."

    if message.guild:
        Session = sessionmaker(bind=engine_db)
        session = Session()

        result = session.query(Server).filter_by(server_id=message.guild.id).first()

        if result is not None:
            prefix = result.prefix

    return commands.when_mentioned_or(prefix)(bot, message)


client = commands.Bot(command_prefix=get_prefix)
client.help_command = Help()
client.load_extension("core.commands")

cogs_path = "cogs/"  # Директория, где расположены модули
for name_of_file in [f for f in os.listdir("cogs") if os.path.isfile(os.path.join("cogs", f))]:
    client.load_extension(f"cogs.{name_of_file[:-3]}")  # Загрузка модуля из множества


@client.event
async def on_ready():
    await client.change_presence(activity=discord.Streaming(name=".help", url="https://twitch.tv/volkovik/"))

    print(f"Бот {client.user.name} был запущен")


if __name__ == '__main__':
    client.run(CONFIG["token"])
