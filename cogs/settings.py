from discord.ext import commands
from discord.ext.commands import CommandError

from main import Session, DEFAULT_PREFIX
from core.commands import BotCommand
from core.database import Server
from core.templates import SuccessfulMessage


class Settings(commands.Cog, name="Настройки"):
    def __init__(self, bot):
        self.client = bot

    @commands.command(
        cls=BotCommand, name="prefix",
        usage={"prefix": ("префикс бота, который будет работать только на этом сервере (оставьте пустым, если хотите "
                          "удалить уже существующий префикс)", True)}
    )
    @commands.has_permissions(administrator=True)
    async def set_prefix_server(self, ctx, prefix=None):
        """
        Изменение префикса бота на сервере
        """

        server = ctx.guild

        session = Session()

        db_kwargs = {
            "server_id": str(server.id)
        }

        server_from_db = session.query(Server).filter_by(**db_kwargs).first()

        if server_from_db is None:
            server_from_db = Server(**db_kwargs)
            session.add(server_from_db)

        last_prefix = server_from_db.prefix if server_from_db.prefix is not None else DEFAULT_PREFIX

        if prefix is not None:
            if len(prefix) > 32:
                session.close()
                raise CommandError("Я не могу поставить префикс, который больше 32 символов")
            elif prefix == last_prefix:
                session.close()
                raise CommandError("Вы уже используете данный префикс")

            if prefix == DEFAULT_PREFIX:
                server_from_db.prefix = None
                message = SuccessfulMessage("Я успешно сбросил префикс на стандартный")
            else:
                server_from_db.prefix = prefix
                message = SuccessfulMessage("Я успешно изменил префикс")
        else:
            if last_prefix == DEFAULT_PREFIX:
                session.close()
                raise CommandError("Вы не ввели префикс")
            else:
                server_from_db.prefix = None

                message = SuccessfulMessage("Я успешно сбросил префикс на стандартный")

        await ctx.send(embed=message)

        session.commit()
        session.close()


def setup(bot):
    bot.add_cog(Settings(bot))
