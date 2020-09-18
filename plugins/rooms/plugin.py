import discord
from discord.ext import commands
from discord import PermissionOverwrite as Permissions
from discord.ext.commands import CommandError

from main import Session
from core.database import ServerSettingsOfRooms, UserSettingsOfRoom, UserPermissionsOfRoom, PermissionsForRoom
from core.commands import Cog, Command
from core.templates import SuccessfulMessage, DefaultEmbed as Embed

# Настройки владельца комнаты
OWNER_PERMISSIONS = Permissions(manage_channels=True, connect=True, speak=True)


def get_server_settings(session: Session, server):
    return session.query(ServerSettingsOfRooms).filter_by(server_id=str(server.id)).first()


def get_user_settings(session: Session, server, user):
    return session.query(UserSettingsOfRoom).filter_by(server_id=str(server.id), owner_id=str(user.id)).first()


def get_all_permissions(session: Session, server, user):
    return session.query(UserPermissionsOfRoom).filter_by(server_id=str(server.id), owner_id=str(user.id)).all()


class Rooms(Cog, name="Приватные комнаты"):
    @commands.Cog.listener("on_voice_state_update")
    async def rooms_master(self, user, before, after):
        """
        Создание комнат и удаление комнат без пользователей
        """

        server = after.channel.guild if before.channel is None else before.channel.guild

        session = Session()
        server_settings = get_server_settings(session, server)

        if server_settings is None:
            session.close()
            return
        else:
            # голосовой канал, который создаёт комнаты
            creator_rooms = server.get_channel(int(server_settings.channel_id_creates_rooms))

        # если голосового канала нет или у него нет категории, то удалить из базы данных
        if creator_rooms is None or creator_rooms.category is None:
            session.delete(server_settings)
            session.commit()
            session.close()
            return
        else:
            rooms_category = creator_rooms.category  # категория, в которой будут создаваться комнаты

        # голосовой канал, из которого вышел пользователь
        if before.channel:
            channel = before.channel

            if channel in rooms_category.voice_channels and channel != creator_rooms and len(channel.members) == 0:
                await channel.delete()

        # голосовой канал, в который зашёл пользователь
        if after.channel:
            channel = after.channel

            # если этот канал предназначен для создания комнат, то создать комнату
            if creator_rooms == channel:
                # настройки комнаты для пользователя из базы данных
                user_settings = get_user_settings(session, server, user)
                everyone = server.default_role

                # если настроек в базе данных - нет, то создать запись в базе данных
                if user_settings is None:
                    user_settings = UserSettingsOfRoom(server_id=server.id, owner_id=user.id)
                    session.add(user_settings)
                    session.commit()

                # разрешения для голосового канала (комнаты)
                permissions_for_room = {
                    user: OWNER_PERMISSIONS,
                    everyone: Permissions(connect=not user_settings.is_locked)
                }

                # разрешения из базы данных
                users_with_permissions = get_all_permissions(session, server, user)

                for perms in users_with_permissions:
                    user_with_perms = server.get_member(int(perms.user_id))

                    # если пользователя не удалось найти на сервере, то удалить запись из базы данных
                    if user_with_perms is None:
                        session.delete(perms)
                        session.commit()
                    else:
                        permissions_for_room[user_with_perms] = Permissions(connect=perms.permissions.value)

                room = await server.create_voice_channel(
                    name=user_settings.name if user_settings.name is not None else user.display_name,
                    category=rooms_category,
                    overwrites=permissions_for_room,
                    user_limit=user_settings.user_limit,
                    bitrate=user_settings.bitrate * 1000
                )

                await user.move_to(room)

        session.close()

    @commands.Cog.listener("on_guild_channel_delete")
    async def rooms_master_check_deleted_channels(self, channel):
        """
        Проверка удалённого канала на канал, который создаёт приватные комнаты
        """

        session = Session()
        settings = get_server_settings(session, channel.guild)

        if settings is not None and settings.channel_id_creates_rooms == str(channel.id):
            session.delete(settings)
            session.commit()

        session.close()

    @commands.Cog.listener("on_guild_channel_update")
    async def voice_master_checker_updated_channels(self, before, after):
        """
        Проверка изменённого канала на канал, который создаёт приватные комнаты
        """

        server = before.guild

        session = Session()
        server_settings = get_server_settings(session, before.guild)

        # Если у канала удалили категорию или сам канал перемещён в другую категорию, то удалить запись в базе данных
        if before.id == int(server_settings.channel_id_creates_rooms) and before.category != after.category:
            session.delete(server_settings)
            session.commit()
        else:
            # Владелец комнаты
            owner = [m for m, p in before.overwrites.items() if p == OWNER_PERMISSIONS]
            if len(owner) != 0:
                owner = owner[0]
                user_settings = get_user_settings(session, server, owner)

                room = after
                everyone = server.default_role

                user_settings.name = room.name if room.name != owner.display_name else None
                user_settings.user_limit = room.user_limit
                user_settings.bitrate = room.bitrate // 1000
                user_settings.is_locked = room.overwrites_for(everyone) == Permissions(connect=False)
                session.commit()

                # Пользователи, у который есть доступ к каналу, из текущего войса и из базы данных
                permissions_from_voice = dict(
                    filter(
                        lambda p: type(p[0]) is discord.Member and p[0].id != owner.id,
                        map(lambda m: (m[0], PermissionsForRoom(m[1].connect)), room.overwrites.items()))
                )

                # Если список пользователей из войса и из базы данных не сходятся, то обновить список в базе данных
                data_from_db = get_all_permissions(session, server, owner)

                permissions_from_db = {}

                for user in data_from_db:
                    member = server.get_member(int(user.user_id))

                    if member is not None:
                        permissions_from_db[member] = user.permissions

                added = [(m, p) for m, p in permissions_from_voice.items() if m not in permissions_from_db]
                deleted = [(m, p) for m, p in permissions_from_db.items() if m not in permissions_from_voice]
                modified = [(m, p) for m, p in permissions_from_voice.items()
                            if m in permissions_from_db and permissions_from_db[m] != permissions_from_voice[m]]

                db_kwargs = {
                    "server_id": str(server.id),
                    "owner_id": str(owner.id)
                }

                for member, perms in added:
                    session.add(UserPermissionsOfRoom(**db_kwargs, user_id=str(member.id), permissions=perms))

                for member, _ in deleted:
                    session.query(UserPermissionsOfRoom).filter_by(**db_kwargs, user_id=str(member.id)).delete()

                for member, perms in modified:
                    session.query(UserPermissionsOfRoom).filter_by(**db_kwargs,
                                                                   user_id=str(member.id)).first().permissions = perms

                session.commit()
                session.close()

        session.close()

    @commands.group(name="room")
    async def room_settings(self, ctx):
        """
        Настройка вашей приватной комнаты
        """

        user = ctx.author
        server = ctx.guild

        session = Session()

        server_settings = get_server_settings(session, server)
        user_settings = get_user_settings(session, server, user)

        if user_settings is None:
            raise CommandError(f"Вы не ещё не использовали приватные комнаты на этом сервере. Зайдите в голосовой "
                               f"канал `{server.get_channel(int(server_settings.channel_id_creates_rooms))}`, чтобы "
                               f"создать комнату")

        # Если команда была использована без сабкоманды, то отправить информацию о комнате
        if ctx.invoked_subcommand is None:
            message = Embed(title=f"Комната пользователя \"{user.display_name}\"")
            message.set_footer(text=f"Посмотреть все доступные команды для управления комнатой можно с помощью команды "
                                    f"{ctx.prefix}help room")

            if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
                # Проверяет настройки войса с настройками из базы данных
                room = user.voice.channel
                everyone = server.default_role

                name = room.name
                is_locked = room.overwrites_for(everyone) == Permissions(connect=False)
                user_limit = room.user_limit
                bitrate = room.bitrate // 1000

                permissions = dict(
                    filter(
                        lambda p: type(p[0]) is discord.Member and p[0].id != user.id,
                        map(lambda m: (m[0], m[1].connect), room.overwrites.items()))
                )
            else:
                user_settings = get_user_settings(session, server, user)

                name = user_settings.name if user_settings.name is not None else user.display_name
                is_locked = user_settings.is_locked
                user_limit = user_settings.user_limit
                bitrate = user_settings.bitrate

                data_from_db = get_all_permissions(session, server, user)

                permissions = {}

                for perm in data_from_db:
                    member = server.get_member(int(perm.user_id))

                    if member is not None:
                        permissions[member] = perm.permissions.value

            # Информация о комнате
            message.description = f"**Название: ** {name}\n" \
                                  f"**Доступ:** {'закрытый' if is_locked else 'открытый'}\n" \
                                  f"**Лимит пользователей:** {user_limit if user_limit != 0 else 'нет'}\n" \
                                  f"**Битрейт:** {bitrate} кбит/с"

            # Перечесление пользователей с правами доступа
            if permissions is not None:
                allowed = list(filter(lambda p: p[1], permissions.items()))
                banned = list(filter(lambda p: not p[1], permissions.items()))

                if len(allowed) != 0:
                    message.add_field(
                        name="Есть доступ",
                        value="\n".join([f"**{m}**" for m, _ in allowed])
                    )

                if len(banned) != 0:
                    message.add_field(
                        name="Заблокирован доступ",
                        value="\n".join([f"**{m}**" for m, _ in banned])
                    )

            await ctx.send(embed=message)

        session.close()

    @room_settings.command(cls=Command, name="lock")
    async def lock_room(self, ctx):
        """
        Закрыть комнату от посторонних участников
        """

        user = ctx.author
        server = ctx.guild

        session = Session()
        settings = get_user_settings(session, server, user)

        if settings.is_locked:
            session.close()
            raise CommandError("Комната уже закрыта")
        else:
            settings.is_locked = True
            session.commit()
            session.close()

            if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
                await user.voice.channel.set_permissions(server.default_role, overwrite=Permissions(connect=False))

            await ctx.send(embed=SuccessfulMessage("Я закрыл вашу комнату"))

    @room_settings.command(cls=Command, name="unlock")
    async def unlock_room(self, ctx):
        """
        Открыть комнату для посторонних участников
        """

        user = ctx.author
        server = ctx.guild

        session = Session()
        settings = get_user_settings(session, server, user)

        if not settings.is_locked:
            session.close()
            raise CommandError("Комната уже открыта")
        else:
            settings.is_locked = False
            session.commit()
            session.close()

            if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
                await user.voice.channel.set_permissions(server.default_role, overwrite=Permissions(connect=True))

            await ctx.send(embed=SuccessfulMessage("Я открыл вашу комнату"))

    @room_settings.command(
        cls=Command, name="limit",
        usage={"лимит": ("максимальное количество участников, которое может подключиться к комнате (если оставить "
                         "пустым, лимит сбросится)", True)}
    )
    async def room_users_limit(self, ctx, limit: int = 0):
        """
        Поставить лимит пользователей для комнаты
        """

        user = ctx.author
        server = ctx.guild

        session = Session()
        settings = get_user_settings(session, server, user)

        if 0 > limit:
            session.close()
            raise CommandError("Лимит не должен быть меньше 0")
        elif limit > 99:
            session.close()
            raise CommandError("Лимит не должен быть больше 99")

        if settings.user_limit == limit == 0:
            session.close()
            raise CommandError("Вы ещё не поставили лимит пользователей для комнаты, чтобы сбрасывать его")
        elif settings.user_limit == limit:
            session.close()
            raise CommandError("Комната уже имеет такой лимит")
        else:
            if limit == 0:
                message = SuccessfulMessage("Я сбросил лимит пользователей в вашей комнате")
            else:
                message = SuccessfulMessage("Я изменил лимит пользователей для вашей комнаты")

            settings.user_limit = limit
            session.commit()
            session.close()

            if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
                await user.voice.channel.edit(user_limit=limit)

            await ctx.send(embed=message)

    @room_settings.command(
        cls=Command, name="name",
        usage={"название": ("новое название комнаты (если оставить пустым, то название комнаты изменится на ваш ник)",
                            True)}
    )
    async def rename_room(self, ctx, *, name=None):
        """
        Измененить название команты
        """

        user = ctx.author
        server = ctx.guild

        if name is not None and len(name) > 32:
            raise CommandError("Название канала не должно быть больше 32-ух символов")

        session = Session()
        settings = get_user_settings(session, server, user)

        if settings.name == user.display_name and name is None:
            session.close()
            raise CommandError("Вы ещё не поставили название для комнаты, чтобы сбрасывать его")
        elif name == settings.name:
            session.close()
            raise CommandError("Комната уже имеет такое название")
        else:
            if name is None:
                message = SuccessfulMessage("Я сбросил название вашего канала")
                name = user.display_name
                settings.name = None
            else:
                message = SuccessfulMessage("Я изменил название вашей комнаты")
                settings.name = name

            session.commit()
            session.close()

            if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
                await user.voice.channel.edit(name=name)

            await ctx.send(embed=message)

    @room_settings.command(
        cls=Command, name="bitrate",
        usage={"битрейт": ("кбит/с, чем больше, тем лучше качество звука (если оставить пустым, битрейт будет 64)",
                           True)}
    )
    async def change_room_bitrate(self, ctx, bitrate: int = 64):
        """
        Изменить битрейт (качество звука) комнаты
        """

        user = ctx.author
        server = ctx.guild
        max_bitrate = int(server.bitrate_limit // 1000)

        if 8 > bitrate:
            raise CommandError("Битрейт не должен быть меньше 8")
        elif bitrate > max_bitrate:
            raise CommandError(f"Битрейт не должен быть больше {max_bitrate}")

        session = Session()
        settings = get_user_settings(session, server, user)

        if settings.bitrate == bitrate == 64:
            session.close()
            raise CommandError("Вы ещё не изменяли битрейт, чтобы сбрасывать его по умолчанию")
        elif settings.bitrate == bitrate:
            session.close()
            raise CommandError("Комната уже имеет такой битрейт")
        else:
            if bitrate == 0:
                message = SuccessfulMessage("Я сбросил битрейт в вашей комнате")
            else:
                message = SuccessfulMessage("Я изменил битрейт в вашей комнате")

            settings.bitrate = bitrate
            session.commit()
            session.close()

            if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
                await user.voice.channel.edit(bitrate=bitrate * 1000)

            await ctx.send(embed=message)

    @room_settings.command(
        cls=Command, name="kick",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def kick_member_from_room(self, ctx, user: commands.MemberConverter = None):
        """
        Кикнуть пользователя из вашей комнаты
        """

        author = ctx.author

        if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
            if user is None:
                raise CommandError("Вы не ввели пользователя")

            members = author.voice.channel.members

            if user not in members:
                raise CommandError("В вашей комнате нет такого пользователя")
            else:
                await user.move_to(None)
                await ctx.send(embed=SuccessfulMessage(f"Я кикнул `{user.display_name}` из вашей комнаты"))
        else:
            raise CommandError("Вы не находитесь в своей комнате")

    @room_settings.command(
        cls=Command, name="allow",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def allow_member_to_join_room(self, ctx, user: commands.MemberConverter):
        """
        Дать доступ пользователю заходить в комнату
        """

        owner = ctx.author
        server = ctx.guild

        session = Session()

        db_kwargs = {
            "server_id": str(server.id),
            "owner_id": str(owner.id),
            "user_id": str(user.id)
        }

        permissions_from_db = session.query(UserPermissionsOfRoom).filter_by(**db_kwargs).first()
        perms = PermissionsForRoom.allowed

        if permissions_from_db is not None and permissions_from_db.permissions == perms:
            session.close()
            raise CommandError("Этот участник уже имеет доступ к вашей комнате")
        else:
            if permissions_from_db is None:
                session.add(UserPermissionsOfRoom(**db_kwargs, permissions=perms))
            else:
                permissions_from_db.permissions = perms
            session.commit()
            session.close()

            if owner.voice is not None and owner.voice.channel.overwrites_for(owner) == OWNER_PERMISSIONS:
                await owner.voice.channel.set_permissions(user, overwrite=Permissions(connect=perms.value))

            await ctx.send(embed=SuccessfulMessage(f"Я дал доступ `{user.display_name}` к вашей комнате"))

    @room_settings.command(
        cls=Command, name="ban",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def ban_member_from_room(self, ctx, user: commands.MemberConverter):
        """
        Заблокировать доступ пользователю заходить в комнату
        """

        owner = ctx.author
        server = ctx.guild

        session = Session()

        db_kwargs = {
            "server_id": str(server.id),
            "owner_id": str(owner.id),
            "user_id": str(user.id)
        }

        permissions_from_db = session.query(UserPermissionsOfRoom).filter_by(**db_kwargs).first()
        perms = PermissionsForRoom.banned

        if permissions_from_db is not None and permissions_from_db.permissions == perms:
            session.close()
            raise CommandError("У этого участника уже заблокирован доступ к вашей комнате")
        else:
            if permissions_from_db is None:
                session.add(UserPermissionsOfRoom(**db_kwargs, permissions=perms))
            else:
                permissions_from_db.permissions = perms
            session.commit()
            session.close()

            if owner.voice is not None and owner.voice.channel.overwrites_for(owner) == OWNER_PERMISSIONS:
                await owner.voice.channel.set_permissions(user, overwrite=Permissions(connect=perms.value))

            await ctx.send(embed=SuccessfulMessage(f"Я заброкировал доступ у `{user.display_name}` к вашей комнате"))

    @room_settings.command(
        cls=Command, name="remove",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def set_default_permissions_for_member(self, ctx, user: commands.MemberConverter):
        """
        Поставить доступ к каналу у пользователя по умолчанию
        """

        owner = ctx.author
        server = ctx.guild

        session = Session()
        permissions_from_db = session.query(UserPermissionsOfRoom).filter_by(
            server_id=str(server.id), owner_id=str(owner.id), user_id=str(user.id)
        ).first()

        if permissions_from_db is None:
            session.close()
            raise CommandError("Этот участник не имеет особых прав, чтобы сбрасывать их")
        else:
            session.delete(permissions_from_db)
            session.commit()
            session.close()

            if owner.voice is not None and owner.voice.channel.overwrites_for(owner) == OWNER_PERMISSIONS:
                await owner.voice.channel.set_permissions(user, overwrite=Permissions(connect=None))

            await ctx.send(embed=SuccessfulMessage(f"Я сбросил права доступа у `{user.display_name}` к вашей комнате"))

    @room_settings.command(name="reset")
    async def reset_room_settings(self, ctx):
        """
        Сбросить все настройки комнаты
        """

        owner = ctx.author
        server = ctx.guild
        everyone = server.default_role

        session = Session()

        settings = get_user_settings(session, server, owner)
        permissions_from_db = get_all_permissions(session, server, owner)

        voice_channel = owner.voice.channel if owner.voice is not None and \
            owner.voice.channel.overwrites_for(owner) == OWNER_PERMISSIONS else None

        if voice_channel:
            permissions_from_voice = list(filter(
                lambda p: type(p[0]) is discord.Member and p[0].id != owner.id and p[1].connect is not None,
                voice_channel.overwrites.items()
            ))
        else:
            permissions_from_voice = []

        if settings.name is None and settings.user_limit == 0 and settings.bitrate == 64 and not settings.is_locked \
                and (not len(permissions_from_db) and voice_channel is None or not len(permissions_from_voice) and
                     voice_channel is not None):
            for i in permissions_from_db:
                session.delete(i)
            session.commit()
            session.close()
            raise CommandError("Вы ещё не сделали каких-либо изменений для комнаты, чтобы сбрасывать его настройки")
        else:
            settings.name = None
            settings.user_limit = 0
            settings.bitrate = 64
            settings.is_locked = False
            session.commit()
            session.close()

            for i in permissions_from_db:
                session.delete(i)
            session.commit()
            session.close()

            if voice_channel:
                await voice_channel.edit(name=owner.display_name, user_limit=0, bitrate=64000)
                await voice_channel.set_permissions(everyone, overwrite=Permissions(connect=True))

                for user, _ in permissions_from_voice:
                    await voice_channel.set_permissions(user, overwrite=None)

            await ctx.send(embed=SuccessfulMessage("Я сбросил настройки вашей комнаты"))
