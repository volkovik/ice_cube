from discord.ext import commands


class Command(commands.Command):
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


class Group(commands.Group):
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


class Cog(commands.Cog):
    def __init__(self, bot):
        self.client = bot
        self.ru_name = self.qualified_name
