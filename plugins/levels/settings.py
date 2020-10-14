import random
from discord.ext import commands
from discord.ext.commands import CommandError

from main import Session
from core.commands import Cog, Group, Command
from core.templates import SuccessfulMessage, DefaultEmbed as Embed, send_message_with_reaction_choice
from core.database import (UserLevel, ServerSettingsOfLevels, ServerAwardOfLevels, ServerIgnoreChannelsListOfLevels,
                           ServerIgnoreRolesListOfLevels)

from .utils import (format_levelup_message, level_system_is_enabled, level_system_is_on,
                    DEFAULT_LEVELUP_MESSAGE_FOR_SERVER, DEFAULT_LEVELUP_MESSAGE_FOR_DM)


def level_system_is_off():
    def predicate(ctx):
        session = Session()
        is_off = not level_system_is_enabled(session, ctx)
        session.close()

        return is_off

    return commands.check(predicate)


def notify_of_levelup_is_enabled(session, ctx):
    settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()

    return settings.notify_of_levelup if settings is not None else False


def notify_of_levelup_is_on():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            session.close()
            return False
        is_on = notify_of_levelup_is_enabled(session, ctx)
        session.close()

        return is_on

    return commands.check(predicate)


def notify_of_levelup_is_off():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            session.close()
            return False
        is_off = not notify_of_levelup_is_enabled(session, ctx)
        session.close()

        return is_off

    return commands.check(predicate)


def levelup_message_is_custom():
    def predicate(ctx):
        session = Session()
        if not (level_system_is_enabled(session, ctx) and notify_of_levelup_is_enabled(session, ctx)):
            session.close()
            return False
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return settings.levelup_message is not None if settings is not None else False

    return commands.check(predicate)


def levelup_message_destination_is_not_dm():
    def predicate(ctx):
        session = Session()
        if not (level_system_is_enabled(session, ctx) and notify_of_levelup_is_enabled(session, ctx)):
            session.close()
            return False
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return not settings.levelup_message_dm if settings is not None else False

    return commands.check(predicate)


def levelup_message_destination_is_not_current():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx) or not notify_of_levelup_is_enabled(session, ctx):
            session.close()
            return False
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return settings.levelup_message_channel_id is not None or settings.levelup_message_dm \
            if settings is not None else False

    return commands.check(predicate)


def level_awards_exist():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            session.close()
            return False
        award = session.query(ServerAwardOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return award is not None

    return commands.check(predicate)


def channels_in_ignore_list_exist():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            session.close()
            return False
        ignored = session.query(ServerIgnoreChannelsListOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return ignored is not None

    return commands.check(predicate)


def roles_in_ignore_list_exist():
    def predicate(ctx):
        session = Session()
        if not level_system_is_enabled(session, ctx):
            session.close()
            return False
        ignored = session.query(ServerIgnoreRolesListOfLevels).filter_by(server_id=str(ctx.guild.id)).first()
        session.close()

        return ignored is not None

    return commands.check(predicate)


class LevelsSettings(Cog, name="settings"):
    def __init__(self, bot):
        super(LevelsSettings, self).__init__(bot)
        self.ru_name = "настройки"

    @commands.group(name="setlevels", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def levels_settings(self, ctx):
        """
        Настройка рейтинга участников на сервере
        """

        embed = Embed(
            title="Настройка рейтинга участников",
        )

        session = Session()
        if level_system_is_enabled(session, ctx):
            embed.description = f"**На сервере включён рейтинг участников**\n\n" \
                                f"Используйте команду `{ctx.prefix}help setlevels`, чтобы узнать о настройках\n" \
                                f"Если вы хотите выключить это, используйте команду `{ctx.prefix}setlevels disable`"
        else:
            embed.description = f"**На сервере нет рейтинга участников.**\n\n" \
                                f"Чтобы включить это, используйте команду `{ctx.prefix}setlevels enable`"
        session.close()

        await ctx.send(embed=embed)

    @levels_settings.command(cls=Command, name="enable")
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

    @levels_settings.command(cls=Command, name="disable")
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

        embed = Embed(
            title="Выключение рейтинга участников",
            description=f"Вы уверены, что хотите выключить рейтинг участников?\n\n"
                        f"{emojis['accept']} - Да, выключить\n"
                        f"{emojis['cancel']} - Нет, отменить выключение"
        )

        message, answer = await send_message_with_reaction_choice(self.client, ctx, embed, emojis)

        if answer == "accept":
            session.delete(server_settings)
            session.query(UserLevel).filter_by(**db_kwargs).delete()
            session.commit()

            await message.edit(embed=SuccessfulMessage("Вы выключили рейтинг участников на сервере"))
        elif answer == "cancel":
            await message.edit(embed=SuccessfulMessage("Вы отменили выключение рейтинга участников"))

        session.close()

    @levels_settings.group(name="message", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
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

        embed = Embed(
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
    @commands.has_permissions(administrator=True)
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
    @commands.has_permissions(administrator=True)
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
        cls=Group, name="edit", invoke_without_command=True,
        usage={"текст": ("текст, который будет отправляться по достижению нового уровня пользователем", True)}
    )
    @commands.has_permissions(administrator=True)
    @notify_of_levelup_is_on()
    async def edit_levelup_message(self, ctx, *, text=None):
        """
        Редактировать текст сообщения
        """

        session = Session()
        settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first()

        if text is None:
            raise CommandError("Вы не ввели текст")
        elif len(text) > 256:
            raise CommandError("Вы не можете поставить текст больше 256 символов")
        else:
            settings.levelup_message = text

        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы изменили текст сообщения"))

    @edit_levelup_message.command(cls=Command, name="default")
    @commands.has_permissions(administrator=True)
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
        cls=Group, name="send", invoke_without_command=True,
        usage={"канал": ("упоминание, ID или название текстового канала", True)}
    )
    @commands.has_permissions(administrator=True)
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
    @commands.has_permissions(administrator=True)
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
    @commands.has_permissions(administrator=True)
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
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def awards_for_levels(self, ctx):
        """
        Настройка наград за достижение определённого уровня
        """

        server = ctx.guild

        session = Session()
        awards = session.query(ServerAwardOfLevels).filter_by(server_id=str(server.id)).all()
        session.close()

        higher_bot_role = server.me.roles[-1]

        sorted_awards = {}
        unavailable_awards = []

        for award in awards:
            role = server.get_role(int(award.role_id))

            if role is None:
                session.delete(award)
                session.commit()
                continue

            if role > higher_bot_role:
                unavailable_awards.append(f"`{role.name}`")
            else:
                if award.level in sorted_awards:
                    sorted_awards[award.level].append(f"`{role.name}`")
                else:
                    sorted_awards[award.level] = [f"`{role.name}`"]

        if sorted_awards:
            text = "\n".join([f"`{level} уровень`: {', '.join(roles)}" for level, roles in sorted_awards.items()])
        else:
            text = f"**Здесь ничего нет**"

            if not unavailable_awards:
                text += f"\n\nВы можете добавить роль в качестве награды за достижение определённого уровня " \
                        f"пользователем, используя команду `.setlevels award add`"

        embed = Embed(
            title="Награды за получение уровня",
            description=text
        )

        if unavailable_awards:
            embed.add_field(
                name="Недоступные роли",
                value=", ".join(unavailable_awards) +
                      "\n\nДанные роли не могут быть выданы ботом другим пользователям. Поставьте роль бота выше этих "
                      "ролей или удалите их с помощью команды `.setlevels award remove`"
            )

        await ctx.send(embed=embed)

    @awards_for_levels.command(
        cls=Command, name="add",
        usage={
            "роль": ("упоминание, ID или название роли", True),
            "уровень": ("по достижению этого уровня, пользователь получит роль", True)
        }
    )
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def add_award_for_level(self, ctx, role: commands.RoleConverter = None, level: int = None):
        """
        Добавить роль в качестве награды за получение определённого уровня
        """

        if role is None:
            raise CommandError("Вы не ввели роль")

        if level > 1000:
            raise CommandError("Вы не можете поставить уровень больше 1000-го")
        elif level < 0:
            raise CommandError("Вы не можете поставить уровень меньше нуля")

        server = ctx.guild

        session = Session()
        db_kwargs = {
            "server_id": str(server.id),
            "role_id": str(role.id)
        }
        award = session.query(ServerAwardOfLevels).filter_by(**db_kwargs).first()

        higher_bot_role = server.me.roles[-1]

        if award is not None:
            session.close()
            raise CommandError("Эта роль уже используется в качестве награды.\n"
                               "Используйте `.setlevels award edit`, если вы хотите изменить её")
        elif higher_bot_role < role:
            session.close()
            raise CommandError("Данная роль выше роли бота. Вы должны поставить роль бота выше, чем эта роль, чтобы "
                               "бот смог выдавать эту роль другим пользователям")
        else:
            if level is None:
                session.close()
                raise CommandError("Вы не ввели уровень")

            award = ServerAwardOfLevels(**db_kwargs, level=level)
            session.add(award)
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage(f"Вы добавили роль `{role.name}` в качестве награды по достижению "
                                                   f"`{level} уровня`"))

    @awards_for_levels.command(
        cls=Command, name="edit",
        usage={
            "роль": ("упоминание, ID или название роли", True),
            "уровень": ("по достижению этого уровня, пользователь получит роль", True)
        }
    )
    @commands.has_permissions(administrator=True)
    @level_awards_exist()
    async def edit_award_for_level(self, ctx, role: commands.RoleConverter = None, level: int = None):
        """
        Редактировать требуемый уровень для получения роли
        """

        if role is None:
            raise CommandError("Вы не ввели роль")
        elif level is None:
            raise CommandError("Вы не ввели уровень")

        if level > 1000:
            raise CommandError("Вы не можете поставить уровень больше 1000-го")
        elif level < 0:
            raise CommandError("Вы не можете поставить уровень меньше нуля")

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
        cls=Command, name="remove",
        usage={"роль": ("упоминание, ID или название текстового канала", True)}
    )
    @commands.has_permissions(administrator=True)
    @level_awards_exist()
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
    @commands.has_permissions(administrator=True)
    @level_awards_exist()
    async def reset_awards_for_levels(self, ctx):
        """
        Удалить все роли в качестве награды за уровень
        """

        session = Session()

        emojis = {
            "accept": "✅",
            "cancel": "🚫"
        }

        embed = Embed(
            title="Удаление всех наград",
            description=f"Вы уверены, что хотите удалить все роли из списка наград за уровень?\n\n"
                        f"{emojis['accept']} - Да, выключить\n"
                        f"{emojis['cancel']} - Нет, отменить удаление"
        )

        message, answer = await send_message_with_reaction_choice(self.client, ctx, embed, emojis)

        if answer == "accept":
            session.query(ServerAwardOfLevels).filter_by(server_id=str(ctx.guild.id)).delete()
            session.commit()

            embed = SuccessfulMessage("Вы удалили все награды за уровень")
            await message.edit(embed=embed)
        elif answer == "cancel":
            await message.edit(embed=SuccessfulMessage("Вы отменили удаление всех наград"))

        session.close()

    @levels_settings.group(name="ignore", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def ignore_list(self, ctx):
        """
        Настройка чёрного списка
        """

        server = ctx.guild

        session = Session()
        ignored_channels = session.query(ServerIgnoreChannelsListOfLevels).filter_by(server_id=str(server.id)).all()
        ignored_roles = session.query(ServerIgnoreRolesListOfLevels).filter_by(server_id=str(server.id)).all()

        verified_channels = []
        verified_roles = []

        if ignored_channels:
            for ignored in ignored_channels:
                channel = server.get_channel(int(ignored.channel_id))

                if channel is not None:
                    verified_channels.append(f"`{channel.name}`")
                else:
                    session.delete(ignored)
                    session.commit()

        if ignored_roles:
            for ignored in ignored_roles:
                role = server.get_role(int(ignored.role_id))

                if role is not None:
                    verified_roles.append(f"`{role.name}`")
                else:
                    session.delete(ignored)
                    session.commit()

        session.close()

        if verified_channels:
            channels_text = "\n".join(verified_channels)
        else:
            channels_text = f"**Здесь ничего нет**"

        if verified_roles:
            roles_text = "\n".join(verified_roles)
        else:
            roles_text = f"**Здесь ничего нет**"

        embed = Embed(
            title="Чёрный список"
        )
        embed.add_field(
            name="Текстовые каналы",
            value=channels_text,
            inline=True
        )
        embed.add_field(
            name="Роли",
            value=roles_text,
            inline=True
        )
        embed.add_field(
            name="Что такое чёрный список?",
            value=f"Добавляя текстовый канал в чёрный список, пользователи не смогут зарабатывать опыт в этом канале.\n"
                  f"Добавляя роль в чёрный список, пользователей с этой ролью не сможет зарабатывать опыт.\n"
                  f"Используйте `{ctx.prefix}help setlevels ignore`, чтобы узнать, как редактировать чёрный список",
            inline=False
        )

        await ctx.send(embed=embed)

    @ignore_list.group(name="channel", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def channel_ignore_list(self, ctx):
        """
        Настройка чёрного списка для текстовых каналов
        """

        await ctx.send_help(ctx.command)

    @channel_ignore_list.command(
        cls=Command, name="add",
        usage={"канал": ("упоминание, ID или название текстового канала", True)}
    )
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def add_channel_to_ignore_list(self, ctx, channel: commands.TextChannelConverter):
        """
        Добавить текстовый канал в чёрный список
        """

        if channel is None:
            raise CommandError("Вы не ввели тектовый канал")

        session = Session()
        db_kwargs = {
            "server_id": str(ctx.guild.id),
            "channel_id": str(channel.id)
        }
        ignored_channel = session.query(ServerIgnoreChannelsListOfLevels).filter_by(**db_kwargs).first()

        if ignored_channel is not None:
            session.close()
            raise CommandError("Данный текстовый канал уже в чёрном списке")
        else:
            ignored_channel = ServerIgnoreChannelsListOfLevels(**db_kwargs)
            session.add(ignored_channel)
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage("Вы добавили текстовый канал в чёрный список"))

    @channel_ignore_list.command(
        cls=Command, name="remove",
        usage={"канал": ("упоминание, ID или название текстового канала", True)}
    )
    @commands.has_permissions(administrator=True)
    @channels_in_ignore_list_exist()
    async def remove_channel_from_ignore_list(self, ctx, channel: commands.TextChannelConverter):
        """
        Удалить текстовый канал из чёрного списка
        """

        if channel is None:
            raise CommandError("Вы не ввели тектовый канал")

        session = Session()
        db_kwargs = {
            "server_id": str(ctx.guild.id),
            "channel_id": str(channel.id)
        }
        ignored_channel = session.query(ServerIgnoreChannelsListOfLevels).filter_by(**db_kwargs).first()

        if ignored_channel is None:
            session.close()
            raise CommandError("Данного текстового канала нет в чёрном списке")
        else:
            session.delete(ignored_channel)
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage("Вы удалили текстовый канал из чёрного списка"))

    @channel_ignore_list.command(name="reset")
    @commands.has_permissions(administrator=True)
    @channels_in_ignore_list_exist()
    async def reset_ignore_list_for_channels(self, ctx):
        """
        Сбросить чёрный список для текстовых каналов
        """

        session = Session()
        session.query(ServerIgnoreChannelsListOfLevels).filter_by(server_id=str(ctx.guild.id)).delete()
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы сбросили чёрный список для тектовых каналов"))

    @ignore_list.group(name="role", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def role_ignore_list(self, ctx):
        """
        Настройка чёрного списка для ролей
        """

        await ctx.send_help(ctx.command)

    @role_ignore_list.command(
        cls=Command, name="add",
        usage={"роль": ("упоминание, ID или название роли", True)}
    )
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def add_role_to_ignore_list(self, ctx, role: commands.RoleConverter):
        """
        Добавить роль в чёрный список
        """

        if role is None:
            raise CommandError("Вы не ввели роль")

        session = Session()
        db_kwargs = {
            "server_id": str(ctx.guild.id),
            "role_id": str(role.id)
        }
        ignored_role = session.query(ServerIgnoreRolesListOfLevels).filter_by(**db_kwargs).first()

        if ignored_role is not None:
            session.close()
            raise CommandError("Данная роль уже в чёрном списке")
        else:
            ignored_role = ServerIgnoreRolesListOfLevels(**db_kwargs)
            session.add(ignored_role)
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage("Вы добавили роль в чёрный список"))

    @role_ignore_list.command(
        cls=Command, name="remove",
        usage={"роль": ("упоминание, ID или название роли", True)}
    )
    @commands.has_permissions(administrator=True)
    @roles_in_ignore_list_exist()
    async def remove_role_from_ignore_list(self, ctx, role: commands.RoleConverter):
        """
        Удалить роль из чёрного списка
        """

        if role is None:
            raise CommandError("Вы не ввели роль")

        session = Session()
        db_kwargs = {
            "server_id": str(ctx.guild.id),
            "role_id": str(role.id)
        }
        ignored_role = session.query(ServerIgnoreRolesListOfLevels).filter_by(**db_kwargs).first()

        if ignored_role is None:
            session.close()
            raise CommandError("Данной роли нет в чёрном списке")
        else:
            session.delete(ignored_role)
            session.commit()
            session.close()

            await ctx.send(embed=SuccessfulMessage("Вы удалили роль из чёрного списка"))

    @role_ignore_list.command(name="reset")
    @commands.has_permissions(administrator=True)
    @roles_in_ignore_list_exist()
    async def reset_ignore_list_for_roles(self, ctx):
        """
        Сбросить чёрный список для ролей
        """

        session = Session()
        session.query(ServerIgnoreRolesListOfLevels).filter_by(server_id=str(ctx.guild.id)).delete()
        session.commit()
        session.close()

        await ctx.send(embed=SuccessfulMessage("Вы сбросили чёрный список для ролей"))
