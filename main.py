import discord
import sqlalchemy
import os
from discord.ext import commands
from sqlalchemy.orm import sessionmaker

from core.templates import Help
from core.database import Base, Server

DEV_MODE = os.environ.get("DEV_MODE")
DEFAULT_PREFIX = "." if not DEV_MODE else ">"

ENGINE_DB = sqlalchemy.create_engine("sqlite:///ice_cube")
Base.metadata.create_all(bind=ENGINE_DB)


def get_prefix(bot, message):
    """
    Возвращение префикса из базы данных, стандартного или при упоминание

    :param bot: класс бота
    :param message: сообщение
    :return: конечный префикс
    """

    prefix = DEFAULT_PREFIX

    if message.guild:
        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        server_from_db = session.query(Server).filter_by(server_id=message.guild.id).first()

        if server_from_db is not None and server_from_db.prefix is not None:
            prefix = server_from_db.prefix

    return commands.when_mentioned_or(prefix)(bot, message)


client = commands.Bot(command_prefix=get_prefix)
client.help_command = Help()
client.load_extension("core.commands")

cogs_path = "cogs/"  # Директория, где расположены модули
for name_of_file in [f for f in os.listdir("cogs") if os.path.isfile(os.path.join("cogs", f))]:
    client.load_extension(f"cogs.{name_of_file[:-3]}")  # Загрузка модуля из множества


@client.event
async def on_ready():
    if DEV_MODE:
        await client.change_presence(status=discord.Status.do_not_disturb, activity=discord.Activity(
            name="dev",
            type=discord.ActivityType.watching
        ))
    else:
        await client.change_presence(activity=discord.Streaming(name=".help", url="https://twitch.tv/volkovik/"))

    print(f"Бот {client.user.name} был запущен")


if __name__ == '__main__':
    client.run(os.environ.get("BOT_TOKEN"))
