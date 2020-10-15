import asyncio
import os
from enum import Enum
from itertools import groupby
from typing import Union

import discord
from discord import Embed
from discord.ext import commands
from discord.ext.commands import HelpCommand

from core.commands import Command, Group


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
    embed = DefaultEmbed()
    gitbook_link = os.environ.get("GITBOOK_LINK")

    def get_destination(self) -> discord.TextChannel:
        """Returns channel for sending help"""
        return self.context.channel

    async def prepare_help_command(self, ctx: commands.Context, command: Union[Command, Group] = None):
        """Create a new Embed"""
        self.embed = DefaultEmbed()

    def get_command_signature(self, command: Union[Command, Group], args=False) -> str:
        """
        Returns command signature

        :param command: bot's command
        :param args: include command's arguments in signature
        """

        string = f"{self.clean_prefix}{command}"

        if args and command.signature:
            string += " " + command.signature

        return string

    def get_gitbook_link(self, command: Union[Command, Group]) -> str:
        """Returns link of command documentation in gitbook"""
        return self.gitbook_link + f"{'-'.join(command.cog_name.split())}/" + "/".join(str(command).split())

    async def send_bot_help(self, mapping):
        """Sends list of bot's commands"""
        ctx = self.context

        # delete all commands without category and sort them
        def get_category(command):
            return command.cog.ru_name.capitalize()

        filtered = await self.filter_commands(filter(
            lambda c: c.cog_name is not None, ctx.bot.commands),
            sort=True,
            key=get_category
        )
        categories = groupby(filtered, key=get_category)

        # configure embed
        self.embed.title = ":bookmark: Команды"
        self.embed.description = f"Напишите `{self.clean_prefix}help <команда>` для подробной информации. " \
                                 f"Либо нажмите на нужную команду ниже"

        if self.gitbook_link:
            self.embed.url = self.gitbook_link

        for category, cmds in categories:
            if self.gitbook_link:
                text = [f"[`{self.get_command_signature(i)}`]({self.get_gitbook_link(i)})" for i in cmds]
            else:
                text = [f"`{self.get_command_signature(i)}`" for i in cmds]

            self.embed.add_field(
                name=category,
                value=" ".join(text),
                inline=False
            )

        await self.get_destination().send(embed=self.embed)

    def make_help(self, command: Union[Command, Group]):
        """Configure Embed for command or group of commands"""
        self.embed.title = f":bookmark: Команда \"{command.name}\""
        self.embed.description = f"`{self.get_command_signature(command, args=True)}` - {command.short_doc}"
        if self.gitbook_link:
            self.embed.url = self.get_gitbook_link(command)

        if command.notes:
            self.embed.add_field(
                name="Примечание",
                value="\n".join([f"**{i}**" for i in command.notes])
            )

        if command.aliases:
            self.embed.description += "\n **Данную команду также можно вызвать как:** " + ", ".join(
                [f"`{self.clean_prefix}{i}`" for i in command.aliases]
            )

        if command.arguments:
            self.embed.set_footer(text="Виды аргументов: <arg> - обязательный, [arg] - необязятельный")

            args = []

            for k, v in command.arguments.items():
                args.append((f"`<{k}>`" if v[1] is True else f"`[{k}]`") + f" - {v[0]}" +
                            (f"\n**{v[2]}**" if v[2] else ""))

            self.embed.add_field(
                name="Аргументы",
                value="\n".join(args),
                inline=False
            )

        if command.examples:
            self.embed.add_field(
                name="Примеры",
                value="\n".join([i.format(prefix=self.clean_prefix) for i in command.examples]),
                inline=False
            )

    async def send_command_help(self, command: Command):
        """
        Sends info about command

        :param command: bot's command
        """
        self.make_help(command)
        await self.context.send(embed=self.embed)

    async def send_group_help(self, group: Group):
        """
        Sends info about group of commands

        :param group: group of commands
        """
        self.make_help(group)
        await self.context.send(embed=self.embed)

    async def send_error_message(self, error: str):
        """
        Sends error message

        :param error: info about error
        """
        self.embed.title = ":x: Ошибка"
        self.embed.description = error
        self.embed.colour = 0xDD2E44

        await self.get_destination().send(embed=self.embed)

    async def command_not_found(self, name: str) -> str:
        """
        Returns error message when command doesn't exist

        :param name: name of command that user tried to find
        """
        return f"Я не нашёл команду `{name}`"

    async def subcommand_not_found(self, command: Union[Command, Group], string: str) -> str:
        """
        Returns error message when subcommand doesn't exist

        :param command: bot's command
        :param string: name of subcommand that user tried to find
        """
        return f"Команда `{command.qualified_name} {string}` не найдена"
