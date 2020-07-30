from discord.ext import commands


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


class BotGroupCommands(commands.Group):
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
