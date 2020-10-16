import discord
from discord import Status
from discord.ext import commands
from discord.ext.commands import CommandError

from main import Session, __version__
from core.database import User, UserScoreToAnotherUser
from core.commands import Cog, Group, Command
from core.templates import SuccessfulMessage, DefaultEmbed as Embed, send_message_with_reaction_choice
from core.converts import convert_status, convert_activity_type, convert_voice_region, convert_verification_level


class Information(Cog, name="info"):
    def __init__(self, bot):
        super(Information, self).__init__(bot)
        self.ru_name = "информация"

    @commands.command("user", Command)
    async def user_information(self, ctx, user: commands.MemberConverter = None):
        """
        Профиль пользователя

        :argname user: пользователь
        :argdesc user: имя, упоминание или ID пользователя
        :argreq user: False

        :example: `{prefix}user`  - информация о вашем аккаунте
        :example: `{prefix}user @anyone`  - информация о пользователе anyone
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

        session = Session()

        user_from_db = session.query(User).filter_by(user_id=str(user.id)).first()
        bio = user_from_db.bio if user_from_db is not None else None

        up_score = session.query(UserScoreToAnotherUser).filter_by(rated_user_id=str(user.id), score=True).count()
        down_score = session.query(UserScoreToAnotherUser).filter_by(rated_user_id=str(user.id), score=False).count()

        user_score = up_score - down_score
        user_score = str(user_score) if user_score <= 0 else f"+{user_score}"

        session.close()

        if bio is None:
            if user == ctx.author:
                bio = "Вы можете вести свою информацию здесь с помощью команды `.bio`"
            else:
                bio = "Пользователь ещё не ввёл информацию здесь"

        app = await self.client.application_info()
        is_dev = app.owner.id == user.id

        message = Embed(
            title=f"Информация о \"{user.display_name}\"" + (" :ice_cube:" if is_dev else ""),
            description=bio
        )
        message.add_field(
            name="Основная информация",
            value=f"**Никнейм:** {user.name}#{user.discriminator}\n"
                  f"**Репутация:** {user_score}\n"
                  f"**Статус:** {status}\n{activity}"
                  f"**Дата регистрации:** {created_at}\n"
                  f"**Дата присоеденения:** {joined_at}",
        )
        message.set_thumbnail(url=user.avatar_url_as(static_format="jpg"))
        message.set_footer(text=f"ID: {user.id}")

        await ctx.send(embed=message)

    @commands.command("bio", Command)
    async def change_bio(self, ctx, *, text=None):
        """
        Редактировать информацию о себе

        :note: Данный текст будет отображаться в профиле, независимо от того, на каком сервере вызвали команду

        :argname text: текст
        :argdesc text: текст, который будет отображаться в профиле
        :argnote text: Если аргумент оставить пустым, то информация в профиле удалиться (если она, конечно, есть)
        :argreq text: True

        :example: `.bio Я люблю клубнику!`  - поставить "Я люблю клубнику!" в вашем профиле
        :example: `.bio` - удалить текущую информацию в профиле (если её нет, то будет ошибка)
        """
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
        session.close()

    @commands.group("rep", cls=Group, aliases=["rate"], invoke_without_command=True)
    async def set_reputation_for_user(self, ctx, user: commands.MemberConverter):
        """
        Поставить оценку пользователю

        :argname user: пользователь
        :argdesc user: имя, упоминание или ID пользователя
        :argreq user: True

        :example: `.rep @anyone`  - поставить оценку пользователю anyone
        """
        if user == ctx.author:
            raise CommandError("Вы не можете дать оценку самому себе")
        elif user.bot:
            raise CommandError("Вы не можете оценить бота")

        session = Session()

        db_kwargs = {
            "user_id": str(ctx.author.id),
            "rated_user_id": str(user.id)
        }

        user_score_from_db = session.query(UserScoreToAnotherUser).filter_by(**db_kwargs).first()

        emojis = {
            "up": "⬆️",
            "down": "⬇️"
        }

        if user_score_from_db is None:
            emojis["cancel"] = "🚫"
            embed = Embed(
                title="Выберите оценку пользователю",
                description=f"{emojis['up']} - Положительная {emojis['down']} - Отрицательная\n\n"
                            f"{emojis['cancel']} - Отменить оценку пользователю"
            )

            message, answer = await send_message_with_reaction_choice(self.client, ctx, embed, emojis)

            if answer == "up":
                session.add(UserScoreToAnotherUser(**db_kwargs, score=True))
                session.commit()
                await message.edit(embed=SuccessfulMessage(f"Вы поставили положительную оценку "
                                                           f"`{user.display_name}`"))
            elif answer == "down":
                session.add(UserScoreToAnotherUser(**db_kwargs, score=False))
                session.commit()
                await message.edit(embed=SuccessfulMessage(f"Вы поставили отрицательную оценку "
                                                           f"`{user.display_name}`"))
            elif answer == "cancel":
                await message.edit(embed=Embed(
                    title=":x: Отменено",
                    description="Вы отменили оценку пользователю",
                    color=0xDD2E44
                ))
        else:
            cancelled_message = Embed(
                title=":x: Отменено",
                description="Вы отменили изменение оценки пользователю",
                color=0xDD2E44
            )

            emojis["remove"] = "❌"
            emojis["cancel"] = "🚫"

            if user_score_from_db.score is True:
                del emojis["up"]

                embed = Embed(
                    title="Выберите оценку пользователю",
                    description=f"Ваша текущая оценка этому пользователю: `Положительная`\n"
                                f"{emojis['down']} - Изменить оценку на отрицательную\n"
                                f"{emojis['remove']} - Удалить оценку пользователю\n\n"
                                f"{emojis['cancel']} - Отменить изменение оценки пользователю"
                )

                message, answer = await send_message_with_reaction_choice(self.client, ctx, embed, emojis)

                if answer == "down":
                    user_score_from_db.score = False
                    session.commit()
                    await message.edit(embed=SuccessfulMessage(f"Вы изменили вашу оценку на отрицательную "
                                                               f"`{user.display_name}`"))
                elif answer == "remove":
                    session.delete(user_score_from_db)
                    session.commit()
                    await message.edit(embed=SuccessfulMessage(f"Вы удалили оценку `{user.display_name}`"))
                elif answer == "cancel":
                    await message.edit(embed=cancelled_message)
            else:
                del emojis["down"]

                embed = Embed(
                    title="Выберите оценку пользователю",
                    description=f"Ваша текущая оценка этому пользователю: `Отрицательная`\n"
                                f"{emojis['up']} - Изменить оценку на положительную\n"
                                f"{emojis['remove']} - Удалить оценку пользователю\n\n"
                                f"{emojis['cancel']} - Отменить изменение оценки пользователю"
                )

                message, answer = await send_message_with_reaction_choice(self.client, ctx, embed, emojis)

                if answer == "up":
                    user_score_from_db.score = True
                    session.commit()
                    await message.edit(embed=SuccessfulMessage(f"Вы изменили вашу оценку на положительную "
                                                               f"`{user.display_name}`"))
                elif answer == "remove":
                    session.delete(user_score_from_db)
                    session.commit()
                    await message.edit(embed=SuccessfulMessage(f"Вы удалили оценку `{user.display_name}`"))
                elif answer == "cancel":
                    await message.edit(embed=cancelled_message)

        session.close()

    @set_reputation_for_user.command("+", Command, aliases=["up"])
    async def rate_up_user(self, ctx, user: commands.MemberConverter):
        """
        Поставить положительную оценку пользователю

        :argname user: пользователь
        :argdesc user: имя, упоминание или ID пользователя
        :argreq user: True

        :example: `.rep + @anyone`  - поставить положительную оценку пользователю anyone
        """
        if user == ctx.author:
            raise CommandError("Вы не можете дать оценку самому себе")
        elif user.bot:
            raise CommandError("Вы не можете оценить бота")

        session = Session()

        db_kwargs = {
            "user_id": str(ctx.author.id),
            "rated_user_id": str(user.id)
        }

        score_from_db = session.query(UserScoreToAnotherUser).filter_by(**db_kwargs).first()

        if score_from_db is None:
            session.add(UserScoreToAnotherUser(**db_kwargs, score=True))
            embed = SuccessfulMessage(f"Вы поставили положительную оценку `{user.display_name}`")
        else:
            if score_from_db.score is True:
                session.close()
                raise CommandError("Вы уже поставили положительную оценку пользователю")
            else:
                score_from_db.score = True
                embed = SuccessfulMessage(f"Вы изменили вашу оценку на положительную `{user.display_name}`")

        await ctx.send(embed=embed)

        session.commit()
        session.close()

    @set_reputation_for_user.command("-", Command, aliases=["down"])
    async def rate_down_user(self, ctx, user: commands.MemberConverter):
        """
        Поставить отрицательную оценку пользователю

        :argname user: пользователь
        :argdesc user: имя, упоминание или ID пользователя
        :argreq user: True

        :example: `.rep - @anyone`  - поставить отрицательную оценку пользователю anyone
        """
        if user == ctx.author:
            raise CommandError("Вы не можете дать оценку самому себе")
        elif user.bot:
            raise CommandError("Вы не можете оценить бота")

        session = Session()

        db_kwargs = {
            "user_id": str(ctx.author.id),
            "rated_user_id": str(user.id)
        }

        score_from_db = session.query(UserScoreToAnotherUser).filter_by(**db_kwargs).first()

        if score_from_db is None:
            session.add(UserScoreToAnotherUser(**db_kwargs, score=False))
            embed = SuccessfulMessage(f"Вы поставили отрицательную оценку `{user.display_name}`")
        else:
            if score_from_db.score is False:
                session.close()
                raise CommandError("Вы уже поставили отрицательную оценку пользователю")
            else:
                score_from_db.score = False
                session.commit()
                embed = SuccessfulMessage(f"Вы изменили вашу оценку на отрицательную `{user.display_name}`")

        await ctx.send(embed=embed)

        session.close()

    @set_reputation_for_user.command("remove", Command)
    async def remove_score_user(self, ctx, user: commands.MemberConverter):
        """
        Удалить оценку у пользователя

        :argname user: пользователь
        :argdesc user: имя, упоминание или ID пользователя
        :argreq user: True

        :example: `.rep remove @anyone`  -  удалить оценку у пользователя anyone
        """
        if user == ctx.author:
            raise CommandError("Вы не можете удалить оценку самому себе")
        elif user.bot:
            raise CommandError("Вы не можете удалить оценку у бота")

        session = Session()

        db_kwargs = {
            "user_id": str(ctx.author.id),
            "rated_user_id": str(user.id)
        }

        score_from_db = session.query(UserScoreToAnotherUser).filter_by(**db_kwargs)

        if score_from_db is None:
            session.close()
            raise CommandError("Вы не ставили этому пользователю оценку")
        else:
            score_from_db.delete()
            session.commit()
            embed = SuccessfulMessage(f"Вы удалили оценку `{user.display_name}`")

            await ctx.send(embed=embed)

        session.close()

    @commands.command("server", Command)
    async def server_information(self, ctx):
        """Основная информация о сервере"""
        server = ctx.guild

        region = convert_voice_region(server.region)
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

        message = Embed(
            title=f"Информация о \"{server.name}\"",
            description=f"**Владелец:** {server.owner}"
                        f"\n**Регион:** {region}"
                        f"\n**Дата создания:** {created_at}"
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

    @commands.command("info", Command)
    async def about_bot(self, ctx):
        """Информация о боте"""
        app = await self.client.application_info()

        message = Embed(
            title=f"Информация о \"{app.name}\"",
            description=app.description
        )
        message.set_thumbnail(url=self.client.user.avatar_url)
        message.set_footer(
            text="© volkovik 2020. Все права защищены",
            icon_url="https://avatars.githubusercontent.com/u/40608600"
        )
        message.add_field(
            name="Полезные ссылки",
            value=f"[Discord сервер](https://discord.gg/atxwBRB)\n"
                  f"[Разработчик](https://github.com/volkovik)\n"
                  f"[Пригласить бота](https://discord.com/oauth2/authorize?client_id={app.id}&scope=bot&permissions=8)"
        )
        message.add_field(
            name="Версия бота",
            value=__version__
        )

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Information(bot))
