import cmath
from discord.ext import commands
from string import Template

from main import Session
from core.database import ServerSettingsOfLevels


DEFAULT_LEVELUP_MESSAGE_FOR_SERVER = "$member_mention получил `$level уровень`"
DEFAULT_LEVELUP_MESSAGE_FOR_DM = "Вы получили `$level уровень` на **$server_name**"


def get_experience(level):
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


def get_level(exp):
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


def level_system_is_enabled(session, ctx):
    return session.query(ServerSettingsOfLevels).filter_by(server_id=str(ctx.guild.id)).first() is not None


def level_system_is_on():
    def decorator(ctx):
        session = Session()
        is_on = level_system_is_enabled(session, ctx)
        session.close()

        return is_on

    return commands.check(decorator)
