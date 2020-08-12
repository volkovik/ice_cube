import discord
import datetime
import random
import sqlalchemy
from discord.ext import commands
from discord.ext.commands import CommandError
from discord.ext.commands import CooldownMapping, Cooldown

from main import Session
from core.commands import Cog, Command
from core.templates import SuccessfulMessage, DefaultEmbed as Embed
from core.database import (UserLevel, ServerSettingsOfLevels, ServerAwardOfLevels, ServerIgnoreChannelsListOfLevels,
                           ServerIgnoreRolesListOfLevels)

from .utils import (level_system_is_on, get_level, get_experience, format_levelup_message,
                    DEFAULT_LEVELUP_MESSAGE_FOR_SERVER, DEFAULT_LEVELUP_MESSAGE_FOR_DM)


class Levels(Cog, name="Уровни"):
    def __init__(self, bot):
        self._buckets = CooldownMapping(Cooldown(1, 60, commands.BucketType.member))
        super().__init__(bot)

    @commands.Cog.listener(name="on_message")
    async def when_message(self, message):
        context = await self.client.get_context(message)

        if context.valid:
            return

        user = message.author

        if user.bot or message.channel.type is discord.ChannelType.private:
            return

        server = message.guild

        session = Session()
        server_settings = session.query(ServerSettingsOfLevels).filter_by(server_id=str(server.id)).first()

        if server_settings is not None:
            ignored_channels = session.query(ServerIgnoreChannelsListOfLevels).filter_by(server_id=str(server.id)).all()

            for ignored in ignored_channels:
                channel = server.get_channel(int(ignored.channel_id))

                if channel is not None:
                    if message.channel == channel:
                        session.close()
                        return
                else:
                    session.delete(ignored)
                    session.close()

                if str(message.channel.id) == ignored.channel_id:
                    session.close()
                    return

            ignored_roles = session.query(ServerIgnoreRolesListOfLevels).filter_by(server_id=str(server.id)).all()

            for ignored in ignored_roles:
                role = server.get_role(int(ignored.role_id))

                if role is not None:
                    if role in user.roles:
                        session.close()
                        return
                else:
                    session.delete(ignored)
                    session.commit()

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

                add_exp = random.randint(15, 25)

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
                        higher_bot_role = server.me.roles[-1]

                        for award in awards:
                            role = server.get_role(int(award.role_id))

                            if role is None:
                                session.delete(award)
                                session.commit()
                            elif role < higher_bot_role:
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
        cls=Command, name="rank",
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

        message = Embed()
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

    @commands.command(cls=Command, name="top")
    @level_system_is_on()
    async def get_leaders_on_server(self, ctx):
        """
        Топ 10 участников по уровню на сервере
        """

        server = ctx.guild

        session = Session()
        users = session.query(UserLevel).filter_by(
            server_id=str(server.id)
        ).order_by(sqlalchemy.desc(UserLevel.experience)).all()
        session.close()

        top = []

        for user_from_db in users:
            if len(top) == 10:
                break

            user = server.get_member(int(user_from_db.user_id))

            if user is None:
                continue
            else:
                user_exp = user_from_db.experience

                top.append(f"**#{len(top) + 1}:** `{user.display_name}`\n"
                           f"Уровень: {get_level(user_exp)} | Опыт: {user_exp}")

        if not top:
            raise CommandError("Никто из пользователь на сервере ещё не получил опыт")

        embed = Embed(
            title="Топ 10 пользователей на сервере",
            description="\n".join(top)
        )

        await ctx.send(embed=embed)

    @commands.command(
        cls=Command, name="editlevel",
        usage={
            "уровень": ("уровень, который будет поставлен для участника", True),
            "пользователь": ("упоминание, ID или никнейм пользователя (оставьте пустым, если хотите изменить уровень "
                             "себе)", True),
        }
    )
    @commands.has_permissions(administrator=True)
    @level_system_is_on()
    async def edit_user_level(self, ctx, level: int = None, user: commands.MemberConverter = None):
        """
        Изменить уровень пользователя
        """

        if user is None:
            user = ctx.author

        if level > 1000:
            raise CommandError("Вы не можете поставить уровень больше 1000-го")
        elif level < 0:
            raise CommandError("Вы не можете поставить уровень меньше нуля")

        session = Session()
        db_kwargs = {
            "server_id": str(ctx.guild.id),
            "user_id": str(user.id)
        }
        user_level = session.query(UserLevel).filter_by(**db_kwargs).first()

        if user_level is None:
            user_level = UserLevel(**db_kwargs)
            session.add(user_level)

        user_level.experience = get_experience(level)
        session.commit()
        session.close()

        if user == ctx.author:
            await ctx.send(embed=SuccessfulMessage(f"Вы поставили себе `{level} уровень`"))
        else:
            await ctx.send(
                embed=SuccessfulMessage(f"Вы поставили пользователю `{user.display_name}` `{level} уровень`")
            )