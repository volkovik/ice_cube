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

        cursor.execute("SELECT allowed_member_id FROM permissions_to_join_room "
                       "WHERE server_id=%(server_id)s AND user_id=%(user_id)s",
                       data_sql)
        result = cursor.fetchall()
        allowed_members_to_join = [server.get_member(int(x[0])) for x in result] if result is not None else None

        # если канал не найден, то завершить процесс
        if creator is None:
            cursor.close()
            db.close()

            return
        else:
            creator = server.get_channel(creator)

            # если канала из базы данных нет на сервере или он не имеет категории, то удалить этот канал в базе данных
            if creator is None or creator.category is None:
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

                # дать доступ пользователем, которые были в базе данных
                if allowed_members_to_join is not None:
                    for user in allowed_members_to_join:
                        permissions = discord.PermissionOverwrite(connect=True)

                        await private.set_permissions(user, overwrite=permissions)

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

        db = mysql.connector.connect(**CONFIG["database"])
        cursor = db.cursor()

        user = ctx.author
        server = ctx.guild
        everyone = server.default_role

        data_sql = {
            "server_id": server.id,
            "user_id": user.id
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        voice_creator = result[0] if result is not None else None

        if voice_creator is None:
            cursor.close()
            db.close()

            raise CustomError("У данного сервера нет системы приватных комнат")

        if ctx.invoked_subcommand is None:
            db.autocommit = True

            # Конфигурация голосового канала из базы данных
            cursor.execute("SELECT is_private, user_limit, name FROM rooms_user_settings "
                           "WHERE server_id=%(server_id)s AND user_id=%(user_id)s", data_sql)
            result = cursor.fetchone()
            settings_db = result if result is not None else None
            name_db = settings_db[2] if settings_db[2] is not None else user.display_name
            user_limit_db = settings_db[1]
            is_locked_db = settings_db[0]

            # Список пользователей из базы данных, у которых есть доступ к комнате
            cursor.execute("SELECT allowed_member_id FROM permissions_to_join_room "
                           "WHERE server_id=%(server_id)s AND user_id=%(user_id)s", data_sql)
            result = cursor.fetchall()
            allowed_members_db = [server.get_member(int(x[0])) for x in result] if len(result) != 0 else None

            # Создание формы сообщения
            message = discord.Embed(title=f"Информация о комнате пользователя \"{user.display_name}\"")
            message.set_footer(text=f"Посмотреть все доступные команды для управления комнатой можно "
                                    f"через {ctx.prefix}help user")

            if user.voice is None or user.voice.channel.overwrites_for(user) != self.owner_permissions:
                # Выставить настройки из базы данных, если пользователь не находится в своём голосовом канале
                name, user_limit, is_locked = name_db, user_limit_db, is_locked_db

                allowed_members = allowed_members_db
            else:
                channel = user.voice.channel

                # Выставить настройки из текущего голосового канала, если он является комнатой пользователя
                name = channel.name
                user_limit = channel.user_limit
                is_locked = channel.overwrites_for(everyone) == discord.PermissionOverwrite(connect=False)

                # Записать изменения голосового канала в базу данных, если данные из базы данных не соотвествуют данным
                # из канала
                if name != name_db or user_limit != user_limit_db or is_locked != is_locked_db:
                    data_sql["is_private"] = is_locked
                    data_sql["user_limit"] = user_limit
                    data_sql["name"] = name if name != user.display_name else None

                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private, user_limit, name) "
                                   "VALUES(%(server_id)s, %(user_id)s, %(is_private)s, %(user_limit)s, %(name)s) "
                                   "ON DUPLICATE KEY UPDATE is_private=%(is_private)s, user_limit=%(user_limit)s, "
                                   "name=%(name)s", data_sql)

                allowed_members = []

                for m, p in channel.overwrites.items():
                    if type(m) is discord.Member and p == discord.PermissionOverwrite(connect=True) and m.id != user.id:
                        allowed_members.append(m)

                        if m not in allowed_members_db:
                            data_sql["allowed_member_id"] = m.id

                            cursor.execute("INSERT INTO permissions_to_join_room(server_id, user_id, "
                                           "allowed_member_id) "
                                           "VALUES (%(server_id)s, %(user_id)s, %(allowed_member_id)s)", data_sql)

                # Удалить пользователей из базы данных, которые не были в голосовом канале
                if allowed_members_db is not None:
                    for m in set(allowed_members_db) - set(allowed_members):
                        data_sql["allowed_member_id"] = m.id

                        cursor.execute("DELETE FROM permissions_to_join_room WHERE server_id=%(server_id)s "
                                       "AND user_id=%(user_id)s AND allowed_member_id=%(allowed_member_id)s", data_sql)

            # Информация о комнате
            message.description = f"**Название: ** {name}\n" \
                                  f"**Доступ:** {'закрытый' if is_locked else 'открытый'}\n" \
                                  f"**Лимит пользователей: ** {user_limit if user_limit != 0 else 'нет'}"

            # Информация о пользователях с правами доступа
            if allowed_members is not None:
                allowed_members.sort(key=lambda m: m.name)

                message.add_field(
                    name="Список пользователей с доступом",
                    value="\n".join([f"**{m}** (ID: {m.id})" for m in allowed_members])
                )

            await ctx.send(embed=message)

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

        cursor.execute("SELECT is_private FROM rooms_user_settings "
                       "WHERE server_id=%(server_id)s AND user_id=%(user_id)s", data_sql)
        result = cursor.fetchone()
        last_value = True if result is not None and result[0] == 1 else False

        if creator is None:
            cursor.close()
            db.close()

            return

        if member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            if last_value is True:
                cursor.close()
                db.close()

                raise CustomError("Комната уже закрыта")
            else:
                message = SuccessfulMessage("Я закрыл вашу комнату")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private)\n"
                               "VALUES(%(server_id)s, %(user_id)s, True)\n"
                               "ON DUPLICATE KEY UPDATE is_private=True", data_sql)

                cursor.close()
                db.close()
        else:
            if member.voice.channel.overwrites_for(everyone) == permissions:
                if last_value is not True:
                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private)\n"
                                   "VALUES(%(server_id)s, %(user_id)s, True)\n"
                                   "ON DUPLICATE KEY UPDATE is_private=True", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Комната уже закрыта")
            else:
                message = SuccessfulMessage("Я закрыл вашу комнату")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private)\n"
                               "VALUES(%(server_id)s, %(user_id)s, True)\n"
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

        cursor.execute("SELECT is_private FROM rooms_user_settings "
                       "WHERE server_id=%(server_id)s AND user_id=%(user_id)s", data_sql)
        result = cursor.fetchone()
        last_value = True if result is not None and result[0] == 1 else False

        if creator is None:
            cursor.close()
            db.close()

            return

        if member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            if last_value is False:
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
        else:
            if member.voice.channel.overwrites_for(everyone) == permissions:
                if last_value is not False:
                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private)\n"
                                   "VALUES(%(server_id)s, %(user_id)s, False)\n"
                                   "ON DUPLICATE KEY UPDATE is_private=False", data_sql)

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
        usage={"лимит участников": ("максимальное количество участников, которое может подключиться к комнате (если "
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
        creator = result[0] if result is not None else None

        cursor.execute("SELECT user_limit FROM rooms_user_settings WHERE server_id=%(server_id)s "
                       "AND user_id=%(user_id)s", data_sql)
        result = cursor.fetchone()
        last_limit = int(result[0]) if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            return

        if 0 > limit:
            cursor.close()
            db.close()

            raise CustomError("Лимит не должен быть меньше 0")
        elif limit > 99:
            cursor.close()
            db.close()

            raise CustomError("Лимит не должен быть больше 99")

        if member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            if last_limit == 0 and limit == 0:
                cursor.close()
                db.close()

                raise CustomError("Вы ещё не поставили лимит пользователей для комнаты, чтобы сбрасывать его")
            elif last_limit == limit:
                cursor.close()
                db.close()

                raise CustomError("Комната уже имеет такой лимит")
            else:
                message = SuccessfulMessage("Я изменил лимит пользователей для вашей комнаты")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, user_limit)\n"
                               "VALUES(%(server_id)s, %(user_id)s, %(user_limit)s)\n"
                               "ON DUPLICATE KEY UPDATE user_limit=%(user_limit)s", data_sql)

                cursor.close()
                db.close()
        else:
            if member.voice.channel.user_limit == limit == 0:
                if last_limit != 0:
                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, user_limit)\n"
                                   "VALUES(%(server_id)s, %(user_id)s, 0)\n"
                                   "ON DUPLICATE KEY UPDATE user_limit=0", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Вы ещё не поставили лимит для комнаты, чтобы сбрасывать его")
            elif member.voice.channel.user_limit == limit:
                if last_limit != limit:
                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, user_limit)\n"
                                   "VALUES(%(server_id)s, %(user_id)s, %(user_limit)s)\n"
                                   "ON DUPLICATE KEY UPDATE user_limit=%(user_limit)s", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Комната уже имеет такой лимит")
            else:
                if limit == 0:
                    message = SuccessfulMessage("Я сбросил лимит пользователей в вашей комнате")
                else:
                    message = SuccessfulMessage("Я изменил лимит пользователей в вашей комнате")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, user_limit)\n"
                               "VALUES(%(server_id)s, %(user_id)s, %(user_limit)s)\n"
                               "ON DUPLICATE KEY UPDATE user_limit=%(user_limit)s", data_sql)

                cursor.close()
                db.close()

                await member.voice.channel.edit(user_limit=limit)

        await ctx.send(embed=message)

    @room_settings.command(
        cls=BotCommand, name="rename",
        usage={"название": ("новое название комнаты (если оставить пустым, то название комнаты станет ваше имя)", True)}
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

        cursor.execute("SELECT name FROM rooms_user_settings WHERE server_id=%(server_id)s AND user_id=%(user_id)s",
                       data_sql)
        result = cursor.fetchone()
        last_name = result[0] if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            return

        if name is not None and len(name) > 32:
            cursor.close()
            db.close()

            raise CustomError("Название канала не должно быть больше 32-ух символов")

        if member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            if last_name is None and name is None:
                cursor.close()
                db.close()

                raise CustomError("Вы ещё не поставили название для комнаты, чтобы сбрасывать его")
            elif last_name == name:
                cursor.close()
                db.close()

                raise CustomError("Комната уже имеет такое название")
            else:
                message = SuccessfulMessage("Я изменил название вашей комнаты")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, name)\n"
                               "VALUES(%(server_id)s, %(user_id)s, %(name)s)\n"
                               "ON DUPLICATE KEY UPDATE name=%(name)s", data_sql)

                cursor.close()
                db.close()
        else:
            if member.voice.channel.name == member.display_name and name is None:
                if last_name is not None:
                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, name)\n"
                                   "VALUES(%(server_id)s, %(user_id)s, NULL)\n"
                                   "ON DUPLICATE KEY UPDATE name=NULL", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Вы ещё не поставили название для комнаты, чтобы сбрасывать его")
            elif member.voice.channel.name == name:
                if not last_name == name:
                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, name)\n"
                                   "VALUES(%(server_id)s, %(user_id)s, %(name)s)\n"
                                   "ON DUPLICATE KEY UPDATE name=%(name)s", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Комната уже имеет такое название")
            else:
                if name is None:
                    name = member.display_name
                    message = SuccessfulMessage("Я сбросил название вашего канала")
                else:
                    message = SuccessfulMessage("Я изменил название вашего канала")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, name)\n"
                               "VALUES(%(server_id)s, %(user_id)s, %(name)s)\n"
                               "ON DUPLICATE KEY UPDATE name=%(name)s", data_sql)

                cursor.close()
                db.close()

                await member.voice.channel.edit(name=name)

        await ctx.send(embed=message)

    @room_settings.command(cls=BotCommand, name="addmember",
                           usage={"пользователь": ("упоминание или ID участника сервера", True)})
    async def give_permissions_to_member(self, ctx, member: commands.MemberConverter):
        """
        Дать доступ к приватному каналу пользователю
        """

        user = ctx.author
        server = ctx.guild
        permissions = discord.PermissionOverwrite(connect=True)

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "server_id": server.id,
            "user_id": user.id,
            "allowed_member_id": member.id
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            raise()

        cursor.execute("SELECT allowed_member_id FROM permissions_to_join_room "
                       "WHERE server_id=%(server_id)s AND user_id=%(user_id)s",
                       data_sql)
        result = cursor.fetchall()
        allowed_members = [int(x[0]) for x in result] if result is not None else None

        if user.voice is None or user.voice.channel.overwrites_for(user) != self.owner_permissions:
            if member.id in allowed_members:
                cursor.close()
                db.close()

                raise CustomError("Этот участник уже имеет доступ к вашей комнате")
            else:
                cursor.execute("INSERT IGNORE INTO permissions_to_join_room(server_id, user_id, allowed_member_id) "
                               "VALUES(%(server_id)s, %(user_id)s, %(allowed_member_id)s)", data_sql)

                cursor.close()
                db.close()

                message = SuccessfulMessage(f"Я дал доступ `{member.display_name}` к вашей комнате")
        else:
            if user.voice.channel.overwrites_for(member) == permissions:
                if member.id not in allowed_members:
                    cursor.execute("INSERT IGNORE INTO permissions_to_join_room(server_id, user_id, allowed_member_id) "
                                   "VALUES(%(server_id)s, %(user_id)s, %(allowed_member_id)s)", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Этот участник уже имеет доступ к вашей комнате")
            else:
                cursor.execute("INSERT IGNORE INTO permissions_to_join_room(server_id, user_id, allowed_member_id) "
                               "VALUES(%(server_id)s, %(user_id)s, %(allowed_member_id)s)", data_sql)

                cursor.close()
                db.close()

                message = SuccessfulMessage(f"Я дал доступ `{member.display_name}` к вашей комнате")

                await user.voice.channel.set_permissions(member, overwrite=permissions)

        await ctx.send(embed=message)

    @room_settings.command(cls=BotCommand, name="removemember",
                           usage={"пользователь": ("упоминание или ID участника сервера", True)})
    async def remove_permissions_to_member(self, ctx, member: commands.MemberConverter):
        """
        Забрать доступ к приватному каналу у пользователя
        """

        user = ctx.author
        server = ctx.guild
        permissions = discord.PermissionOverwrite(connect=None)

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {
            "server_id": server.id,
            "user_id": user.id,
            "allowed_member_id": member.id
        }

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        creator = int(result[0]) if result is not None else None

        if creator is None:
            cursor.close()
            db.close()

            raise ()

        cursor.execute("SELECT allowed_member_id FROM permissions_to_join_room "
                       "WHERE server_id=%(server_id)s AND user_id=%(user_id)s",
                       data_sql)
        result = cursor.fetchall()
        allowed_members = [int(x[0]) for x in result] if result is not None else None

        if user.voice is None or user.voice.channel.overwrites_for(user) != self.owner_permissions:
            if member.id not in allowed_members:
                cursor.close()
                db.close()

                raise CustomError("Этот участник не имеет доступ к каналу")
            else:
                cursor.execute("DELETE FROM permissions_to_join_room WHERE server_id=%(server_id)s AND "
                               "user_id=%(user_id)s AND allowed_member_id=%(allowed_member_id)s", data_sql)

                cursor.close()
                db.close()

                message = SuccessfulMessage(f"Я забрал доступ у `{member.display_name}` к вашей комнате")
        else:
            if user.voice.channel.overwrites_for(member) == permissions:
                if member.id not in allowed_members:
                    cursor.execute("DELETE FROM permissions_to_join_room WHERE server_id=%(server_id)s AND "
                                   "user_id=%(user_id)s AND allowed_member_id=%(allowed_member_id)s", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Этот участник не имеет доступ к каналу")
            else:
                cursor.execute("DELETE FROM permissions_to_join_room WHERE server_id=%(server_id)s AND "
                               "user_id=%(user_id)s AND allowed_member_id=%(allowed_member_id)s", data_sql)

                cursor.close()
                db.close()

                message = SuccessfulMessage(f"Я забрал доступ у `{member.display_name}` к вашей комнате")

                await user.voice.channel.set_permissions(member, overwrite=permissions)

        await ctx.send(embed=message)

    @room_settings.command(name="reset")
    async def reset_room_settings(self, ctx):
        """
        Сбросить все настройки комнаты
        """

        member = ctx.author
        server = ctx.guild
        everyone = server.default_role

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

        cursor.execute("SELECT is_private, user_limit, name FROM rooms_user_settings "
                       "WHERE server_id=%(server_id)s AND user_id=%(user_id)s", data_sql)
        result = cursor.fetchone()
        settings_from_db = result if result is not None else None

        default_settings_db = (0, 0, None)
        permissions = discord.PermissionOverwrite(connect=True)

        if creator is None:
            cursor.close()
            db.close()

            return

        if member.voice is None or member.voice.channel.overwrites_for(member) != self.owner_permissions:
            if settings_from_db == default_settings_db or settings_from_db is None:
                cursor.close()
                db.close()

                raise CustomError("Вы ещё не сделали каких-либо изменений для комнаты, чтобы сбрасывать его настройки")
            else:
                message = SuccessfulMessage("Я сбросил настройки вашей комнаты")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private, user_limit, name)\n"
                               "VALUES(%(server_id)s, %(user_id)s, False, 0, NULL)\n"
                               "ON DUPLICATE KEY UPDATE is_private=False, user_limit=0, name=NULL", data_sql)

                cursor.close()
                db.close()
        else:
            channel = member.voice.channel

            if channel.name == member.display_name and channel.user_limit == 0 \
                    and channel.overwrites_for(everyone) == permissions:
                if settings_from_db != default_settings_db:
                    cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private, user_limit, name)\n"
                                   "VALUES(%(server_id)s, %(user_id)s, False, 0, NULL)\n"
                                   "ON DUPLICATE KEY UPDATE is_private=False, user_limit=0, name=NULL", data_sql)

                cursor.close()
                db.close()

                raise CustomError("Вы ещё не сделали каких-либо изменений для комнаты, чтобы сбрасывать его настройки")
            else:
                message = SuccessfulMessage("Я сбросил настройки вашей комнаты")

                cursor.execute("INSERT INTO rooms_user_settings(server_id, user_id, is_private, user_limit, name)\n"
                               "VALUES(%(server_id)s, %(user_id)s, False, 0, NULL)\n"
                               "ON DUPLICATE KEY UPDATE is_private=False, user_limit=0, name=NULL", data_sql)

                cursor.close()
                db.close()

                await channel.edit(name=member.display_name, user_limit=0)
                await channel.set_permissions(everyone, overwrite=permissions)

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Rooms(bot))
