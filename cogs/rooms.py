import discord
import mysql.connector
from discord.ext import commands

from main import CONFIG
from core.commands import BotCommand
from core.templates import SuccessfulMessage, CustomError


class Rooms(commands.Cog, name="Приватные комнаты"):
    def __init__(self, bot):
        self.client = bot
        self.owner_permissions = discord.PermissionOverwrite(manage_channels=True, connect=True, speak=True)

    @commands.Cog.listener("on_voice_state_update")
    async def voice_master(self, member, before, after):
        """
        Создание и удаление команты, когда пользователей заходит, выходит или перемещается по голосовым каналам

        :param member: пользователь, у которого был обновлён VoiceState
        :param before: VoiceState до обновления
        :param after: VoiceState после обновления
        """

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        server = after.channel.guild if before.channel is None else before.channel.guild
        everyone = server.default_role

        data_sql = {
            "server_id": server.id,
            "user_id": member.id
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None  # канал для создания комнат

        cursor.execute("SELECT name, is_private, user_limit FROM rooms_user_settings\n"
                       "WHERE server_id=%(server_id)s AND user_id=%(user_id)s", data_sql)
        result = cursor.fetchone()
        config = result if result is not None else None  # настройки пользователя

        # если канал не найден, то завершить процесс
        if creator is None:
            cursor.close()
            db.close()

            return
        else:
            creator = server.get_channel(creator)

            # если канала из базы данных нет на сервере или он не имеет категории, то удалить этот канал в базе данных
            if creator is None or creator.category is None:  #
                cursor.execute("DELETE FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)

                cursor.close()
                db.close()

                return
            else:
                category = creator.category

        if after.channel:
            # когда пользователь присоединяется или перемещается к голосовому каналу
            channel = after.channel

            if config is not None and config[0] is not None:
                channel_name = config[0]
            else:
                channel_name = member.display_name

            if creator == channel:
                # создать голосовой канал

                private = await server.create_voice_channel(channel_name, category=category)
                await private.set_permissions(member, overwrite=self.owner_permissions)

                if config is not None:
                    await private.edit(user_limit=config[2])

                    # если у пользователя стоит приватная комната
                    if config[1] == 1:
                        permissions = discord.PermissionOverwrite(connect=False)

                        await private.set_permissions(everyone, overwrite=permissions)

                await member.move_to(private)

        if before.channel:
            # когда пользователь выходит из голосового канала

            channel = before.channel

            if channel in category.voice_channels and channel != creator and len(channel.members) == 0:
                # удалить голосовой канал, если он является комнатой

                await channel.delete()

        cursor.close()
        db.close()

    @commands.Cog.listener("on_guild_channel_delete")
    async def voice_master_checker_deleted_channels(self, channel):
        """
        Проверка удалённого канала на канал, который создаёт приватные комнаты

        :param channel: удалённый канал
        """

        server = channel.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server_id": server.id}

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if channel.id == creator:
            cursor.execute("DELETE FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)

        cursor.close()
        db.close()

    @commands.Cog.listener("on_guild_channel_update")
    async def voice_master_checker_updated_channels(self, before, after):
        """
        Проверка изменённого канала на канал, который создаёт приватные комнаты

        :param before: канало до обновления
        :param after: канал после обновления
        """

        server = before.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server_id": server.id}

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if before.id == creator and after.category is None:
            cursor.execute("DELETE FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)

        cursor.close()
        db.close()

    @commands.group(name="room")
    async def room_settings(self, ctx):
        """
        Настройка вашей приватной комнаты
        """

    @room_settings.command(cls=BotCommand, name="lock")
    async def room_lock(self, ctx):
        """
        Закрыть комнату от постороних участников
        """

        member = ctx.author
        server = ctx.guild
        everyone = server.default_role

        permissions = discord.PermissionOverwrite(connect=False)

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "server_id": server.id,
            "user_id": member.id
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            return
        elif member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            cursor.close()
            db.close()

            raise CustomError("Вы должны быть в вашей приватной комнате, чтобы использовать данную команду")
        elif member.voice.channel.overwrites_for(everyone) == permissions:
            cursor.close()
            db.close()

            raise CustomError("Комната уже закрыта")
        else:
            message = SuccessfulMessage("Я закрыл вашу комнату")

            cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private)"
                           "VALUES(%(server_id)s, %(user_id)s, True)"
                           "ON DUPLICATE KEY UPDATE is_private=True", data_sql)

            cursor.close()
            db.close()

            await member.voice.channel.set_permissions(everyone, overwrite=permissions)

        await ctx.send(embed=message)

    @room_settings.command(cls=BotCommand, name="unlock")
    async def voice_unlock(self, ctx):
        """
        Открыть комнату для остальных участников
        """

        member = ctx.author
        server = ctx.guild
        everyone = server.default_role

        permissions = discord.PermissionOverwrite(connect=True)

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "server_id": server.id,
            "user_id": member.id
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            return
        elif member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            cursor.close()
            db.close()

            raise CustomError("Вы должны быть в вашей приватной комнате, чтобы использовать данную команду")
        elif member.voice.channel.overwrites_for(everyone) == permissions:
            cursor.close()
            db.close()

            raise CustomError("Комната уже открыта")
        else:
            message = SuccessfulMessage("Я открыл вашу комнату")

            cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private)\n"
                           "VALUES(%(server_id)s, %(user_id)s, False)\n"
                           "ON DUPLICATE KEY UPDATE is_private=False", data_sql)

            cursor.close()
            db.close()

            await member.voice.channel.set_permissions(everyone, overwrite=permissions)

        await ctx.send(embed=message)

    @room_settings.command(
        cls=BotCommand, name="limit",
        usage={"лимит участников": ("максимальное количество участников, которое может подключиться в комнату (если "
                                    "оставить пустым, лимит сбросится)", True)}
    )
    async def voice_users_limit(self, ctx, limit: int = 0):
        """
        Поставить лимит на количество пользователей в вашей приватной комнате
        """

        member = ctx.author
        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "server_id": server.id,
            "user_id": member.id,
            "user_limit": limit
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            return
        elif member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            cursor.close()
            db.close()

            raise CustomError("Вы должны быть в вашей приватной комнате, чтобы использовать данную команду")
        elif limit is not None and limit < 0:
            cursor.close()
            db.close()

            raise CustomError("Лимит не может быть меньше 0")
        elif member.voice.channel.user_limit == limit or (member.voice.channel.user_limit == 0 and limit is None):
            cursor.close()
            db.close()

            if member.voice.channel.user_limit == 0:
                raise CustomError("Я не могу сбросить лимит, когда самого лимита - нет")
            else:
                raise CustomError("Комната уже имеет такой лимит")
        else:
            if limit == 0:
                message = SuccessfulMessage("Я сбросил лимит в вашей комнате")
            else:
                message = SuccessfulMessage("Я изменил лимит вашей комнаты")

            cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, user_limit)\n"
                           "VALUES(%(server_id)s, %(user_id)s, %(user_limit)s)\n"
                           "ON DUPLICATE KEY UPDATE user_limit=%(user_limit)s", data_sql)

            cursor.close()
            db.close()

            await member.voice.channel.edit(user_limit=limit)

        await ctx.send(embed=message)

    @room_settings.command(
        cls=BotCommand, name="rename",
        usage={"название": ("новое название комнаты", True)}
    )
    async def rename(self, ctx, *, name=None):
        """
        Изменение названия команты
        """

        member = ctx.author
        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "server_id": server.id,
            "user_id": member.id,
            "name": name
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            return
        elif member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            cursor.close()
            db.close()

            raise CustomError("Вы должны быть в вашей приватной комнате, чтобы использовать данную команду")
        elif name is not None and len(name) > 32:
            cursor.close()
            db.close()

            raise CustomError("Название канала не должно быть больше 32-ух символов")
        elif member.voice.channel.name == name:
            cursor.close()
            db.close()

            raise CustomError("Комната уже имеет такое название")
        else:
            if name is None:
                message = SuccessfulMessage("Я сбросил название вашей комнаты")
                name = member.display_name

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, name)\n"
                               "VALUES(%(server_id)s, %(user_id)s, NULL)\n"
                               "ON DUPLICATE KEY UPDATE name=NULL", data_sql)
            else:
                message = SuccessfulMessage("Я изменил название вашей комнаты")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, name)\n"
                               "VALUES(%(server_id)s, %(user_id)s, %(name)s)\n"
                               "ON DUPLICATE KEY UPDATE name=%(name)s", data_sql)

            cursor.close()
            db.close()

            await member.voice.channel.edit(name=name)

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Rooms(bot))
