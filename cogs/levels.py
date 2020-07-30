import discord
import datetime
from discord.ext import commands
from discord.ext.commands import CommandError
from discord.ext.commands import CooldownMapping, Cooldown
from sqlalchemy.orm import sessionmaker

from main import ENGINE_DB
from core.commands import BotCommand
from core.templates import SuccessfulMessage
from core.database import UserLevel, ServerSettingsOfLevels


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

                update_user_experience(server, author, 25)

                if user_exp % 500 > (user_exp + 25) % 500:
                    await message.channel.send(f"{author.mention} получил `{(user_exp + 25) // 500} уровень`")

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

        message = discord.Embed()
        message.add_field(
            name="Уровень",
            value=str(user_exp // 500)
        )
        message.add_field(
            name="Опыт",
            value=f"{user_exp % 500}/500"
        )
        message.set_author(name=user.display_name, icon_url=user.avatar_url_as(static_format="jpg"))

        await ctx.send(embed=message)

    @commands.group(name="setlevels", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def rooms_settings(self, ctx):
        """
        Настройка системы уровней на сервере
        """

        await ctx.send_help(ctx.command.name)

    @rooms_settings.command(cls=BotCommand, name="enable")
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

    @rooms_settings.command(cls=BotCommand, name="disable")
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
            session.delete(server_settings)

            message = SuccessfulMessage("Я выключил систему уровней на вашем сервере")

            session.commit()
            session.close()

            await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Level(bot))
