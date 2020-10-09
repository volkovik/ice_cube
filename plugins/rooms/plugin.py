import discord
from discord import PermissionOverwrite as Permissions
from discord.ext import commands
from discord.ext.commands import CommandError

from core.commands import Cog
from core.database import UserPermissionsOfRoom
from core.templates import PermissionsForRoom, DefaultEmbed as Embed
from main import Session

from plugins.rooms.utils import get_server_settings, get_user_settings, add_user_settings, get_all_permissions


# user's permissions for his room
OWNER_PERMISSIONS = Permissions(manage_channels=True, connect=True, speak=True)


def rooms_system_is_enabled(ctx, session):
    settings = get_server_settings(session, ctx.guild)
    return settings is not None and ctx.guild.get_channel(settings.creator) is not None


def rooms_system_is_on():
    def predicate(ctx):
        session = Session()
        is_on = rooms_system_is_enabled(ctx, session)
        session.close()

        return is_on

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
        """Checking if a deleted channel is a voice channel that creates rooms"""
        session = Session()
        settings = get_server_settings(session, channel.guild)

        if settings is not None and settings.creator == channel.id:
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
            owner = [m for m, p in before.overwrites.items() if p == OWNER_PERMISSIONS]

            # if the channel has special permissions, start check all changes
            if len(owner) != 0:
                owner = owner[0]
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

    @commands.group(name="room")
    @rooms_system_is_on()
    async def room_settings(self, ctx):
        """
        Настройка вашей приватной комнаты
        """

        user = ctx.author
        server = ctx.guild

        session = Session()
        user_settings = get_user_settings(session, server, user)

        # if the user haven't created a room in this server, notify that he must create room to make changes in database
        # before he can use this command
        if not user_settings:
            server_settings = get_server_settings(session, server)
            creator = server.get_channel(server_settings.creator)
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
