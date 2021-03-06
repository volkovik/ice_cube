import asyncio
from enum import Enum
from itertools import groupby
from discord import Embed
from discord.ext import commands
from discord.ext.commands import HelpCommand


async def send_message_with_reaction_choice(client: commands.Bot, ctx: commands.Context, embed: Embed, emojis: dict):
    """
    Прислать сообщение с выбором ответа в виде реакций

    :param client: бот
    :type client: commands.Bot
    :param ctx: информация о сообщении
    :type ctx: commands.Context
    :param embed: Embed интерфейс
    :type embed: Embed
    :param emojis: словарь со эмоджи
    :type emojis: dict
    :return: сообщение и выбор пользователя
    :rtype: discord.Message and str
    """

    message = await ctx.send(embed=embed)

    for e in emojis.values():
        await message.add_reaction(e)

    def check(react, user):
        return ctx.author == user and str(react) in emojis.values()

    try:
        reaction, _ = await client.wait_for('reaction_add', timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await message.clear_reactions()
        await message.edit(embed=ErrorMessage("Превышено время ожидания"))
        return message, None
    else:
        await message.clear_reactions()

        answer = None

        for k, v in emojis.items():
            if v == str(reaction.emoji):
                answer = k
                break

        return message, answer


class PermissionsForRoom(Enum):
    banned = False
    default = None
    allowed = True


class DefaultEmbed(Embed):
    """
    Embed сообщение с цветом по стандарту
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("color", 0xAEE4FC)
        super().__init__(**kwargs)


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
        self.embed = DefaultEmbed()  # Embed-шаблон

        super().__init__(**options)

        self.command_attrs["hidden"] = True  # не показывать команды, которые заведомо скрыты

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

        self.embed = DefaultEmbed()

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
                commands_descriptions.append(f"`{self.get_command_signature(cmd)}` - {cmd.short_doc}")

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

        self.embed.description = f"`{self.get_command_signature(command, args=True)}` - {command.short_doc}"

        if command.usage:
            self.embed.set_footer(text="Виды аргументов: <arg> - обязательный, [arg] - необязятельный")
            self.embed.add_field(
                name="Аргументы",
                value="\n".join([(f"`<{key}>`" if params[1] is True else f"`[{key}]`") + f" - {params[0]}"
                                 for key, params in command.usage.items()])
            )

        if command.usage:
            self.embed.set_footer(text="Виды аргументов: <arg> - обязательный, [arg] - необязятельный")
            self.embed.add_field(
                name="Аргументы",
                value="\n".join([(f"`<{key}>`" if params[1] is True else f"`[{key}]`") + f" - {params[0]}"
                                 for key, params in command.usage.items()])
            )

        await self.context.send(embed=self.embed)

    async def send_group_help(self, group):
        """
        Отправка информации о группе команды в тектовый канал

        :param group: группа команд
        """

        self.embed.title = f"Команда \"{group.name}\""
        self.embed.description = f"`{self.get_command_signature(group, args=True)}` - {group.short_doc}"

        if group.aliases:
            self.embed.description += "\n Данную команду также можно вызвать как: " + ", ".join(
                [f"`{self.clean_prefix}{i}`" for i in group.aliases]
            )

        if group.usage:
            self.embed.set_footer(text="Виды аргументов: <arg> - обязательный, [arg] - необязятельный")
            self.embed.add_field(
                name="Аргументы",
                value="\n".join([(f"`<{key}>`" if params[1] is True else f"`[{key}]`") + f" - {params[0]}"
                                 for key, params in group.usage.items()])
            )

        if group.commands:
            commands = []

            for cmd in group.commands:
                try:
                    if await cmd.can_run(self.context):
                        commands.append(f"`{self.get_command_signature(cmd, args=False)}` - {cmd.short_doc}")
                except commands.CommandError:
                    pass

            if commands:
                self.embed.add_field(
                    name=f"Дополнительные команды",
                    value="\n".join(commands),
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

    async def subcommand_not_found(self, command, string):
        """
        Текст ошибки, при ненахождении введённой сабкоманды

        :param command: команда
        :param string: название ошибочной сабкоманды, которую пытались вызвать
        :return: сообщение об ошибке
        """

        return f"Команда `{command.qualified_name} {string}` не найдена"

    async def send_error_message(self, error):
        """
        Отправка ошибок, вызванные использованием команды

        :param error: сообщение об ошибке
        """

        self.embed.title = ":x: Ошибка"
        self.embed.description = error
        self.embed.colour = 0xDD2E44

        await self.get_destination().send(embed=self.embed)
