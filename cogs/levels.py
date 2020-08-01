import discord
import datetime
import asyncio
import cmath
import random
import sqlalchemy
from discord.ext import commands
from discord.ext.commands import CommandError
from discord.ext.commands import CooldownMapping, Cooldown
from sqlalchemy.orm import sessionmaker
from string import Template

from main import ENGINE_DB
from core.commands import BotCommand, BotGroupCommands
from core.templates import SuccessfulMessage, ErrorMessage
from core.database import UserLevel, ServerSettingsOfLevels


DEFAULT_LEVELUP_MESSAGE = "$member_mention получил `$level уровень`"


def get_exp_for_level(level: int):
    """
    Выдаёт количество опыта, необходимого для получения n уровня

    :param level: n уровень
    :type level: int
    :return: кол-во опыта
    :rtype: int
    """

    if level <= 0:
        return 0
    else:
        return 5 * level ** 2 + 100 * level + 200


def get_level(exp: int):
    """
    Выдаёт достигнутый уровень по количеству опыта

    :param exp: количество опыта
    :type exp: int
    :return: уровень
    :rtype: int
    """

    a = 5
    b = 100
    c = 200 - exp

    D = b ** 2 - 4 * a * c

    x = ((-b + cmath.sqrt(D)) / (2 * a)).real

    if x < 0:
        return 0
    else:
        return int(x)


def get_levelup_message(server):
    """
    Выдать сообщение при получении нового уровня

    :param server: Сервер для которого нужно получить сообщение
    :type server: discord.Guild
    :return: Сообщение из базы данных или по умолчанию
    :rtype: str
    """

    Session = sessionmaker(bind=ENGINE_DB)
    session = Session()

    settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()

    session.close()

    if settings.levelup_message is None:
        return DEFAULT_LEVELUP_MESSAGE
    else:
        return settings.levelup_message


def format_levelup_message(text, ctx, level):
    """
    Форматировать сообщение по заданным переменным

    :param text: Текст, которое нужно форматировать
    :type text: str
    :param ctx: Данные об сообщении
    :type ctx: discord.Context
    :param level: Уровень, который был достигнут
    :type level: int
    :return: Форматированное сообщение
    :rtype: str
    """

    return Template(text).safe_substitute(
        member_name=ctx.author.display_name,
        member_mention=ctx.author.mention,
        level=level
    )


def get_user_experience(server, user):
    """
    Выдаёт количество опыта у пользователя на сервере из базы данных

    :param server: сервер, на котором находится пользователь
    :type server: discord.Guild
    :param user: пользователь, у которого нужно узнать опыт
    :type user: discord.User or discord.Member
    :return: количество опыта
    :rtype: int
    """

    Session = sessionmaker(bind=ENGINE_DB)
    session = Session()

    user_experience = session.query(UserLevel).filter_by(server_id=str(server.id), user_id=str(user.id)).first()

    if user_experience is None:
        experience = 0
    else:
        experience = user_experience.experience

    session.close()

    return experience


def update_user_experience(server, user, exp):
    """
    Обновляет количество опыта пользователя в базе данных

    :param server: сервер, на котором находится пользователь
    :type server: discord.Guild
    :param user: пользователь, которому нужно обновить опыт
    :type user: discord.User or discord.Member
    :param exp: количество опыта, которое нужно добавить
    :type exp: int
    """

    Session = sessionmaker(bind=ENGINE_DB)
    session = Session()

    db_kwargs = {
        "server_id": str(server.id),
        "user_id": str(user.id)
    }

    user_experience = session.query(UserLevel).filter_by(**db_kwargs).first()

    if user_experience is None:
        session.add(UserLevel(**db_kwargs, experience=exp))
    else:
        user_experience.experience = user_experience.experience + exp

    session.commit()
    session.close()


def level_system_is_on(server):
    """
    Проверка, включёна ли система уровней на сервере

    :param server: сервер Discord
    :type server: discord.Guild
    :return: True, если включена, иначе False
    :rtype: bool
    """

    Session = sessionmaker(bind=ENGINE_DB)
    session = Session()

    server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()

    if server_settings is None:
        is_on = False
    else:
        is_on = True

    session.close()

    return is_on


def check_level_system_is_on():
    """
    Декоратор для discord.Command, с проверкой, включена ли система уровней на сервере
    """

    def predicate(ctx):
        return level_system_is_on(ctx.guild)

    return commands.check(predicate)


class Level(commands.Cog, name="Уровни"):
    def __init__(self, bot):
        self.client = bot
        self._buckets = CooldownMapping(Cooldown(1, 60, commands.BucketType.member))

    @commands.Cog.listener(name="on_message")
    async def when_message(self, message):
        author = message.author
        server = message.guild

        if not author.bot and level_system_is_on(server):
            if self._buckets.valid:
                current = message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp()
                bucket = self._buckets.get_bucket(message, current)
                retry_after = bucket.update_rate_limit(current)

                if retry_after:
                    return

                user_exp = get_user_experience(server, author)
                add_exp = random.randint(15, 30)

                update_user_experience(server, author, add_exp)

                next_level = get_level(user_exp) + 1

                if get_exp_for_level(next_level) <= user_exp + add_exp:
                    await message.channel.send(
                        format_levelup_message(get_levelup_message(message.guild), message, next_level)
                    )

    @commands.command(
        cls=BotCommand, name="rank",
        usage={"пользователь": ("упоминание или ID участника сервера, чтобы посмотреть его профиль", False)}
    )
    @check_level_system_is_on()
    async def get_current_level(self, ctx, user: commands.MemberConverter = None):
        """
        Показывает уровень пользователя
        """

        if user is None:
            user = ctx.author

        user_exp = get_user_experience(ctx.guild, user)
        user_level = get_level(user_exp)

        message = discord.Embed()
        message.add_field(
            name="Уровень",
            value=str(user_level)
        )
        message.add_field(
            name="До следующего уровня",
            value=f"{user_exp - get_exp_for_level(user_level)}/"
                  f"{get_exp_for_level(user_level + 1) - get_exp_for_level(user_level)}"
        )
        message.add_field(
            name="Всего опыта",
            value=str(user_exp)
        )
        message.set_author(name=user.display_name, icon_url=user.avatar_url_as(static_format="jpg"))

        await ctx.send(embed=message)

    @commands.command(
        cls=BotCommand, name="leaders"
    )
    @check_level_system_is_on()
    async def get_leaders_on_server(self, ctx):
        server = ctx.guild

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        users = session.query(UserLevel).filter_by(
            server_id=str(server.id)
        ).order_by(sqlalchemy.desc(UserLevel.experience)).all()

        top = []

        for user_from_db in users:
            if len(top) == 10:
                break

            user = server.get_member(int(user_from_db.user_id))

            if user is None:
                session.delete()
            else:
                user_exp = user_from_db.experience

                top.append(f"**#{len(top) + 1}:** `{user.display_name}`\n"
                           f"Уровень: {get_level(user_exp)} | Опыт: {user_exp}")

        embed = discord.Embed(
            title="Топ пользователей",
            description="\n".join(top)
        )

        session.commit()
        session.close()

        await ctx.send(embed=embed)

    @commands.group(name="setlevels", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def levels_settings(self, ctx):
        """
        Настройка системы уровней на сервере
        """

        server = ctx.guild

        if level_system_is_on(server):
            embed = discord.Embed(
                title="Приватные комнаты",
                description=f"На данный момент на этом сервере установлена система уровней. Чтобы их "
                            f"выключить, используйте команду `{ctx.prefix}setlevels disable`\n\n"
                            f"**Будьте бдительны, когда выключаете систему! Удалятся все настройки и сбросится опыт у "
                            f"каждого участника сервера!**"
            )
        else:
            embed = discord.Embed(
                title="Система уровней",
                description=f"На данный момент на этом сервере нет системы уровней. Чтобы их включить, используйте "
                            f"команду `{ctx.prefix}setlevels enable`"
            )

        await ctx.send(embed=embed)

    @levels_settings.command(cls=BotCommand, name="enable")
    @commands.has_permissions(administrator=True)
    async def enable_level_system(self, ctx):
        """
        Включить систему уровней на сервере
        """

        server = ctx.guild

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        db_kwargs = {
            "server_id": str(server.id)
        }

        server_settings = session.query(ServerSettingsOfLevels).filter_by(**db_kwargs).first()

        if server_settings is not None:
            session.close()
            raise CommandError("На вашем сервере уже включена система уровней")
        else:
            session.add(ServerSettingsOfLevels(**db_kwargs))

            message = SuccessfulMessage("Я включил систему уровней на вашем сервере")

            session.commit()
            session.close()

            await ctx.send(embed=message)

    @levels_settings.command(cls=BotCommand, name="disable")
    @commands.has_permissions(administrator=True)
    async def disable_level_system(self, ctx):
        """
        Выключить систему уровней на сервере
        """

        server = ctx.guild

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        db_kwargs = {
            "server_id": str(server.id)
        }

        server_settings = session.query(ServerSettingsOfLevels).filter_by(**db_kwargs).first()

        if server_settings is None:
            session.close()
            raise CommandError("На вашем сервере нет системы уровней")
        else:
            emojis = {
                "accept": "✅",
                "cancel": "🚫"
            }

            embed = discord.Embed(
                title="Выключение системы уровней",
                description=f"Вы уверены, что хотите выключить систему уровней?\n"
                            f"**Это повлечёт удалению всех настроек, а также к сбросу опыта у каждого участника "
                            f"сервера!**\n\n"
                            f"{emojis['accept']} - Да, выключить\n"
                            f"{emojis['cancel']} - Нет, отменить выключение"
            )

            message = await ctx.send(embed=embed)

            await message.add_reaction(emojis["accept"])
            await message.add_reaction(emojis["cancel"])

            def check(reaction, user):
                return ctx.author == user and str(reaction) in emojis.values()

            try:
                reaction, _ = await self.client.wait_for('reaction_add', timeout=60.0, check=check)
            except asyncio.TimeoutError:
                await message.edit(embed=ErrorMessage("Превышено время ожидания"))
                await message.clear_reactions()
            else:
                if str(reaction) == emojis["accept"]:
                    session.delete(server_settings)
                    session.query(UserLevel).filter_by(**db_kwargs).delete()
                    session.commit()

                    embed = SuccessfulMessage("Я выключил систему уровней на вашем сервере")
                else:
                    embed = discord.Embed(
                        title=":x: Отменено",
                        description="Вы отменили удаление системы уровней на этом сервере",
                        color=0xDD2E44
                    )

                await message.edit(embed=embed)
                await message.clear_reactions()

            session.close()

    @levels_settings.group(name="message", invoke_without_command=True)
    @check_level_system_is_on()
    async def levelup_message(self, ctx):
        """
        Настройка сообщения при получении нового уровня
        """

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()

        session.close()

        key_words_info = "Редактируя сообщение, вы можете использовать ключевые слова, например: `$member_mention`, " \
                         "чтобы упомянуть пользователя\n" \
                         "**Полный список ключевых слов:**\n" \
                         "`$member_name` - имя пользователя\n" \
                         "`$member_mention` - упомянуть пользователя\n" \
                         "`$level` - достигнутый уровень"

        if settings.levelup_message is None:
            text = DEFAULT_LEVELUP_MESSAGE
            additional_info = "Вы можете изменить это сообщение с помощью команды `>setlevels message edit`.\n"
        else:
            text = settings.levelup_message
            additional_info = "Вы можете изменить это сообщение с помощью команды `>setlevels message edit` или " \
                              "сбросить на стандартное сообщение с помощью команды `>setlevels message edit default`\n"

        embed = discord.Embed(
            title="Сообщение при получении нового уровня",
            description=format_levelup_message(text, ctx, random.randint(1, 50))
        )
        embed.add_field(
            name="Дополнительная информация",
            value=additional_info + key_words_info
        )

        await ctx.send(embed=embed)

    @levelup_message.group(
        cls=BotGroupCommands, name="edit", invoke_without_command=True,
        usage={"текст": ("текст, который будет отправляться по достижению нового уровня пользователем", True)}
    )
    async def edit_levelup_message(self, ctx, *, text=None):
        """
        Редактировать текст сообщения
        """

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()

        if text is None:
            raise CommandError("Вы не ввели текст")
        else:
            settings.levelup_message = text

        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы изменили текст сообщения"))

    @edit_levelup_message.command(cls=BotCommand, name="default")
    async def reset_levelup_message(self, ctx):
        """
        Сбросить текст сообщения по умолчанию
        """

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()

        if settings.levelup_message is None:
            raise CommandError("Вы до этого не изменяли текст сообщения")
        else:
            settings.levelup_message = None

        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы сбросил текст сообщения"))


def setup(bot):
    bot.add_cog(Level(bot))
