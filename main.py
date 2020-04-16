import discord
import json
import mysql.connector
from utilities import CustomHelpCommand
from discord.ext import commands

# Загрузка настроек бота
with open("config.json") as f:
    cfg = json.load(f)


def get_prefix(bot, message):
    """
    Возвращение префикса из базы данных, стандартного или при упоминание

    :param bot: класс бота
    :param message: сообщение
    :return: конечный префикс
    """

    prefix = "."

    if message.guild:
        db = mysql.connector.connect(**cfg["database"])
        cursor = db.cursor()

        data_sql = {"server_id": message.guild.id}

        cursor.execute("SELECT prefix FROM servers WHERE id=%(server_id)s;", data_sql)
        result = cursor.fetchone()

        if result is not None:
            prefix = result[0]

        cursor.close()
        db.close()

    return commands.when_mentioned_or(prefix)(bot, message)


client = commands.Bot(command_prefix=get_prefix)
client.help_command = CustomHelpCommand()
cogs = {"information", "fun", "settings"}  # Множество модулей

for cog in cogs:
    client.load_extension(f"cogs.{cog}")  # Загрузка модуля из множества


@client.event
async def on_ready():
    await client.change_presence(activity=discord.Streaming(name=".help", url="https://twitch.tv/volkovik/"))

    print(f"Бот {client.user.name} был запущен")


if __name__ == '__main__':
    client.run(cfg["token"])
