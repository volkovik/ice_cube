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
                message = discord.Embed(
                    title=":x: Ошибка",
                    description="Вы не ввели префикс",
                    color=0xDD2E44
                )
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


def setup(bot):
    bot.add_cog(Settings(bot))
