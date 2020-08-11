import discord
import logging
import sqlalchemy
import os
from discord.ext import commands
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from core.templates import Help
from core.database import Base, Server

__version__ = "0.3.0.1b"

# Основные константы
DEV_MODE = True if os.environ.get("DEV_MODE") == "True" else False
DEFAULT_PREFIX = "." if not DEV_MODE else ">"

# База данных
ENGINE_DB = sqlalchemy.create_engine(os.environ.get("DATABASE_URL"))
Session = sessionmaker(bind=ENGINE_DB)
Base.metadata.create_all(bind=ENGINE_DB)

# Конфигурация логирования
output_log_format = "%(asctime)s | %(levelname)s:%(name)s: %(message)s"
date_format = "%d.%m.%Y %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=output_log_format,
    datefmt=date_format
)

logger = logging.getLogger("ice_cube")
logger.setLevel(logging.INFO)
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)

if not os.path.exists("logs"):
    os.makedirs("logs")

handler = logging.FileHandler(
    filename=f"logs/{datetime.now().strftime('%d-%m-%Y-%H-%M-%S')}.log",
    encoding="utf-8",
    mode="w"
)
handler.setFormatter(logging.Formatter(output_log_format, date_format))
logger.addHandler(handler)
discord_logger.addHandler(handler)


def get_prefix(bot, message):
    """
    Возвращение префикса из базы данных или стандартного, а также префикс в виде упоминания бота

    :param bot: класс бота
    :param message: сообщение
    :return: конечный префикс
    """

    prefix = DEFAULT_PREFIX

    if message.guild:
        session = Session()

        server_from_db = session.query(Server).filter_by(server_id=str(message.guild.id)).first()

        if server_from_db is not None and server_from_db.prefix is not None:
            prefix = server_from_db.prefix

        session.close()

    return commands.when_mentioned_or(prefix)(bot, message)


# Настройка бота
client = commands.Bot(command_prefix=get_prefix)
client.help_command = Help()

cogs_path = "cogs/"  # Директория, где расположены модули
for name_of_file in [f for f in os.listdir("cogs") if os.path.isfile(os.path.join("cogs", f))]:
    client.load_extension(f"cogs.{name_of_file[:-3]}")  # Загрузка модуля из множества


@client.event
async def on_ready():
    logger.info(f"Бот {client.user.name} был запущен")

    if DEV_MODE:
        logger.warning(f"Бот запущен в режиме разработки. Стандартный префикс бота: {DEFAULT_PREFIX}")

        await client.change_presence(status=discord.Status.do_not_disturb, activity=discord.Activity(
            name="dev",
            type=discord.ActivityType.watching
        ))
    else:
        await client.change_presence(activity=discord.Streaming(name=".help", url="https://twitch.tv/volkovik/"))


if __name__ == '__main__':
    client.run(os.environ.get("BOT_TOKEN"))
