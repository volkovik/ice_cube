import re
from discord.ext import commands
from traceback import print_exception

from core.templates import ErrorMessage, CustomError


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
        elif isinstance(error, CustomError):
            message = ErrorMessage(error.get_message())
        else:
            print_exception(type(error), error, error.__traceback__)

            return

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(ErrorHandler(bot))
