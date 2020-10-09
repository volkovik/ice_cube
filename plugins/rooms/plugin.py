from typing import Union

import discord
from discord import PermissionOverwrite as Permissions
from discord.ext import commands
from discord.ext.commands import CommandError

from core.commands import Cog, Command
from core.database import UserPermissionsOfRoom
from core.templates import PermissionsForRoom, DefaultEmbed as Embed, SuccessfulMessage
from main import Session

from plugins.rooms.utils import get_server_settings, get_user_settings, add_user_settings, get_all_permissions, \
    get_permissions, add_permissions

# user's permissions for his room
OWNER_PERMISSIONS = Permissions(manage_channels=True, connect=True, speak=True)


def get_owner(channel: discord.VoiceChannel) -> Union[discord.Member, None]:
    owner = [m for m, p in channel.overwrites.items() if p == OWNER_PERMISSIONS]

    if len(owner) == 0:
        return None
    else:
        return owner[0]


def room_is_locked_predicate(ctx: commands.Context):
    """Returns user's room is locked"""
    session = Session()
    settings = get_user_settings(session, ctx.guild, ctx.author)
    session.close()
    return settings is not None and settings.is_locked


def room_is_locked():
    """Checks user's room is locked"""
    return commands.check(room_is_locked_predicate)


def room_is_not_locked():
    """Checks user's room isn't locked"""
    def predicate(ctx):
        return not room_is_locked_predicate(ctx)

    return commands.check(predicate)


class Rooms(Cog, name="Приватные комнаты"):
    @commands.Cog.listener("on_voice_state_update")
    async def room_master(self, user, before, after):
        """Creating rooms and deleting rooms without users"""
        server = after.channel.guild if before.channel is None else before.channel.guild

        session = Session()
        server_settings = get_server_settings(session, server)

        if server_settings is None:
            session.close()
            return
        else:
            # a voice channel that creates rooms
            creator_rooms = server.get_channel(server_settings.creator)

        # if the voice channel doesn't exist or it doesn't have category, delete server's settings from database
        if creator_rooms is None or creator_rooms.category is None:
            session.delete(server_settings)
            session.commit()
            session.close()
            return
        else:
            rooms_category = creator_rooms.category  # a category that will contain rooms

        if before.channel is not None and get_owner(before.channel) == user and after.channel == creator_rooms:
            await user.move_to(before.channel)
            return

        # when the user have leaved the voice channel
        if before.channel:
            channel = before.channel

            if channel in rooms_category.voice_channels and channel != creator_rooms and len(channel.members) == 0:
                await channel.delete()

        # when the user have joined the voice channel
        if after.channel:
            channel = after.channel

            # if the voice channel that the user joined, create a room
            if creator_rooms == channel:
                # user's settings from database
                user_settings = get_user_settings(session, server, user)
                everyone = server.default_role

                # if user's settings dont't exist, create default settings and write them in database
                if user_settings is None:
                    user_settings = add_user_settings(session, server, user)
                    session.commit()

                # voice channel's permissions
                permissions_for_room = {
                    user: OWNER_PERMISSIONS,
                    everyone: Permissions(connect=not user_settings.is_locked)
                }

                # voice channel's permissions from database
                users_with_permissions = get_all_permissions(session, server, user)

                for perms in users_with_permissions:
                    user_with_perms = server.get_member(perms.user)

                    # if user doesn't exist in the server, delete a permission from database
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
        """Checking if a deleted channel is a voice channel that creates rooms or it's a category that contains rooms"""
        session = Session()
        settings = get_server_settings(session, channel.guild)

        if settings is not None and (settings.creator == channel.id or
                                     channel.guild.get_channel(settings.creator).category is None):
            session.delete(settings)
            session.commit()

        session.close()

    @commands.Cog.listener("on_guild_channel_update")
    async def voice_master_checker_updated_channels(self, before, after):
        """Checking if a edited channel is a voice channel that creates rooms"""
        server = before.guild

        session = Session()
        server_settings = get_server_settings(session, server)

        # if the channel is a voice channel that creates room and this channel moved to another category, delete
        # settings from database
        if before.id == server_settings.creator and before.category != after.category:
            session.delete(server_settings)
            session.commit()
        else:
            # if the channel is a room, we will find special permissions for owner of this room
            owner = get_owner(before)

            # if the channel has special permissions, start check all changes
            if owner:
                user_settings = get_user_settings(session, server, owner)

                room = after
                everyone = server.default_role

                # set room's settings to database
                user_settings.name = room.name if room.name != owner.display_name else None
                user_settings.user_limit = room.user_limit
                user_settings.bitrate = room.bitrate // 1000
                user_settings.is_locked = room.overwrites_for(everyone) == Permissions(connect=False)
                session.commit()

                # permissions from the room
                def check(p):
                    return type(p[0]) is discord.Member and p[0].id != owner.id and \
                           p[1] is not PermissionsForRoom.default

                permissions_from_voice = dict(filter(
                    check,
                    map(lambda m: (m[0], PermissionsForRoom(m[1].connect)), room.overwrites.items())
                ))

                # room's permissions from database
                data_from_db = get_all_permissions(session, server, owner)

                # reformat view of permissions from database for comparing
                permissions_from_db = {}

                for user in data_from_db:
                    member = server.get_member(int(user.user_id))

                    if member is not None:
                        permissions_from_db[member] = user.permissions

                # identify which users is added, deleted, modified
                added = [(m, p) for m, p in permissions_from_voice.items() if m not in permissions_from_db]
                deleted = [(m, p) for m, p in permissions_from_db.items() if m not in permissions_from_voice]
                modified = [(m, p) for m, p in permissions_from_voice.items()
                            if m in permissions_from_db and permissions_from_db[m] != permissions_from_voice[m]]

                db_kwargs = {
                    "server_id": str(server.id),
                    "owner_id": str(owner.id)
                }

                # make changes in database
                for member, perms in added:
                    session.add(UserPermissionsOfRoom(**db_kwargs, user_id=str(member.id), permissions=perms))
                for member, _ in deleted:
                    session.query(UserPermissionsOfRoom).filter_by(**db_kwargs, user_id=str(member.id)).delete()
                for member, perms in modified:
                    session.query(UserPermissionsOfRoom).filter_by(**db_kwargs,
                                                                   user_id=str(member.id)).first().permissions = perms
                session.commit()

        session.close()

    @commands.group(name="room", aliases=["r"])
    async def room_settings(self, ctx):
        """Настройка вашей приватной комнаты"""
        user = ctx.author
        server = ctx.guild

        session = Session()
        server_settings = get_server_settings(session, server)
        creator = server.get_channel(server_settings.creator)
        # if a channel from database doesn't exist, ignore
        if creator is None:
            session.close()
            return

        user_settings = get_user_settings(session, server, user)
        # if the user haven't created a room in this server, notify that he must create room to make changes in database
        # before he can use this command
        if not user_settings:
            session.close()
            raise CommandError(f"Вы не использовали до этого приватные комнаты на этом сервере. Чтобы пользоваться "
                               f"командой `{ctx.prefix}{ctx.command}`, создайте свою комнату, зайдя в голосовой канал "
                               f"`{creator}`")

        # if command is raised without any subcommands, just send info about user's room
        if ctx.invoked_subcommand is None:
            message = Embed(title=f"Комната пользователя \"{user.display_name}\"")
            message.set_footer(text=f"Посмотреть все доступные команды для управления комнатой можно с помощью команды "
                                    f"{ctx.prefix}help {ctx.command}")

            # get settings from database
            user_settings = get_user_settings(session, server, user)
            name = user_settings.name if user_settings.name is not None else user.display_name
            is_locked = user_settings.is_locked
            user_limit = user_settings.user_limit
            bitrate = user_settings.bitrate

            # room's permissions from database
            data_from_db = get_all_permissions(session, server, user)

            # room's permissions as dict
            permissions = {}

            for perm in data_from_db:
                member = server.get_member(int(perm.user_id))

                if member is not None:
                    permissions[member] = perm.permissions.value

            # generate info about general settings of room
            message.description = f"**Название: ** {name}\n" \
                                  f"**Доступ:** {'закрытый' if is_locked else 'открытый'}\n" \
                                  f"**Лимит пользователей:** {user_limit if user_limit != 0 else 'нет'}\n" \
                                  f"**Битрейт:** {bitrate} кбит/с"

            # generate info about access to room for certain users
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
    @room_is_not_locked()
    async def lock_room(self, ctx):
        """Закрыть комнату от посторонних участников"""
        user = ctx.author
        server = ctx.guild

        session = Session()
        settings = get_user_settings(session, server, user)
        settings.is_locked = True
        session.commit()
        session.close()

        if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
            await user.voice.channel.set_permissions(server.default_role, overwrite=Permissions(connect=False))

        await ctx.send(embed=SuccessfulMessage("Я закрыл вашу комнату"))

    @room_settings.command(cls=Command, name="unlock")
    @room_is_locked()
    async def unlock_room(self, ctx):
        """Открыть комнату для посторонних участников"""
        user = ctx.author
        server = ctx.guild

        session = Session()
        settings = get_user_settings(session, server, user)
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
        """Поставить лимит пользователей для комнаты"""
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
        """Измененить название команты"""
        user = ctx.author
        server = ctx.guild

        if name is not None and len(name) > 32:
            raise CommandError("Название канала не должно быть больше 32-ух символов")

        session = Session()
        settings = get_user_settings(session, server, user)

        if settings.name is None and name is None:
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
        """Изменить битрейт (качество звука) комнаты"""
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
        """Кикнуть пользователя из вашей комнаты"""
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
        """Дать доступ пользователю заходить в комнату"""
        owner = ctx.author
        server = ctx.guild

        session = Session()
        permissions_from_db = get_permissions(session, server, owner, user)
        perms = PermissionsForRoom.allowed

        if permissions_from_db is not None and permissions_from_db.permissions == perms:
            session.close()
            raise CommandError("Этот участник уже имеет доступ к вашей комнате")
        else:
            if permissions_from_db is None:
                add_permissions(session, server, owner, user, perms)
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
        """Заблокировать доступ пользователю заходить в комнату"""
        owner = ctx.author
        server = ctx.guild

        session = Session()
        permissions_from_db = get_permissions(session, server, owner, user)
        perms = PermissionsForRoom.banned

        if permissions_from_db is not None and permissions_from_db.permissions == perms:
            session.close()
            raise CommandError("У этого участника уже заблокирован доступ к вашей комнате")
        else:
            if permissions_from_db is None:
                add_permissions(session, server, owner, user, perms)
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
        """Поставить доступ к каналу у пользователя по умолчанию"""
        owner = ctx.author
        server = ctx.guild

        session = Session()
        permissions_from_db = get_permissions(session, server, owner, user)

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
        """Сбросить все настройки комнаты"""
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
