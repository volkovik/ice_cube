import asyncio
from discord.ext import commands
from discord.ext.commands import CommandError

from main import Session
from core.database import ServerSettingsOfRooms
from core.commands import Cog, Command
from core.templates import SuccessfulMessage, ErrorMessage, DefaultEmbed as Embed


class RoomsSettings(Cog, name="Настройки"):
    @commands.group(name="setrooms", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def rooms_settings(self, ctx):
        """
        Настройка приватных комнат на сервере
        """

        server = ctx.guild

        session = Session()
        settings = session.query(ServerSettingsOfRooms).filter_by(server_id=str(server.id)).first()

        if settings is None:
            embed = Embed(
                title="Приватные комнаты",
                description=f"На данный момент на этом сервере нет приватных комнат. Чтобы их включить, используйте "
                            f"команду `{ctx.prefix}setrooms enable`"
            )
        else:
            voice = server.get_channel(int(settings.channel_id_creates_rooms))
            category = voice.category

            embed = Embed(
                title="Приватные комнаты",
                description=f"На данный момент на этом сервере установлена система приватных комнат. Чтобы их "
                            f"выключить, используйте команду `{ctx.prefix}setrooms disable`\n\n"
                            f"**Будьте бдительны, когда выключаете систему! Удаляться все голосовые каналы в категории "
                            f"`{category}` и сама категория!**"
            )

        await ctx.send(embed=embed)

        session.close()

    @rooms_settings.command(cls=Command, name="enable")
    @commands.has_permissions(administrator=True)
    async def create_rooms_system(self, ctx):
        """
        Создать приватные комнаты на сервере
        """

        server = ctx.guild

        session = Session()
        settings = session.query(ServerSettingsOfRooms).filter_by(server_id=str(server.id)).first()

        if settings is not None:
            session.close()
            raise CommandError("У вас уже есть приватные комнаты")
        else:
            message = SuccessfulMessage("Я успешно включил систему приватных комнат")

            category = await server.create_category_channel(name="Приватные комнаты")
            voice = await server.create_voice_channel(name="Создать комнату", category=category)

            settings = ServerSettingsOfRooms(server_id=str(server.id), channel_id_creates_rooms=str(voice.id))
            session.add(settings)

        await ctx.send(embed=message)

        session.commit()
        session.close()

    @rooms_settings.command(cls=Command, name="disable")
    @commands.has_permissions(administrator=True)
    async def remove_rooms_system(self, ctx):
        """
        Выключить и удалить приватные комнаты на сервере
        """

        server = ctx.guild

        session = Session()
        settings = session.query(ServerSettingsOfRooms).filter_by(server_id=str(server.id)).first()

        if settings is None:
            session.close()
            raise CommandError("На вашем сервере не поставлены приватные комнаты")
        else:
            emojis = {
                "accept": "✅",
                "cancel": "🚫"
            }

            voice = server.get_channel(int(settings.channel_id_creates_rooms))
            category = voice.category

            embed = Embed(
                title="Выключение приватных комнат",
                description=f"Вы уверены, что хотите выключить систему приватных комнат?\n"
                            f"**Это повлечёт удалению всех голосовых каналов в категории `{category}` и самой "
                            f"категории!**\n\n"
                            f"{emojis['accept']} - Да, выключить\n"
                            f"{emojis['cancel']} - Нет, отменить выключение"
            )

            message = await ctx.send(embed=embed)

            await message.add_reaction(emojis["accept"])
            await message.add_reaction(emojis["cancel"])

            def check(reaction, user):
                return ctx.author == user and str(reaction) in emojis.values()

            try:
                reaction, _ = await self.client.wait_for('reaction_add', timeout=60.0, check=check)
            except asyncio.TimeoutError:
                await message.edit(embed=ErrorMessage("Превышено время ожидания"))
                await message.clear_reactions()
            else:
                if str(reaction) == emojis["accept"]:
                    embed = SuccessfulMessage("Я успешно выключил и удалил систему приватных комнат")

                    voice = server.get_channel(int(settings.channel_id_creates_rooms))
                    category = voice.category

                    if len(category.voice_channels) != 0:
                        for channel in category.voice_channels:
                            await channel.delete()

                    await category.delete()

                    session.delete(settings)
                else:
                    embed=Embed(
                        title=":x: Отменено",
                        description="Вы отменили удаление приватных комнат на этом сервере",
                        color=0xDD2E44
                    )

                await message.edit(embed=embed)
                await message.clear_reactions()

        session.commit()
        session.close()
