import discord
from discord import Status
from discord.ext import commands
from discord.ext.commands import CommandError
from sqlalchemy.orm import sessionmaker

from main import ENGINE_DB, __version__
from core.database import User
from core.commands import BotCommand
from core.templates import SuccessfulMessage
from core.converts import convert_status, convert_activity_type, convert_voice_region, convert_verification_level


class Information(commands.Cog, name="Информация"):
    def __init__(self, bot):
        self.client = bot
        self.color = 0xFFCC4D

    @commands.command(
        cls=BotCommand, name="user",
        usage={"пользователь": ("упоминание или ID участника сервера, чтобы посмотреть его профиль", False)}
    )
    async def user_information(self, ctx, user: commands.MemberConverter = None):
        """
        Профиль пользователя
        """

        if user is None:
            user = ctx.author

        status = convert_status(user.status)
        created_at = user.created_at.strftime("%d.%m.%Y, %H:%M:%S")
        joined_at = user.joined_at.strftime("%d.%m.%Y, %H:%M:%S")

        if type(user.activity) is discord.CustomActivity:
            activity = f"**Пользовательский статус:** {user.activity}\n"

            if len(user.activities) > 1:
                activity += f"**{convert_activity_type(user.activities[1].type)}** {user.activities[1].name}\n"
        else:
            activity = f"**{convert_activity_type(user.activity.type)}** " \
                       f"{user.activity.name}\n" if user.activity else ""

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        user_from_db = session.query(User).filter_by(user_id=str(user.id)).first()
        bio = user_from_db.bio if user_from_db is not None else None

        if bio is None:
            if user == ctx.author:
                bio = "Вы можете вести свою информацию здесь с помощью команды `.bio`"
            else:
                bio = "Пользователь ещё не ввёл информацию здесь"

        message = discord.Embed(
            title=f"Информация о \"{user.display_name}\"",
            description=bio,
            color=self.color
        )
        message.add_field(
            name="Основная информация",
            value=f"**Никнейм:** {user.name}#{user.discriminator}\n"
                  f"**Статус:** {status}\n{activity}"
                  f"**Дата регистрации:** {created_at}\n"
                  f"**Дата присоеденения:** {joined_at}",
        )
        message.set_thumbnail(url=user.avatar_url_as(static_format="jpg"))
        message.set_footer(text=f"ID: {user.id}")

        await ctx.send(embed=message)

    @commands.command(
        cls=BotCommand, name="bio",
        usage={"текст": ("описание, которое будет отображаться в вашем профиле (оставьте пустым, если хотите удалить "
                         "уже существующий текст)", True)}
    )
    async def change_bio(self, ctx, *, text=None):
        """
        Редактирование описания в профиле
        """

        Session = sessionmaker(bind=ENGINE_DB)
        session = Session()

        user_from_db = session.query(User).filter_by(user_id=str(ctx.author.id)).first()
        if user_from_db is None:
            user_from_db = User(user_id=str(ctx.author.id))
            session.add(user_from_db)

        previous_bio = user_from_db.bio

        if text is not None:
            if len(text) > 512:
                raise CommandError("Я не могу поставить текст больше 512 символов")
            elif text == previous_bio:
                raise CommandError("Введёный текст идентичен вашему описанию в профиле")
            else:
                user_from_db.bio = text
                message = SuccessfulMessage("Я изменил описание в вашем профиле")
        else:
            if previous_bio is None:
                raise CommandError("Вы не ввели текст")
            else:
                user_from_db.bio = None

                message = SuccessfulMessage("Я удалил описание в вашем профиле")

        await ctx.send(embed=message)

        session.commit()

    @commands.command(cls=BotCommand, name="server")
    async def server_information(self, ctx):
        """
        Основная информация о сервере
        """

        server = ctx.guild

        region = convert_voice_region(server.region)
        verification = convert_verification_level(server.verification_level)
        security = str(verification) + (" (2FA)" if server.mfa_level is True else "")
        created_at = server.created_at.strftime("%d.%m.%Y, %H:%M:%S")

        def members_counter():
            members = server.members

            bots = len([x for x in members if x.bot])
            users = len(members) - bots
            online = len([x for x in members if x.status is not (Status.offline or Status.invisible) and not x.bot])
            offline = len([x for x in members if x.status is (Status.offline or Status.invisible) and not x.bot])

            info = f"Ботов: **{bots}**"
            info += f"\nПользователей: **{users}**"
            info += f"\nОнлайн: **{online}**" if online != 0 else ""
            info += f"\nОффлайн: **{offline}**" if offline != 0 else ""

            return info

        def channels_counter():
            text = len(server.text_channels)
            voice = len(server.voice_channels)

            info = f"Всего: **{voice + text}**" \
                   f"\nТекстовых: **{text}**"
            info += f"\nГолосовых: **{voice}**"

            return info

        message = discord.Embed(
            title=f"Информация о \"{server.name}\"",
            description=f"**Владелец:** {server.owner}"
                        f"\n**Регион:** {region}"
                        f"\n**Верификация:** {security}"
                        f"\n**Дата создания:** {created_at}",
            color=self.color
        )
        message.add_field(
            name="Участники",
            value=members_counter(),
            inline=True
        )
        message.add_field(
            name="Каналы",
            value=channels_counter(),
            inline=True
        )
        message.set_thumbnail(url=server.icon_url_as(static_format="jpg", size=512))
        message.set_footer(text=f"ID: {server.id}")

        await ctx.send(embed=message)

    @commands.command(cls=BotCommand, name="info")
    async def about_bot(self, ctx):
        """
        информация о боте
        """

        message = discord.Embed(
            title="Информация о Ice Cube",
            description="**Ice Cube** - это простой бот, основанный на языке Python. Сейчас, функционал у бота "
                        "скудный, но со временем он будет пополняться. Разработчик бота: "
                        "**[volkovik](https://github.com/volkovik)**",
            color=0xAEE4FC
        )
        message.set_thumbnail(url=self.client.user.avatar_url)
        message.set_footer(
            text="© Все права защищены volkovik 2020",
            icon_url="https://avatars.githubusercontent.com/u/40608600"
        )
        message.add_field(
            name="Полезные ссылки",
            value="[Discord сервер](https://discord.gg/atxwBRB)\n"
                  "[GitHub репозиторий](https://github.com/volkovik/ice_cube)"
        )
        message.add_field(
            name="Версия бота",
            value=__version__
        )

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Information(bot))
