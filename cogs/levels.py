import discord
import mysql.connector
from discord.ext import commands
from discord.ext.commands import CommandError

from main import CONFIG
from core.commands import BotCommand
from core.templates import SuccessfulMessage


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

    db = mysql.connector.connect(**CONFIG["database"])
    cursor = db.cursor()

    cursor.execute(
        "SELECT experience FROM levels "
        "WHERE server_id=%s AND user_id=%s",
        (server.id, user.id)
    )
    result = cursor.fetchone()

    db.close()
    cursor.close()

    return result[0] if result is not None else 0


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

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    sql_format = {
        "server": server.id,
        "user": user.id,
        "exp": exp
    }

    cursor.execute(
        "INSERT INTO levels(server_id, user_id, experience) "
        "VALUES(%(server)s, %(user)s, %(exp)s) "
        "ON DUPLICATE KEY UPDATE experience=experience + %(exp)s",
        sql_format
    )

    db.close()
    cursor.close()


def predicate_check_level_system(ctx):
    """
    Проверка, включёна ли система уровней на сервере

    :param ctx: сообщение или context
    :type ctx: commands.Context or discord.Message
    :return: True, если включена, иначе False
    :rtype: bool
    """

    db = mysql.connector.connect(**CONFIG["database"])
    cursor = db.cursor()

    cursor.execute(
        "SELECT level_system FROM servers "
        "WHERE id=%s",
        (ctx.guild.id, )
    )
    result = cursor.fetchone()

    return result[0] if result is not None else False


def level_system_is_on():
    """
    Декоратор для discord.Command, с проверкой, включена ли система уровней на сервере
    """

    return commands.check(predicate_check_level_system)


class Level(commands.Cog, name="Уровни"):
    def __init__(self, bot):
        self.client = bot

    @commands.Cog.listener(name="on_message")
    async def when_message(self, message):
        author = message.author

        if not author.bot and predicate_check_level_system(message):
            server = message.guild

            user_exp = get_user_experience(server, author)

            update_user_experience(server, author, 25)

            if user_exp % 500 > (user_exp + 25) % 500:
                await message.channel.send(f"{author.mention} получил `{(user_exp + 25) // 500} уровень`")

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

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server": server.id}

        cursor.execute(
            "SELECT level_system FROM servers "
            "WHERE id=%(server)s",
            data_sql
        )
        result = cursor.fetchone()
        is_on = result[0] if result is not None else False

        if is_on:
            cursor.close()
            db.close()

            raise CommandError("На вашем сервере уже вылючена система уровней")
        else:
            message = SuccessfulMessage("Я успешно включил систему уровней")

            cursor.execute(
                "INSERT INTO servers(id, level_system) "
                "VALUES (%(server)s, 1) "
                "ON DUPLICATE KEY UPDATE level_system=1",
                data_sql
            )

            cursor.close()
            db.close()

        await ctx.send(embed=message)

    @rooms_settings.command(cls=BotCommand, name="disable")
    @commands.has_permissions(administrator=True)
    async def disable_level_system(self, ctx):
        """
        Выключить систему уровней на сервере
        """

        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server": server.id}

        cursor.execute(
            "SELECT level_system FROM servers "
            "WHERE id=%(server)s",
            data_sql
        )
        result = cursor.fetchone()
        is_on = result[0] if result is not None else False

        if not is_on:
            cursor.close()
            db.close()

            raise CommandError("На вашем сервере уже выключена система уровней")
        else:
            message = SuccessfulMessage("Я успешно выключил систему уровней")

            cursor.execute(
                "UPDATE IGNORE servers SET level_system=0 "
                "WHERE id=%(server)s",
                data_sql
            )

            cursor.close()
            db.close()

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Level(bot))
