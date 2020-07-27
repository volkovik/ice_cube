import discord
from itertools import groupby
from discord import Embed
from discord.ext.commands import HelpCommand


class ErrorMessage(Embed):
    """
    Embed сообщение об ошибке

    :param message: текст сообщения
    """

    def __init__(self, message):
        super().__init__(title=":x: Ошибка", description=message, color=0xDD2E44)


class SuccessfulMessage(Embed):
    """
    Embed сообщение об успешной работе

    :param message: текст сообщения
    """

    def __init__(self, message):
        super().__init__(title=":white_check_mark: Выполнено", description=message, color=0x77B255)


class Help(HelpCommand):
    """
    Производный класс, который формирует вид команды help
    """

    def __init__(self, **options):
        """
        Настройка команды help

        :param **options: некоторые настройки
        """

        self.width = options.pop('width', 80)  # максимальное количество символов для описания
        self.sort_commands = options.pop('sort_commands', True)  # сортировка команд и категорий по алфавиту
        self.commands_heading = options.pop('commands_heading', "Команды")  # название колонки для групп команд
        self.embed = discord.Embed()  # Embed-шаблон

        super().__init__(**options)

        self.command_attrs["hidden"] = True  # не показывать команды, которые заведомо скрыты

    def shorten_text(self, text):
        """
        Сокращение строки до определённого количества символов

        :param text: строка
        :return: обработанная строка или та же строка, если строка меньше или равна лимиту символов
        """

        if text:
            text = text[0].lower() + text[1:]  # сделать первую букву маленькой

        # если описание превышает ограничение по символам, то сократить текст и поставить в конце троеточие
        if len(text) > self.width:
            text = text[0:self.width - 3] + '...'

        return text

    def get_destination(self):
        """
        Получение канала для отправки сообщения

        :return: текстовый канал сервера
        """

        ctx = self.context

        return ctx.channel

    async def prepare_help_command(self, ctx, command=None):
        """
        Очистка Embed-шаблона
        """

        self.embed = discord.Embed()

    def get_command_signature(self, command, args=False):
        """
        Получение строки с командой, текущим префиксом и, если usage=True, ещё аргументы команды

        :param command: команда
        :param args: возвращать ли команду с аргументами
        :return: строка c информацией о команде
        """

        string = f"{self.clean_prefix}{command}"

        if args and command.signature:
            string += " " + command.signature

        return string

    async def send_bot_help(self, mapping):
        """
        Отправка списка команд бота в текстовый канал
        """

        ctx = self.context

        # Удаленяем все команды без категории и сортируем по категориям
        get_category = lambda c: c.cog_name + ":"
        filtered = await self.filter_commands(filter(lambda c: c.cog_name is not None, ctx.bot.commands), sort=True,
                                              key=get_category)
        commands = groupby(filtered, key=get_category)

        self.embed.title = self.commands_heading

        for category, cmds in commands:
            commands_descriptions = []

            for cmd in cmds:
                commands_descriptions.append(f"`{self.get_command_signature(cmd)}` - "
                                             f"{self.shorten_text(cmd.short_doc)}")

            self.embed.add_field(
                name=category,
                value="\n".join(commands_descriptions),
                inline=False
            )

        await self.get_destination().send(embed=self.embed)

    async def send_command_help(self, command):
        """
        Отправка информации о команде в тектовый канал

        :param command: команда бота
        """

        self.embed.title = f"Команда \"{command.name}\""

        self.embed.description = f"{self.get_command_signature(command, args=True)} - " \
                                 f"{self.shorten_text(command.short_doc)}"

        if command.usage:
            self.embed.add_field(
                name="Аргументы",
                value=" ".join([(f"`<{key}>`" if params[1] is True else f"[{key}]") + f" - {params[0]}" for key, params in
                                command.usage.items()])
            )

        self.embed.set_footer(text="Виды аргументов: <arg> - обязательный, [arg] - необязятельный")

        await self.context.send(embed=self.embed)

    async def send_group_help(self, group):
        """
        Отправка информации о группе команды в тектовый канал

        :param group: группа команд
        """

        self.embed.title = f"Группа команд \"{group.name}\""
        self.embed.description = f"`{self.get_command_signature(group, args=True)}` - " \
                                 f"{self.shorten_text(group.short_doc)}"
        self.embed.set_footer(text="Виды аргументов: <arg> - обязательный, [arg] - необязятельный")

        if group.all_commands:
            for _, cmd in group.all_commands.items():
                command_doc = f"`{self.get_command_signature(cmd, args=True)}` - {self.shorten_text(cmd.short_doc)}"

                if cmd.usage:
                    command_doc += "\n**Аргументы**\n"
                    command_doc += " ".join([(f"`<{key}>`" if params[1] is True else f"`[{key}]`") + f" - {params[0]}"
                                             for key, params in cmd.usage.items()])

                self.embed.add_field(
                    name=f"Команда \"{cmd.name}\"",
                    value=command_doc,
                    inline=False
                )

        await self.context.send(embed=self.embed)

    async def command_not_found(self, name):
        """
        Текст ошибки, при ненахождении введённой команды

        :param name: название команды
        :return: сообщение об ошибке
        """

        return f"Я не нашёл команду `{name}`"

    async def send_error_message(self, error):
        """
        Отправка ошибок, вызванные использованием команды

        :param error: сообщение об ошибке
        """

        self.embed.title = ":x: Ошибка"
        self.embed.description = error
        self.embed.colour = 0xDD2E44

        await self.get_destination().send(embed=self.embed)
