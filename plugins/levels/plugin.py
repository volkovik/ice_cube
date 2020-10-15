import discord
import asyncio
import datetime
import random
import sqlalchemy
from discord.ext import commands
from discord.ext.commands import CommandError
from discord.ext.commands import CooldownMapping, Cooldown

from main import Session
from core.commands import Cog, Command
from core.templates import ErrorMessage, SuccessfulMessage, DefaultEmbed as Embed
from core.database import (UserLevel, ServerSettingsOfLevels, ServerAwardOfLevels, ServerIgnoreChannelsListOfLevels,
                           ServerIgnoreRolesListOfLevels)

from .utils import (level_system_is_on, get_level, get_experience, format_levelup_message,
                    DEFAULT_LEVELUP_MESSAGE_FOR_SERVER, DEFAULT_LEVELUP_MESSAGE_FOR_DM)


class Levels(Cog, name="levels"):
    def __init__(self, bot):
        self._buckets = CooldownMapping(Cooldown(1, 60, commands.BucketType.member))
        super().__init__(bot)
        self.ru_name = "уровни"

    @commands.Cog.listener("on_message")
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
                    session.commit()

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
                    session.close()
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

    @commands.command("rank", Command)
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

    @commands.command("top", Command)
    @level_system_is_on()
    async def get_leaders_on_server(self, ctx, page: int = 1):
        """
        Топ участников по уровню на сервере
        """

        server = ctx.guild

        session = Session()
        users = session.query(UserLevel).filter_by(
            server_id=str(server.id)
        ).order_by(sqlalchemy.desc(UserLevel.experience)).all()
        session.close()

        top = []

        for user_from_db in users:
            user = server.get_member(int(user_from_db.user_id))

            if user is None:
                continue
            else:
                top.append((user, user_from_db.experience))

        if not top:
            raise CommandError("Никто из пользователь на сервере ещё не получил опыт")
        else:
            top = list(enumerate(top, 1))

        max_page = len(top) // 10 + (1 if len(top) % 10 > 0 else 0)

        if page > max_page:
            current_page = 1
        else:
            current_page = page

        def get_page():
            template = "**#{}:** `{}`\nУровень: {} | Опыт: {}"

            return "\n".join(map(
                lambda u: template.format(u[0], u[1][0].display_name, get_level(u[1][1]), u[1][1]),
                top[10 * (current_page - 1):10 * current_page]
            ))

        embed = Embed(
            title="Топ пользователей на сервере",
            description=get_page()
        )
        if max_page > 1:
            embed.set_footer(text=f"Стр. {current_page} из {max_page}")

        message = await ctx.send(embed=embed)
        
        if max_page > 1:
            emojis = {
                "previous": "⬅️",
                "next": "➡️"
            }
    
            for e in emojis.values():
                await message.add_reaction(e)
    
            def check(react, user):
                if max_page <= current_page and 1 < current_page:
                    return ctx.author == user and str(react) == emojis["previous"]
                elif 1 >= current_page and max_page > current_page:
                    return ctx.author == user and str(react) == emojis["next"]
                elif 1 < current_page < max_page:
                    return ctx.author == user and str(react) in emojis.values()
    
            while True:
                try:
                    reaction, _ = await self.client.wait_for('reaction_add', timeout=60.0, check=check)
                except asyncio.TimeoutError:
                    await message.clear_reactions()
                    return
                else:
                    if str(reaction) == emojis["next"]:
                        await message.remove_reaction(reaction, ctx.author)
                        current_page += 1
                    elif str(reaction) == emojis["previous"]:
                        await message.remove_reaction(reaction, ctx.author)
                        current_page -= 1
    
                    embed.description = get_page()
                    embed.set_footer(text=f"Стр. {current_page} из {max_page}")
    
                    await message.edit(embed=embed)

    @commands.command("editlevel", Command)
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

        server = ctx.guild

        session = Session()
        db_kwargs = {
            "server_id": str(server.id),
            "user_id": str(user.id)
        }
        user_level = session.query(UserLevel).filter_by(**db_kwargs).first()

        if user_level is None:
            user_level = UserLevel(**db_kwargs)
            session.add(user_level)

        lvl_user = get_level(user_level.experience)

        if lvl_user < level:
            awards = session.query(ServerAwardOfLevels).filter(
                ServerAwardOfLevels.server_id == str(server.id),
                ServerAwardOfLevels.level < level,
                ServerAwardOfLevels.level > lvl_user
            ).all()

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
        else:
            awards = session.query(ServerAwardOfLevels).filter(
                ServerAwardOfLevels.server_id == str(server.id),
                ServerAwardOfLevels.level > level,
                ServerAwardOfLevels.level < lvl_user
            ).all()

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

            await user.remove_roles(*roles)

        user_level.experience = get_experience(level)
        session.commit()
        session.close()

        if user == ctx.author:
            await ctx.send(embed=SuccessfulMessage(f"Вы поставили себе `{level} уровень`"))
        else:
            await ctx.send(
                embed=SuccessfulMessage(f"Вы поставили пользователю `{user.display_name}` `{level} уровень`")
            )
