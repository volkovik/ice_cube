import discord
from main import cfg
import mysql.connector
from discord.ext import commands


class Settings(commands.Cog, name="Настройки"):
    def __init__(self, bot):
        self.client = bot

    @commands.command(name="prefix")
    @commands.has_permissions(administrator=True)
    async def set_prefix_server(self, ctx, prefix=None):
        """
        Изменение префикса бота на сервере
        """

        server = ctx.guild

        db = mysql.connector.connect(**cfg["database"])
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
                message = discord.Embed(
                    title=":x: Ошибка",
                    description="Я не могу поставить префикс, который больше 16 символов",
                    color=0xDD2E44
                )

                cursor.close()
                db.close()

                return await ctx.send(embed=message)
            elif prefix == last_prefix:
                message = discord.Embed(
                    title=":x: Ошибка",
                    description="Вы уже используете данный префикс",
                    color=0xDD2E44
                )

                cursor.close()
                db.close()
                return await ctx.send(embed=message)

            if prefix == ".":
                cursor.execute("DELETE FROM servers WHERE id=%(server_id)s", data_sql)
            else:
                cursor.execute("INSERT INTO servers(id, prefix) VALUES(%(server_id)s, %(prefix)s)\n"
                               "ON DUPLICATE KEY UPDATE prefix=%(prefix)s", data_sql)

            message = discord.Embed(
                title=":white_check_mark: Выполнено",
                description="Я успешно изменил префикс",
                color=0x77B255
            )
        else:
            if last_prefix == '.' or last_prefix is None:
                message = discord.Embed(
                    title=":x: Ошибка",
                    description="Вы не ввели префикс",
                    color=0xDD2E44
                )
            else:
                cursor.execute("DELETE FROM servers WHERE id=%(server_id)s", data_sql)

                message = discord.Embed(
                    title=":white_check_mark: Выполнено",
                    description="Я успешно сбросил префикс на стандартный",
                    color=0x77B255
                )

        await ctx.send(embed=message)

        cursor.close()
        db.close()


def setup(bot):
    bot.add_cog(Settings(bot))
