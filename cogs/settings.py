import mysql.connector
from discord.ext import commands

from main import CONFIG
from core.commands import BotCommand
from core.templates import SuccessfulMessage, CustomError


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
                cursor.close()
                db.close()

                raise CustomError("Я не могу поставить префикс, который больше 16 символов")
            elif prefix == last_prefix or (last_prefix is None and prefix == "."):
                cursor.close()
                db.close()

                raise CustomError("Вы уже используете данный префикс")

            if prefix == ".":
                cursor.execute("DELETE FROM servers WHERE id=%(server_id)s", data_sql)
            else:
                cursor.execute("INSERT INTO servers(id, prefix) VALUES(%(server_id)s, %(prefix)s)\n"
                               "ON DUPLICATE KEY UPDATE prefix=%(prefix)s", data_sql)

            message = SuccessfulMessage("Я успешно изменил префикс")
        else:
            if last_prefix == '.' or last_prefix is None:
                cursor.close()
                db.close()

                raise CustomError("Вы не ввели префикс")
            else:
                cursor.execute("DELETE FROM servers WHERE id=%(server_id)s", data_sql)

                message = SuccessfulMessage("Я успешно сбросил префикс на стандартный")

        await ctx.send(embed=message)

        cursor.close()
        db.close()

    @commands.group(name="setrooms", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def rooms_settings(self, ctx):
        """
        Настройка приватных комнат на сервере
        """

    @rooms_settings.command(cls=BotCommand, name="enable")
    @commands.has_permissions(administrator=True)
    async def create_rooms_system(self, ctx):
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

        if last_voice is not None:
            cursor.close()
            db.close()

            raise CustomError("У вас уже есть приватные комнаты")
        else:
            message = SuccessfulMessage("Я успешно включил систему приватных комнат")

            category = await server.create_category_channel(name="Приватные комнаты")
            voice = await server.create_voice_channel(name="Создать комнату", category=category)

            data_sql["voice_id"] = voice.id

            cursor.execute("INSERT INTO rooms_server_settings(server_id, channel_id)\n"
                           "VALUES(%(server_id)s, %(voice_id)s)\n"
                           "ON DUPLICATE KEY UPDATE channel_id=%(voice_id)s", data_sql)

            cursor.close()
            db.close()

        await ctx.send(embed=message)

    @rooms_settings.command(cls=BotCommand, name="disable")
    @commands.has_permissions(administrator=True)
    async def remove_rooms_system(self, ctx):
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

        if last_voice is None:
            cursor.close()
            db.close()

            raise CustomError("На вашем сервере не поставлены приватные комнаты")
        else:
            message = SuccessfulMessage("Я успешно выключил и удалил систему приватных комнат")

            voice = server.get_channel(int(last_voice))
            category = voice.category

            if len(category.voice_channels) != 0:
                for channel in category.voice_channels:
                    await channel.delete()

            await category.delete()

            cursor.execute("DELETE FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)

            cursor.close()
            db.close()

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Settings(bot))
