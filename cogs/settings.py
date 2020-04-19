import discord
import mysql.connector
from discord.ext import commands

from main import CONFIG
from core.commands import BotCommand
from core.templates import ErrorMessage, SuccessfulMessage


class Settings(commands.Cog, name="Настройки"):
    def __init__(self, bot):
        self.client = bot

    @commands.command(
        cls=BotCommand, name="prefix",
        usage={"prefix": ("префикс бота, который будет работать только на этом сервере (оставьте пустым, если хотите "
                          "удалить уже существующий префикс)", True)}
    )
    @commands.has_permissions(administrator=True)
    async def set_prefix_server(self, ctx, prefix=None):
        """
        Изменение префикса бота на сервере
        """

        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "server_id": server.id,
            "prefix": prefix
        }

        cursor.execute("SELECT prefix FROM servers WHERE id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        last_prefix = result[0] if result is not None else None

        if prefix is not None:
            if len(prefix) > 16:
                message = ErrorMessage("Я не могу поставить префикс, который больше 16 символов")

                cursor.close()
                db.close()

                return await ctx.send(embed=message)
            elif prefix == last_prefix:
                message = ErrorMessage("Вы уже используете данный префикс")

                cursor.close()
                db.close()
                return await ctx.send(embed=message)

            if prefix == ".":
                cursor.execute("DELETE FROM servers WHERE id=%(server_id)s", data_sql)
            else:
                cursor.execute("INSERT INTO servers(id, prefix) VALUES(%(server_id)s, %(prefix)s)\n"
                               "ON DUPLICATE KEY UPDATE prefix=%(prefix)s", data_sql)

            message = SuccessfulMessage("Я успешно изменил префикс")
        else:
            if last_prefix == '.' or last_prefix is None:
                message = ErrorMessage("Вы не ввели префикс")
            else:
                cursor.execute("DELETE FROM servers WHERE id=%(server_id)s", data_sql)

                message = SuccessfulMessage("Я успешно сбросил префикс на стандартный")

        await ctx.send(embed=message)

        cursor.close()
        db.close()

    @set_prefix_server.error
    async def error_set_prefix_server(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=ErrorMessage("Вы должны быть администратором, чтобы измененить префикс на сервере"))

    @commands.group(name="setrooms", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def rooms_settings(self, ctx):
        """
        Настройка приватных комнат на сервере
        """

        await ctx.send_help(ctx.command)

    @rooms_settings.command(cls=BotCommand, name="enable")
    async def create_room_creator(self, ctx):
        """
        Создать приватные комнаты на сервере
        """

        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server_id": server.id}

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        last_voice = result[0] if result is not None else None

        if last_voice is None:
            message = SuccessfulMessage("Я успешно включил систему приватных комнат")

            category = await server.create_category_channel(name="Приватные комнаты")
            voice = await server.create_voice_channel(name="Создать комнату", category=category)

            data_sql["voice_id"] = voice.id

            cursor.execute("INSERT INTO rooms_server_settings(server_id, channel_id)\n"
                           "VALUES(%(server_id)s, %(voice_id)s)\n"
                           "ON DUPLICATE KEY UPDATE channel_id=%(voice_id)s", data_sql)
        else:
            message = ErrorMessage("У вас уже есть приватные комнаты")

        cursor.close()
        db.close()
        await ctx.send(embed=message)

    @rooms_settings.command(cls=BotCommand, name="disable")
    async def remove_room_creator(self, ctx):
        """
        Выключить и удалить приватные комнаты на сервере
        """

        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server_id": server.id}

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        last_voice = result[0] if result is not None else None

        if last_voice is not None:
            message = SuccessfulMessage("Я успешно выключил и удалил систему приватных комнат")

            voice = server.get_channel(int(last_voice))
            category = voice.category

            if len(category.voice_channels) != 0:
                for channel in category.voice_channels:
                    await channel.delete()

            await category.delete()

            cursor.execute("DELETE FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        else:
            message = ErrorMessage("На вашем сервере не поставлены приватные комнаты")

        cursor.close()
        db.close()
        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Settings(bot))
