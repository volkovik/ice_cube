import discord
import json
from utilities import CustomHelpCommand
from discord.ext import commands

# Загрузка настроек бота
with open("config.json") as f:
    cfg = json.load(f)

client = commands.Bot(command_prefix=".")
client.help_command = CustomHelpCommand()
cogs = {"information"}  # Множество модулей

for cog in cogs:
    client.load_extension(f"cogs.{cog}")  # Загрузка модуля из множества


@client.event
async def on_ready():
    await client.change_presence(activity=discord.Streaming(name="Напиши .help", url="https://twitch.tv/volkovik/"))

    print(f"Бот был подключён как \"{client.user}\"")


if __name__ == '__main__':
    client.run(cfg["token"])
