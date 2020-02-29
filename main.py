import discord
import json
from discord.ext import commands

# Загрузка настроек бота
with open("config.json") as f:
    cfg = json.load(f)

client = commands.Bot(command_prefix=".")


@client.event
async def on_ready():
    await client.change_presence(activity=discord.Streaming(name="Напиши .help", url="https://twitch.tv/volkovik/"))

    print(f"Бот был подключён как \"{client.user}\"")


if __name__ == '__main__':
    client.run(cfg["token"])
