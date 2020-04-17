from discord.ext.commands import Command


class BotCommand(Command):
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
