import re
import mysql.connector
from discord.ext import commands
from discord.ext.commands import CommandError
from traceback import print_exception

from main import CONFIG
from core.templates import ErrorMessage, SuccessfulMessage


class BotCommand(commands.Command):
    @property
    def signature(self):
        """
        Возвращает аргументы команды
        """

        if self.usage is not None:
            result = [f"<{key}>" if params[1] is True else f"[{key}]" for key, params in self.usage.items()]

            return " ".join(result)
        else:
            return ""


class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.client = bot

    @commands.Cog.listener(name="on_command_error")
    async def error_handler(self, ctx, error):
        """
        Обработка ошибок, вызванные во время использования бота

        :param ctx: context
        :param error: ошибка
        """

        if hasattr(ctx.command, "on_error"):
            return

        error = getattr(error, "original", error)
        ignored = (commands.CommandNotFound, commands.CheckFailure)  # ошибки, которые должны игнорироваться

        if isinstance(error, ignored):
            return
        elif isinstance(error, commands.MissingPermissions):
            message = ErrorMessage("У вас недостаточно прав для использования данной команды")
        elif isinstance(error, commands.BadArgument) and re.search(r"Member \"\w+\" not found", error.args[0]):
            message = ErrorMessage("Я не нашёл указанного участника на сервере")
        elif isinstance(error, commands.MissingRequiredArgument) and \
                "user is a required argument that is missing." == error.args[0]:
            message = ErrorMessage("Вы не ввели пользователя")
        elif isinstance(error, commands.CommandError):
            message = ErrorMessage(str(error))
        else:
            print_exception(type(error), error, error.__traceback__)

            return

        await ctx.send(embed=message)


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

                raise CommandError("Я не могу поставить префикс, который больше 16 символов")
            elif prefix == last_prefix or (last_prefix is None and prefix == "."):
                cursor.close()
                db.close()

                raise CommandError("Вы уже используете данный префикс")

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

                raise CommandError("Вы не ввели префикс")
            else:
                cursor.execute("DELETE FROM servers WHERE id=%(server_id)s", data_sql)

                message = SuccessfulMessage("Я успешно сбросил префикс на стандартный")

        await ctx.send(embed=message)

        cursor.close()
        db.close()
