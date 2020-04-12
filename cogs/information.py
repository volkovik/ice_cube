import discord
import json
import mysql.connector
from discord import Status
from utilities import ConvertEnums
from discord.ext import commands


class Information(commands.Cog, name="Информация"):
    def __init__(self, bot):
        self.client = bot
        self.color = 0xFFCC4D

        with open("config.json") as f:
            self.config = json.load(f)

    @commands.command(name="user")
    async def user_information(self, ctx, user: commands.MemberConverter = None):
        """
        Некоторая информация о пользователе
        """

        if user is None:
            user = ctx.author

        status = ConvertEnums.status(user.status)
        created_at = user.created_at.strftime("%d.%m.%Y, %H:%M:%S")
        joined_at = user.joined_at.strftime("%d.%m.%Y, %H:%M:%S")

        if type(user.activity) is discord.CustomActivity:
            activity = f"**Пользовательский статус:** {user.activity}\n"

            if len(user.activities) > 1:
                activity += f"**{ConvertEnums.activity_type(user.activities[1].type)}** {user.activities[1]}\n"
        else:
            activity = f"**{ConvertEnums.activity_type(user.activity.type)}** " \
                       f"{user.activity.name}\n" if user.activity else ""

        db = mysql.connector.connect(**self.config["database"])
        cursor = db.cursor()

        data_sql = {"user_id": user.id}

        cursor.execute("SELECT bio FROM users WHERE id=%(user_id)s", data_sql)
        result = cursor.fetchone()
        bio = result[0] if result is not None else None

        cursor.close()
        db.close()

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

    @user_information.error
    async def error_user_information(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            message = discord.Embed(
                title=":x: Ошибка",
                description="Я не нашёл указанного участника на сервере",
                color=0xDD2E44
            )

            await ctx.send(embed=message)

    @commands.command(name="bio")
    async def change_bio(self, ctx, *, text=None):
        """
        Редактирование описания в профиле
        """

        db = mysql.connector.connect(**self.config["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "user_id": ctx.author.id,
            "bio": text
        }

        cursor.execute("SELECT bio FROM users WHERE id=%(user_id)s", data_sql)
        result = cursor.fetchone()
        last_text = result[0] if result is not None else None

        if text is not None:
            if len(text) > 255:
                message = discord.Embed(
                    title=":x: Ошибка",
                    description="Я не могу поставить текст больше 255 символов",
                    color=0xDD2E44
                )

                cursor.close()
                db.close()

                return await ctx.send(embed=message)
            elif text == last_text:
                message = discord.Embed(
                    title=":x: Ошибка",
                    description="Введёный текст идентичен вашему описанию в профиле",
                    color=0xDD2E44
                )

                cursor.close()
                db.close()
                return await ctx.send(embed=message)

            cursor.execute("INSERT INTO users(id, bio) VALUES(%(user_id)s, %(bio)s)\n"
                           "ON DUPLICATE KEY UPDATE bio=%(bio)s", data_sql)

            message = discord.Embed(
                title=":white_check_mark: Успешно",
                description="Я изменил описание в вашем профиле",
                color=0x77B255
            )
        else:
            if last_text is None:
                message = discord.Embed(
                    title=":x: Ошибка",
                    description="Вы не ввели текст",
                    color=0xDD2E44
                )
            else:
                cursor.execute("DELETE FROM users WHERE id=%(user_id)s", data_sql)

                message = discord.Embed(
                    title=":white_check_mark: Успешно",
                    description="Я удалил описание в вашем профиле",
                    color=0x77B255
                )

        await ctx.send(embed=message)

        cursor.close()
        db.close()

    @commands.command(name="server")
    async def server_information(self, ctx):
        """
        Основная информация о сервере
        """

        server = ctx.guild

        region = ConvertEnums.voice_region(server.region)
        verification = ConvertEnums.verification_level(server.verification_level)
        security = str(verification) + (" (2FA)" if server.mfa_level is True else "")
        created_at = server.created_at.strftime("%d.%m.%Y, %H:%M:%S")

        def members_counter():
            members = server.members

            bots = len([x for x in members if x.bot])
            users = len(members) - bots
            online = len([x for x in members if x.status is Status.online and not x.bot])
            idle = len([x for x in members if x.status is Status.idle and not x.bot])
            dnd = len([x for x in members if x.status is (Status.dnd or Status.do_not_disturb) and not x.bot])
            offline = len([x for x in members if x.status is (Status.offline or Status.invisible) and not x.bot])

            info = f"Пользователей: **{users}**"
            info += f"\nОнлайн: **{online}**" if online != 0 else ""
            info += f"\nНеактивны: **{idle}**" if idle != 0 else ""
            info += f"\nНе беспокоить: **{dnd}**" if dnd != 0 else ""
            info += f"\nОффлайн: **{offline}**" if offline != 0 else ""
            info += f"\nБотов: **{bots}**"

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
        message.set_thumbnail(
            url=server.icon_url_as(static_format="jpg", size=512))

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Information(bot))
