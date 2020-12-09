import discord
import logging
import sqlalchemy
import os
from discord.ext import commands
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from core.templates import Help
from core.database import Base, Server

__version__ = "0.3.1"

# Environment variables
DEV_MODE = os.environ.get("DEV_MODE") == "True"
DEFAULT_PREFIX = "." if not DEV_MODE else ">"
SAVE_LOGS = os.environ.get("SAVE_LOGS") == "True"
PRINT_LOG_TIME = os.environ.get("PRINT_LOG_TIME") == "True"

# Database
ENGINE_DB = sqlalchemy.create_engine(os.environ.get("DATABASE_URL"))
Session = sessionmaker(bind=ENGINE_DB)
Base.metadata.create_all(bind=ENGINE_DB)

# Logs settings

# Print logs time
if PRINT_LOG_TIME:
    output_log_format = "%(asctime)s | %(levelname)s:%(name)s: %(message)s"
else:
    output_log_format = "%(levelname)s:%(name)s: %(message)s"
date_format = "%d.%m.%Y %H:%M:%S"

# Printing debug logs
if DEV_MODE:
    level = logging.DEBUG
else:
    level = logging.INFO

# Set settings
logging.basicConfig(
    level=level,
    format=output_log_format,
    datefmt=date_format
)

logger = logging.getLogger("ice_cube")
logger.setLevel(logging.INFO)
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)

if SAVE_LOGS:
    handler = logging.FileHandler(
        filename=f"logs/{datetime.now().strftime('%d-%m-%Y-%H-%M-%S')}.log",
        encoding="utf-8",
        mode="w"
    )
    handler.setFormatter(logging.Formatter(output_log_format, date_format))
    logger.addHandler(handler)
    discord_logger.addHandler(handler)


def get_prefix(bot: commands.Bot, message: commands.Context) -> list:
    """
    Returns prefixes like bot mention and either prefix default prefix defined by env variable or prefix from database
    """
    prefix = DEFAULT_PREFIX

    if message.guild:
        session = Session()
        server_from_db = session.query(Server).filter_by(server_id=str(message.guild.id)).first()
        session.close()

        # If data from db exists, we set prefix from db
        if server_from_db is not None and server_from_db.prefix is not None:
            prefix = server_from_db.prefix

    return commands.when_mentioned_or(prefix)(bot, message)


# Bot settings
client = commands.Bot(command_prefix=get_prefix)
client.help_command = Help()


@client.event
async def on_ready():
    logger.info(f"Бот {client.user.name} запущен")

    if DEV_MODE:
        logger.warning(f"Бот запущен в режиме разработки. Стандартный префикс бота: {DEFAULT_PREFIX}")

        await client.change_presence(status=discord.Status.do_not_disturb, activity=discord.Activity(
            name="dev",
            type=discord.ActivityType.watching
        ))
    else:
        await client.change_presence(activity=discord.Streaming(name=".help", url="https://twitch.tv/volkovik/"))


if __name__ == '__main__':
    plugins_path = "plugins"
    plugins = ["levels", "rooms", "settings", "error", "fun", "information", ]

    for plugin in plugins:
        client.load_extension(f"{plugins_path}.{plugin}")
        logging.info(f"\"{plugin}\" плагин загружен")

    client.run(os.environ.get("BOT_TOKEN"))
