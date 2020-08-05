import discord
import datetime
import asyncio
import cmath
import random
import sqlalchemy
from discord.ext import commands
from discord.ext.commands import CommandError
from discord.ext.commands import CooldownMapping, Cooldown
from string import Template

from main import Session
from core.commands import BotCommand, BotGroupCommands
from core.templates import SuccessfulMessage, ErrorMessage
from core.database import UserLevel, ServerSettingsOfLevels, ServerAwardOfLevels


DEFAULT_LEVELUP_MESSAGE_FOR_SERVER = "$member_mention получил `$level уровень`"
DEFAULT_LEVELUP_MESSAGE_FOR_DM = "Вы получили `$level уровень` на **$server_name**"


def get_experience(level: int):
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
        server_name=ctx.guild.name,
        level=level
    )

# Проверки для команд


def level_system_is_enabled(session, ctx):
    server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()

    return server_settings is not None


def level_system_is_on():
    def decorator(ctx):
        session = Session()
        is_on = level_system_is_enabled(session, ctx)
        session.close()

        return is_on

    return commands.check(decorator)


def level_system_is_off():
    def predicate(ctx):
        session = Session()
        is_off = not level_system_is_enabled(session, ctx)
        session.close()

        return is_off

    return commands.check(predicate)


def notify_of_levelup_is_enabled(session, ctx):
    server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()

    return server_settings.notify_of_levelup


def notify_of_levelup_is_on():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            return False
        is_on = notify_of_levelup_is_enabled(session, ctx)
        session.close()

        return is_on

    return commands.check(predicate)


def notify_of_levelup_is_off():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            return False
        is_off = not notify_of_levelup_is_enabled(session, ctx)
        session.close()

        return is_off

    return commands.check(predicate)


def levelup_message_is_custom():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx) or not notify_of_levelup_is_enabled(session, ctx):
            return False
        server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return server_settings.levelup_message is not None

    return commands.check(predicate)


def levelup_message_destination_is_not_dm():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx) or not notify_of_levelup_is_enabled(session, ctx):
            return False
        server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return not server_settings.levelup_message_dm

    return commands.check(predicate)


def levelup_message_destination_is_not_current():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx) or not notify_of_levelup_is_enabled(session, ctx):
            return False
        server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return server_settings.levelup_message_channel_id is not None or server_settings.levelup_message_dm

    return commands.check(predicate)


def level_awards_exists():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            return False
        server_awards = session.query(ServerAwardOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        return True if server_awards is not None else False

    return commands.check(predicate)


class Level(commands.Cog, name="Уровни"):
    def __init__(self, bot):
        self.client = bot
        self._buckets = CooldownMapping(Cooldown(1, 60, commands.BucketType.member))

    @commands.Cog.listener(name="on_message")
    async def when_message(self, message):
        user = message.author

        if user.bot or message.channel.type is discord.ChannelType.private:
            return

        server = message.guild

        session = Session()
        server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()

        if server_settings is not None:
            if self._buckets.valid:
                current = message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp()
                bucket = self._buckets.get_bucket(message, current)
                retry_after = bucket.update_rate_limit(current)

                if retry_after:
                    return

                db_kwargs = {
                    "server_id": str(server.id),
                    "user_id": str(user.id)
                }

                user_db = session.query(UserLevel).filter_by(**db_kwargs).first()

                add_exp = random.randint(15, 30)

                if user_db is None:
                    user_db = UserLevel(**db_kwargs, experience=add_exp)
                    before_exp = 0
                    session.add(user_db)
                else:
                    before_exp = user_db.experience
                    user_db.experience += add_exp
                session.commit()

                next_level = get_level(before_exp) + 1

                if get_experience(next_level) <= user_db.experience and server_settings.notify_of_levelup:
                    del db_kwargs["user_id"]
                    awards = session.query(ServerAwardOfLevels).filter_by(**db_kwargs, level=next_level).all()

                    roles = []

                    if awards is not None:
                        for award in awards:
                            role = server.get_role(int(award.role_id))

                            if role is None:
                                session.delete(award)
                                session.commit()
                            else:
                                roles.append(role)

                    await user.add_roles(*roles)

                    if server_settings.levelup_message is not None:
                        text = server_settings.levelup_message
                    else:
                        if server_settings.levelup_message_dm:
                            text = DEFAULT_LEVELUP_MESSAGE_FOR_DM
                        else:
                            text = DEFAULT_LEVELUP_MESSAGE_FOR_SERVER

                    if server_settings.levelup_message_dm:
                        channel = user
                    else:
                        if server_settings.levelup_message_channel_id is None:
                            channel = message.channel
                        else:
                            channel = message.guild.get_channel(int(server_settings.levelup_message_channel_id))

                            if channel is None:
                                server_settings.levelup_message_channel_id = None
                                session.commit()

                                channel = message.channel

                    await channel.send(format_levelup_message(text, message, next_level))

        session.close()

    @commands.command(
        cls=BotCommand, name="rank",
        usage={"пользователь": ("упоминание или ID участника сервера, чтобы посмотреть его профиль", False)}
    )
    @level_system_is_on()
    async def get_current_level(self, ctx, user: commands.MemberConverter = None):
        """
        Показывает уровень пользователя
        """

        if user is None:
            user = ctx.author

        server = ctx.guild

        session = Session()
        user_db = session.query(UserLevel).filter_by(server_id=str(server.id), user_id=str(user.id)).first()
        session.close()

        if user_db is None:
            if user == ctx.author:
                raise CommandError("Вы ещё не числитесь в рейтинге участников")
            else:
                raise CommandError("Этот пользователь ещё не числится в рейтинге участников")

        experience = user_db.experience
        level = get_level(experience)

        message = discord.Embed()
        message.add_field(
            name="Уровень",
            value=str(level)
        )
        message.add_field(
            name="До следующего уровня",
            value=f"{experience - get_experience(level)}/"
                  f"{get_experience(level + 1) - get_experience(level)}"
        )
        message.add_field(
            name="Всего опыта",
            value=str(experience)
        )
        message.set_author(name=user.display_name, icon_url=user.avatar_url_as(static_format="jpg"))

        await ctx.send(embed=message)

    @commands.command(
        cls=BotCommand, name="leaders"
    )
    @level_system_is_on()
    async def get_leaders_on_server(self, ctx):
        server = ctx.guild

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
        Настройка рейтинга участников на сервере
        """

        embed = discord.Embed(
            title="Настройка рейтинга участников",
        )

        session = Session()
        if level_system_is_enabled(session, ctx):
            embed.description = f"**На сервере включён рейтинг участников**\n\n" \
                                f"Используйте команду `{ctx.prefix}help setlevels`, чтобы узнать о настройках\n" \
                                f"Если вы хотите выключить это, используйте команду `{ctx.prefix}help setlevels " \
                                f"disable`"
        else:
            embed.description = f"**На сервере нет рейтинга участников.**\n\n" \
                                f"Чтобы включить это, используйте команду `{ctx.prefix}help setlevels enable`"
        session.close()

        await ctx.send(embed=embed)

    @levels_settings.command(cls=BotCommand, name="enable")
    @commands.has_permissions(administrator=True)
    @level_system_is_off()
    async def enable_levels_system(self, ctx):
        """
        Включить рейтинг участников на сервере
        """

        session = Session()
        session.add(ServerSettingsOfLevels(server_id=str(ctx.guild.id)))
        session.commit()
        session.close()

        message = SuccessfulMessage(f"Вы включили рейтинг участников на сервере.\n"
                                    f"Используйте команду `{ctx.prefix}help setlevels`, чтобы узнать о "
                                    f"настройках")

        await ctx.send(embed=message)

    @levels_settings.command(cls=BotCommand, name="disable")
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def disable_levels_system(self, ctx):
        """
        Выключить рейтинг участников на сервере
        """

        server = ctx.guild

        session = Session()

        db_kwargs = {
            "server_id": str(server.id)
        }

        server_settings = session.query(ServerSettingsOfLevels).filter_by(**db_kwargs).first()

        emojis = {
            "accept": "✅",
            "cancel": "🚫"
        }

        embed = discord.Embed(
            title="Выключение рейтинга участников",
            description=f"Вы уверены, что хотите выключить рейтинг участников?\n\n"
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

                embed = SuccessfulMessage("Вы выключили рейтинг участников на сервере")
            else:
                embed = discord.Embed(
                    title=":x: Отменено",
                    description="Вы отменили выключение рейтинга участников на сервере",
                    color=0xDD2E44
                )

            await message.edit(embed=embed)
            await message.clear_reactions()

        session.close()

    @levels_settings.group(name="message", invoke_without_command=True)
    @level_system_is_on()
    async def levelup_message(self, ctx):
        """
        Настройка сообщения при получении нового уровня
        """

        server = ctx.guild

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()
        session.close()

        if not settings.notify_of_levelup:
            where_sends = "**Оповещение о новом уровне выключено**\n" \
                          "Чтобы включить оповещение, используйте команду `.setlevels message send enable`"
        else:
            if settings.levelup_message_dm:
                where_sends = "**Данное сообщение присылается в ЛС пользователю, получивший новый уровень**"
            else:
                if settings.levelup_message_channel_id is None:
                    channel = None
                else:
                    channel = server.get_channel(int(settings.levelup_message_channel_id))

                if channel is None:
                    settings.levelup_message_channel_id = None
                    session.commit()

                    where_sends = f"**Данное сообщение присылается в том же канеле, где пользователь получил новый " \
                                  f"уровень**"
                else:
                    where_sends = f"**Данное сообщение присылается в {channel.mention}, если пользователь получил " \
                                  f"новый уровень**"

            where_sends += f"\nВы можете изменить место отправки этого сообщение, используя команду " \
                           f"`{ctx.prefix}setlevels message send`. Подробнее о команде: " \
                           f"`{ctx.prefix}help setlevels message send`\n"

        if settings.levelup_message is None:
            if settings.levelup_message_dm:
                text = DEFAULT_LEVELUP_MESSAGE_FOR_DM
            else:
                text = DEFAULT_LEVELUP_MESSAGE_FOR_SERVER

            edit_info = "Вы можете изменить это сообщение с помощью команды `>setlevels message edit`. "
        else:
            text = settings.levelup_message
            edit_info = "Вы можете изменить это сообщение с помощью команды `>setlevels message edit` или " \
                        "сбросить на стандартное сообщение с помощью команды `>setlevels message edit default`. "

        edit_info += "Редактируя сообщение, вы можете использовать ключевые слова, например: `$member_mention`, " \
                     "чтобы упомянуть пользователя\n" \
                     "**Полный список ключевых слов:**\n" \
                     "`$member_name` - имя пользователя\n" \
                     "`$member_mention` - упомянуть пользователя\n" \
                     "`$server_name` - название сервера\n" \
                     "`$level` - достигнутый уровень"

        embed = discord.Embed(
            title="Сообщение при получении нового уровня",
            description=format_levelup_message(text, ctx, random.randint(1, 50))
        )
        embed.add_field(
            name="Где отправляется это сообщение?",
            value=where_sends,
            inline=False
        )
        embed.add_field(
            name="Как изменить это сообщение?",
            value=edit_info
        )

        await ctx.send(embed=embed)

    @levelup_message.command(name="enable")
    @notify_of_levelup_is_off()
    async def enable_notify_of_levelup(self, ctx):
        """
        Включить оповещение о новом уровне пользователя
        """

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        settings.notify_of_levelup = True
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы включили оповещение о новом уровне пользователя"))

    @levelup_message.command(name="disable")
    @notify_of_levelup_is_on()
    async def disable_notify_of_levelup(self, ctx):
        """
        Выключить оповещение о новом уровне пользователя
        """

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        settings.notify_of_levelup = False
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы выключили оповещение о новом уровне пользователя"))

    @levelup_message.group(
        cls=BotGroupCommands, name="edit", invoke_without_command=True,
        usage={"текст": ("текст, который будет отправляться по достижению нового уровня пользователем", True)}
    )
    @notify_of_levelup_is_on()
    async def edit_levelup_message(self, ctx, *, text=None):
        """
        Редактировать текст сообщения
        """

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
    @levelup_message_is_custom()
    async def reset_levelup_message(self, ctx):
        """
        Сбросить текст сообщения по умолчанию
        """

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        settings.levelup_message = None
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы сбросили текст сообщения"))

    @levelup_message.group(
        cls=BotGroupCommands, name="send", invoke_without_command=True,
        usage={"канал": ("упоминание, ID или название текстового канала", True)}
    )
    @notify_of_levelup_is_on()
    async def edit_levelup_message_destination(self, ctx, channel=None):
        """
        Изменить канал, где присылаются сообщения о получении нового уровня пользователями
        """

        if channel is None:
            await ctx.send_help(ctx.command)
            return

        converter = commands.TextChannelConverter()
        channel = await converter.convert(ctx, channel)

        server = ctx.guild

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()

        if not settings.levelup_message_dm and settings.levelup_message_channel_id is not None and \
                channel.id == int(settings.levelup_message_channel_id):
            session.close()
            raise CommandError("В данном канале уже и так присылаются сообщения о новом уровне")
        else:
            settings.levelup_message_dm = False
            settings.levelup_message_channel_id = str(channel.id)
            session.commit()

            await ctx.send(embed=SuccessfulMessage(f"Теперь сообщения о новом уровне будут присылаться в "
                                                   f"{channel.mention}"))

        session.close()

    @edit_levelup_message_destination.command(name="dm")
    @levelup_message_destination_is_not_dm()
    async def set_levelup_message_destination_as_user_dm(self, ctx):
        """
        Отправлять сообщение о новом уровне в личные сообщения пользователю
        """

        server = ctx.guild

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()
        settings.levelup_message_dm = True
        settings.levelup_message_channel_id = None
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Теперь сообщения о новом уровне будут присылаться в ЛС "
                                               "пользователю"))

    @edit_levelup_message_destination.command(name="current")
    @levelup_message_destination_is_not_current()
    async def set_levelup_message_destination_as_channel_where_reached_new_level(self, ctx):
        """
        Отправлять сообщение о новом уровне в том канале, где пользователь получил новый уровень
        """

        server = ctx.guild

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()
        settings.levelup_message_dm = False
        settings.levelup_message_channel_id = None
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Теперь сообщения о новом уровне будут присылаться в том же канале "
                                               "где пользователь достиг нового уровня"))

    @levels_settings.group(name="award", invoke_without_command=True)
    @level_system_is_on()
    async def awards_for_levels(self, ctx):
        """
        Настройка наград за достижение определённого уровня
        """

        server = ctx.guild

        session = Session()
        awards = session.query(ServerAwardOfLevels).filter_by(server_id=str(server.id)).all()
        session.close()

        sorted_awards = {}

        for award in awards:
            role = server.get_role(int(award.role_id))

            if role is None:
                session.delete(award)
                session.commit()
                continue

            if award.level in sorted_awards:
                sorted_awards[award.level].append(f"`{role.name}`")
            else:
                sorted_awards[award.level] = [f"`{role.name}`"]

        if sorted_awards:
            text = "\n".join([f"`{level} уровень`: {', '.join(roles)}" for level, roles in sorted_awards.items()])
        else:
            text = f"**Здесь ничего нет**\n\n" \
                   f"Вы можете добавить роль в качестве награды за достижение определённого уровня пользователем, " \
                   f"используя команду `.setlevels award add`"

        embed = discord.Embed(
            title="Награды за получение уровня",
            description=text
        )

        await ctx.send(embed=embed)

    @awards_for_levels.command(
        cls=BotCommand, name="add",
        usage={
            "роль": ("упоминание, ID или название текстового канала", True),
            "уровень": ("по достижению этого уровня, пользователь получит роль", True)
        }
    )
    @level_system_is_on()
    async def add_award_for_level(self, ctx, role: commands.RoleConverter = None, level: int = None):
        """
        Добавить роль в качестве награды за получение определённого уровня
        """

        if role is None:
            raise CommandError("Вы не ввели роль")
        elif level is None:
            raise CommandError("Вы не ввели уровень")

        session = Session()
        db_kwargs = {
            "server_id": str(ctx.guild.id),
            "role_id": str(role.id)
        }
        award = session.query(ServerAwardOfLevels).filter_by(**db_kwargs).first()

        if award is not None:
            session.close()
            raise CommandError("Эта роль уже используется в качестве награды.\n"
                               "Используйте `.setlevels award edit`, если вы хотите изменить её")
        else:
            award = ServerAwardOfLevels(**db_kwargs, level=level)
            session.add(award)
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage(f"Вы добавили роль `{role.name}` в качестве награды по достижению "
                                                   f"`{level} уровня`"))

    @awards_for_levels.command(
        cls=BotCommand, name="edit",
        usage={
            "роль": ("упоминание, ID или название текстового канала", True),
            "уровень": ("по достижению этого уровня, пользователь получит роль", True)
        }
    )
    @level_awards_exists()
    async def edit_award_for_level(self, ctx, role: commands.RoleConverter = None, level: int = None):
        """
        Редактировать требуемый уровень для получения роли
        """

        if role is None:
            raise CommandError("Вы не ввели роль")
        elif level is None:
            raise CommandError("Вы не ввели уровень")

        session = Session()
        award = session.query(ServerAwardOfLevels).filter_by(server_id=str(ctx.guild.id), role_id=str(role.id)).first()

        if award is None:
            session.close()
            raise CommandError("Этой роли нет в списке наград за уровень.\n"
                               "Используйте `.setlevels award add`, если вы хотите добавить её")
        elif level == award.level:
            session.close()
            raise CommandError("Эту роль и так можно получить, достигнув введённого уровня")
        else:
            award.level = level
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage(f"Теперь роль `{role.name}` можно получить по достижению `{level} "
                                                   f"уровня`"))

    @awards_for_levels.command(
        cls=BotCommand, name="remove",
        usage={"роль": ("упоминание, ID или название текстового канала", True)}
    )
    @level_awards_exists()
    async def remove_award_for_level(self, ctx, role: commands.RoleConverter = None):
        """
        Удалить роль из списка наград за уровень
        """

        if role is None:
            raise CommandError("Вы не ввели роль")

        session = Session()
        award = session.query(ServerAwardOfLevels).filter_by(server_id=str(ctx.guild.id), role_id=str(role.id)).first()

        if award is None:
            session.close()
            raise CommandError("Этой роли нет в списке наград за уровень.")
        else:
            session.delete(award)
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage(f"Вы удалили роль `{role.name}` из списка наград за уровень"))

    @awards_for_levels.command(name="reset")
    @level_awards_exists()
    async def reset_awards_for_levels(self, ctx):
        """
        Удалить все роли в качестве награды за уровень
        """

        session = Session()
        session.query(ServerAwardOfLevels).filter_by(server_id=str(ctx.guild.id)).delete()
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage(f"Вы удалили все награды за уровень"))


def setup(bot):
    bot.add_cog(Level(bot))
