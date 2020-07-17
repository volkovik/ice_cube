import discord
from discord.ext import commands
from discord import PermissionOverwrite as Permissions
from discord.ext.commands import CommandError
from sqlalchemy.orm import sessionmaker

from main import engine_db
from core.database import ServerSettingsOfRooms, UserSettingsOfRoom, UserPermissionsOfRoom, PermissionsForRoom
from core.commands import BotCommand
from core.templates import SuccessfulMessage

# Настройки войса для пользователя, которым им владеет
OWNER_PERMISSIONS = Permissions(manage_channels=True, connect=True, speak=True)


def get_user_settings(server, owner):
    """
    Выдаёт настройки из базы данных комнаты пользователя на определённом сервере

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param owner: пользователь владеющей комнатой
    :type owner: discord.Member or discord.User
    :return: настроки комнаты, если есть данные в базе данных
    :rtype: dict or None
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    settings_from_db = session.query(UserSettingsOfRoom).filter_by(server_id=server.id, owner_id=owner.id).first()

    if settings_from_db is not None:
        settings = settings_from_db.__dict__
        settings["name"] = owner.display_name if settings["name"] is None else settings["name"]

        return settings_from_db.__dict__
    else:
        return None


def update_user_settings(server, owner, **settings):
    """
    Обновление пользовательских настроек комнат в базе данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param owner: пользователь владеющей комнатой
    :type owner: discord.Member or discord.User
    :param settings: параметры, которые должны быть изменены
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    settings_from_db = session.query(UserSettingsOfRoom).filter_by(server_id=server.id, owner_id=owner.id).first()

    if settings_from_db is None:
        settings_from_db = UserSettingsOfRoom(server_id=server.id, owner_id=owner.id)
        session.add(settings_from_db)

    if owner.voice is not None and owner.voice.channel.overwrites_for(owner) == OWNER_PERMISSIONS:
        room = owner.voice.channel
        perms_connection = Permissions(connect=False)

        # Настройки из войса пользователя
        settings.setdefault("is_locked", room.overwrites_for(server.default_role) == perms_connection)
        settings.setdefault("user_limit", room.user_limit)
        settings.setdefault("bitrate", room.bitrate)
        settings.setdefault("name", room.name if room.name != owner.display_name else None)
    else:
        settings_db = get_user_settings(server, owner)

        if settings_db is not None:
            # Настройки из базы данных
            settings.setdefault("is_locked", settings_db["is_locked"])
            settings.setdefault("user_limit", settings_db["user_limit"])
            settings.setdefault("bitrate", settings_db["bitrate"])
            settings.setdefault("name", settings_db["name"])
        else:
            # Настройки, которые стоят по умолчанию, когда пользователь создаёт комнату впервые
            settings.setdefault("is_locked", False)
            settings.setdefault("user_limit", 0)
            settings.setdefault("bitrate", 64)
            settings.setdefault("name", None)

    settings_from_db.is_locked = settings["is_locked"]
    settings_from_db.user_limit = settings["user_limit"]
    settings_from_db.bitrate = settings["bitrate"]
    settings_from_db.name = settings["name"]

    session.commit()


def get_permissions_for_all_users(server, owner):
    """
    Выдаёт словарь с правами пользователей

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param owner: пользователь владеющей комнатой
    :type owner: discord.Member or discord.User
    :return: словарь с правами пользователей
    :rtype: dict
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    all_permissions = session.query(UserPermissionsOfRoom).filter_by(server_id=server.id, owner_id=owner.id).all()

    users = {}

    for user in all_permissions:
        member = server.get_member(user.user_id)

        if member is not None:
            users[member] = Permissions(connect=user.permissions.value)
        else:
            user.delete()

    session.commit()

    return users


def update_permissions_for_all_users(server, owner, users):
    """
    Обновляет список пользователей, сопостовляя его со списком из базы данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param owner: пользователь владеющей комнатой
    :type owner: discord.Member or discord.User
    :param users: словарь из пользователей и их прав, которые нужно заменить на текущий список в базе данных
    :type users: dict
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    users_db = get_permissions_for_all_users(server, owner)

    # Если в базе данных нет какой-либо информации правах пользователей
    if users_db is None:
        for user, permissions in users.items():
            permissions_for_user = UserPermissionsOfRoom(
                server_id=server.id,
                owner_id=owner.id,
                user_id=user.id,
                permission=PermissionsForRoom(permissions.connect)
            )

            session.add(permissions_for_user)
    else:
        # Ищет пользователей, которых нет в базе данных
        for user, permissions in users:
            permissions_for_user = UserPermissionsOfRoom(
                server_id=server.id,
                owner_id=owner.id,
                user_id=user.id,
                permission=PermissionsForRoom(permissions.connect)
            )

            session.add(permissions_for_user)

        # Удаляет записи в базе данных о пользователях, которые не были в голосовом канале
        for user, _ in set(users.items()) - set(users.items()):
            session.query(UserPermissionsOfRoom).filter_by(
                server_id=server.id, owner_id=owner.id, user_id=user.id
            ).delete()

    session.commit()


def update_permissions_for_user(server, owner, user, permissions):
    """
    Даёт права доступа пользователю в базе данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param owner: пользователь владеющей комнатой
    :type owner: discord.Member or discord.User
    :param user: пользователь, которому нужно дать доступ
    :type user: discord.Member or discord.User
    :param permissions: права для пользователя
    :type permissions: PermissionsForRoom
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    permissions_for_user = session.query(UserPermissionsOfRoom).filter_by(
        server_id=server.id, owner_id=owner.id, user_id=user.id
    ).first()

    if permissions_for_user is None:
        permissions_for_user = UserPermissionsOfRoom(server_id=server.id, owner_id=owner.id, user_id=user.id)
        session.add(permissions_for_user)

    permissions_for_user.permissions = permissions

    session.commit()


def remove_permissions_for_user(server, owner, user):
    """
    Забирает права доступа у пользователя в базе данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param owner: пользователь владеющей комнатой
    :type owner: discord.Member or discord.User
    :param user: пользователь, у которого нужно убрать доступ к комнате
    :type user: discord.Member or discord.User
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    permissions_for_user = session.query(UserPermissionsOfRoom).filter_by(
        server_id=server.id, owner_id=owner.id, user_id=user.id
    ).first()

    if permissions_for_user is not None:
        session.delete(permissions_for_user)

    session.commit()


def get_room_creator(server):
    """
    Выдача канала, который создаёт комнаты для пользователя

    :param server: сервер, на котром нужно найти канал
    :type server: discord.Guild
    :return: голосовой канал, если в базе данных есть данные
    :rtype: discord.VoiceChannel or None
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    channel_from_db = session.query(ServerSettingsOfRooms).filter_by(server_id=server.id).first()

    channel = server.get_channel(channel_from_db.channel_id_creates_rooms) if channel_from_db is not None else None

    if channel is None:
        delete_room_creator(server)

    return channel


def delete_room_creator(server):
    """
    Удаляет записи в базе данных о канале, который создаёт комнаты

    :param server: Сервер, для которого нужно удалить записи
    :type server: discord.Guild
    """

    Session = sessionmaker(bind=engine_db)
    session = Session()

    channel_from_db = session.query(ServerSettingsOfRooms).filter_by(server_id=server.id).first()

    if channel_from_db is not None:
        session.delete(channel_from_db)

    session.commit()


def check_room_settings(server, owner, channel, settings):
    """
    Проверяет настройки войса и настроек из settings. Если есть различия, то в базе данных обновляются данные

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param owner: пользователь владеющей комнатой
    :type owner: discord.Member or discord.User
    :param channel: войс, из которого берутся настройки
    :type channel: discord.VoiceChannel
    :param settings: настройки, с которыми сравниваются настройки войса
    :type settings: dict
    """

    everyone = server.default_role

    settings_from_voice = {
        "name": channel.name if channel.name != owner.display_name else None,
        "user_limit": channel.user_limit,
        "bitrate": channel.bitrate // 1000,
        "is_locked": channel.overwrites_for(everyone) == Permissions(connect=False)
    }

    # Если настройки из базы данных несостыкуются с настройками текущего войса или же настройки не
    # зафиксированны в базе данных, то записать изменения в базу данных
    if settings != settings_from_voice:
        update_user_settings(server, owner, **settings_from_voice)

    def check(p):
        return type(p[0]) is discord.Member and p[1] == Permissions(connect=True) and p[0].id != owner.id

    # Пользователи, у который есть доступ к каналу, из текущего войса и из базы данных
    users_from_voice = dict(filter(check, channel.overwrites.items()))
    users_from_db = get_permissions_for_all_users(server, owner)

    # Если список пользователей из войса и из базы данных не сходятся, то обновить список в базе данных
    if users_from_voice != users_from_db:
        update_permissions_for_all_users(server, owner, users_from_voice)


class Rooms(commands.Cog, name="Приватные комнаты"):
    def __init__(self, bot):
        self.client = bot

    async def cog_check(self, ctx):
        author = ctx.author
        server = ctx.guild

        creator = get_room_creator(server)

        # Если на сервере нет системы комнат, то выдать ошибку
        if creator is None:
            raise CommandError("У данного сервера нет системы приватных комнат")

        settings = get_user_settings(server, author)

        # Если участник, на данный момент, в своей комнате
        if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
            # Проверяет настройки войса с настройками из базы данных
            check_room_settings(server, author, author.voice.channel, settings)
        elif settings is None:
            raise CommandError(f"Ранее, вы не использовали комнаты на этом сервере. Чтобы использовать эту команду, "
                               f"создайте комнату с помощью голосового канала `{creator.name}`")

        return True

    @commands.Cog.listener("on_voice_state_update")
    async def voice_master(self, user, before, after):
        """
        Создание и удаление команты, когда пользователей заходит, выходит или перемещается по голосовым каналам
        """

        server = after.channel.guild if before.channel is None else before.channel.guild
        creator = get_room_creator(server)

        # если канал не найден, то завершить процесс
        if creator is None:
            return

        # если канал не имеет категории, то удалить этот канал в базе данных и завершить процесс
        if creator.category is None:
            delete_room_creator(server)

            return
        else:
            creator_category = creator.category

        # Когда пользователь перемещается по войсам или только что присоеденился к войсу
        if after.channel:
            channel = after.channel

            # Если канал, в котом сейчас находится пользователь является тем каналом, который создаёт комнаты, то
            # начинается конфигурация комнаты
            if creator == channel:
                settings = get_user_settings(server, user)
                everyone = server.default_role

                if settings is None:
                    update_user_settings(server, user)
                    settings = get_user_settings(server, user)

                permissions_for_room = {
                    user: OWNER_PERMISSIONS,
                    everyone: Permissions(connect=not settings["is_locked"])
                }
                permissions_for_room.update(get_permissions_for_all_users(server, user))

                room = await server.create_voice_channel(
                    name=settings["name"],
                    category=creator_category,
                    overwrites=permissions_for_room,
                    user_limit=settings["user_limit"],
                    bitrate=settings["bitrate"] * 1000
                )

                await user.move_to(room)

        if before.channel:
            # когда пользователь выходит из голосового канала
            channel = before.channel

            if channel in creator_category.voice_channels and channel != creator and len(channel.members) == 0:
                # удалить голосовой канал, если он является комнатой и в ней нет пользователей
                await channel.delete()

    @commands.Cog.listener("on_guild_channel_delete")
    async def voice_master_checker_deleted_channels(self, channel):
        """
        Проверка удалённого канала на канал, который создаёт приватные комнаты
        """

        creator = get_room_creator(channel.guild)

        # Если удалённый был каналом, который создаёт комнаты, то удалить его в базе данных
        if channel == creator:
            delete_room_creator(channel.guild)

    @commands.Cog.listener("on_guild_channel_update")
    async def voice_master_checker_updated_channels(self, before, after):
        """
        Проверка изменённого канала на канал, который создаёт приватные комнаты
        """

        creator = get_room_creator(before.guild)

        # Если у канала удалили категорию или его переместили в другую, то удалить канал в базе данных и на сервере
        if before == creator and before.category != after.category:
            delete_room_creator(after.guild)
            await after.delete()

            return

        server = after.guild
        # Владелец комнаты
        author = [m for m, p in before.overwrites.items() if p == OWNER_PERMISSIONS][0]
        settings = get_user_settings(server, author)

        # Проверяет настройки войса с настройками из базы данных
        check_room_settings(after.guild, author, after, settings)

    @commands.group(name="room")
    async def room_settings(self, ctx):
        """
        Настройка вашей приватной комнаты
        """

        # Если команда была использована без сабкоманды, то отправить информацию о комнате
        if ctx.invoked_subcommand is None:
            author = ctx.author
            server = ctx.guild

            settings = get_user_settings(server, author)
            creator = get_room_creator(server)

            if settings is None:
                raise CommandError(f"Вы не ещё не использовали приватные комнаты на этом сервере. Зайдите в голосовой "
                                   f"канал `{creator}`, чтобы создать комнату")

            name = settings["name"]
            user_limit = settings["user_limit"]
            bitrate = settings["bitrate"]
            is_locked = settings["is_locked"]

            message = discord.Embed(title=f"Информация о комнате пользователя \"{author.display_name}\"")
            message.set_footer(text=f"Посмотреть все доступные команды для управления комнатой можно "
                                    f"через {ctx.prefix}help room")

            users_with_permissions = get_permissions_for_all_users(server, author)

            # Информация о комнате
            message.description = f"**Название: ** {name}\n" \
                                  f"**Доступ:** {'закрытый' if is_locked else 'открытый'}\n" \
                                  f"**Лимит пользователей:** {user_limit if user_limit != 0 else 'нет'}\n" \
                                  f"**Битрейт:** {bitrate} кбит/с"

            # Перечесление пользователей с правами доступа
            if users_with_permissions is not None:
                allowed = list(filter(lambda p: p[1].connect is True, users_with_permissions.items()))
                banned = list(filter(lambda p: p[1].connect is False, users_with_permissions.items()))

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

    @room_settings.command(cls=BotCommand, name="lock")
    async def lock_room(self, ctx):
        """
        Закрыть комнату от посторонних участников
        """

        author = ctx.author
        server = ctx.guild
        everyone = server.default_role
        is_locked = get_user_settings(server, author)["is_locked"]

        if is_locked:
            raise CommandError("Комната уже закрыта")
        else:
            update_user_settings(server, author, is_locked=True)

            if author.voice is not None or author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.set_permissions(everyone, overwrite=Permissions(connect=False))

            await ctx.send(embed=SuccessfulMessage("Я закрыл вашу комнату"))

    @room_settings.command(cls=BotCommand, name="unlock")
    async def unlock_room(self, ctx):
        """
        Открыть комнату для посторонних участников
        """

        author = ctx.author
        server = ctx.guild
        everyone = server.default_role
        is_locked = get_user_settings(server, author)["is_locked"]

        if not is_locked:
            raise CommandError("Комната уже открыта")
        else:
            update_user_settings(server, author, is_locked=False)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.set_permissions(everyone, overwrite=Permissions(connect=True))

            await ctx.send(embed=SuccessfulMessage("Я открыл вашу комнату"))

    @room_settings.command(
        cls=BotCommand, name="limit",
        usage={"лимит": ("максимальное количество участников, которое может подключиться к комнате (если оставить "
                         "пустым, лимит сбросится)", True)}
    )
    async def room_users_limit(self, ctx, limit: int = 0):
        """
        Поставить лимит пользователей в вашей комнате
        """

        author = ctx.author
        server = ctx.guild
        current_limit = get_user_settings(server, author)["user_limit"]

        if 0 > limit:
            raise CommandError("Лимит не должен быть меньше 0")
        elif limit > 99:
            raise CommandError("Лимит не должен быть больше 99")

        if current_limit == limit == 0:
            raise CommandError("Вы ещё не поставили лимит пользователей для комнаты, чтобы сбрасывать его")
        elif current_limit == limit:
            raise CommandError("Комната уже имеет такой лимит")
        else:
            if limit == 0:
                message = SuccessfulMessage("Я сбросил лимит пользователей в вашей комнате")
                update_user_settings(server, author, user_limit=limit)
            else:
                message = SuccessfulMessage("Я изменил лимит пользователей для вашей комнаты")
                update_user_settings(server, author, user_limit=limit)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.edit(user_limit=limit)

            await ctx.send(embed=message)

    @room_settings.command(
        cls=BotCommand, name="name",
        usage={"название": ("новое название комнаты (если оставить пустым, то название комнаты изменится на ваш ник)",
                            True)}
    )
    async def rename_room(self, ctx, *, name=None):
        """
        Измененить название команты
        """

        author = ctx.author
        server = ctx.guild
        current_name = get_user_settings(server, author)["name"]

        if name is not None and len(name) > 32:
            raise CommandError("Название канала не должно быть больше 32-ух символов")

        if current_name == author.display_name and name is None:
            raise CommandError("Вы ещё не поставили название для комнаты, чтобы сбрасывать его")
        elif name == current_name:
            raise CommandError("Комната уже имеет такое название")
        else:
            if name is None:
                message = SuccessfulMessage("Я сбросил название вашего канала")
                name = author.display_name
                update_user_settings(server, author, name=None)
            else:
                message = SuccessfulMessage("Я изменил название вашей комнаты")
                update_user_settings(server, author, name=name)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.edit(name=name)

            await ctx.send(embed=message)

    @room_settings.command(
        cls=BotCommand, name="bitrate",
        usage={"битрейт": ("кбит/с, чем больше, тем лучше качество звука (если оставить пустым, битрейт будет 64)",
                           True)}
    )
    async def change_room_bitrate(self, ctx, bitrate: int = 64):
        """
        Изменить битрейт (качество звука) комнаты
        """

        author = ctx.author
        server = ctx.guild
        current_bitrate = get_user_settings(server, author)["bitrate"]
        max_bitrate = int(server.bitrate_limit // 1000)

        if 8 > bitrate:
            raise CommandError("Битрейт не должен быть меньше 8")
        elif bitrate > max_bitrate:
            raise CommandError(f"Битрейт не должен быть больше {max_bitrate}")

        if current_bitrate == bitrate == 64:
            raise CommandError("Вы ещё не изменяли битрейт, чтобы сбрасывать его по умолчанию")
        elif current_bitrate == bitrate:
            raise CommandError("Комната уже имеет такой битрейт")
        else:
            if bitrate == 0:
                message = SuccessfulMessage("Я сбросил битрейт в вашей комнате")
                update_user_settings(server, author, bitrate=bitrate)
            else:
                message = SuccessfulMessage("Я изменил битрейт в вашей комнате")
                update_user_settings(server, author, bitrate=bitrate)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.edit(bitrate=bitrate * 1000)

            await ctx.send(embed=message)

    @room_settings.command(
        cls=BotCommand, name="allow",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def allow_member_to_join_room(self, ctx, user: commands.MemberConverter):
        """
        Дать доступ пользователю заходить в комнату
        """

        author = ctx.author
        server = ctx.guild
        users_with_permissions = get_permissions_for_all_users(server, author)
        permissions = PermissionsForRoom.allowed

        if user in users_with_permissions and users_with_permissions[user].connect == permissions.value:
            raise CommandError("Этот участник уже имеет доступ к вашей комнате")
        else:
            update_permissions_for_user(server, author, user, permissions)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.set_permissions(user, overwrite=Permissions(connect=permissions.value))

            await ctx.send(embed=SuccessfulMessage(f"Я дал доступ `{user.display_name}` к вашей комнате"))

    @room_settings.command(
        cls=BotCommand, name="ban",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def ban_member_from_room(self, ctx, user: commands.MemberConverter):
        """
        Заблокировать доступ пользователю заходить в комнату
        """

        author = ctx.author
        server = ctx.guild
        users_with_permissions = get_permissions_for_all_users(server, author)
        permissions = PermissionsForRoom.banned

        if user in users_with_permissions and users_with_permissions[user].connect == permissions.value:
            raise CommandError("У этого участника уже заблокирован доступ к вашей комнате")
        else:
            update_permissions_for_user(server, author, user, permissions)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.set_permissions(user, overwrite=Permissions(connect=permissions.value))

            await ctx.send(embed=SuccessfulMessage(f"Я заброкировал доступ у `{user.display_name}` к вашей комнате"))

    @room_settings.command(
        cls=BotCommand, name="remove",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def set_default_permissions_for_member(self, ctx, user: commands.MemberConverter):
        """
        Поставить доступ к каналу у пользователя по умолчанию
        """

        author = ctx.author
        server = ctx.guild
        users_with_permissions = get_permissions_for_all_users(server, author)

        if user not in users_with_permissions:
            raise CommandError("Этот участник не имеет особых прав, чтобы сбрасывать их")
        else:
            remove_permissions_for_user(server, author, user)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.set_permissions(user, overwrite=Permissions(connect=None))

            await ctx.send(embed=SuccessfulMessage(f"Я сбросил права доступа у `{user.display_name}` к вашей комнате"))

    @room_settings.command(name="reset")
    async def reset_room_settings(self, ctx):
        """
        Сбросить все настройки комнаты
        """

        author = ctx.author
        server = ctx.guild
        everyone = server.default_role
        settings = get_user_settings(server, author)
        default_settings = {
            "name": author.display_name,
            "user_limit": 0,
            "bitrate": 64,
            "is_locked": False
        }

        if settings == default_settings:
            raise CommandError("Вы ещё не сделали каких-либо изменений для комнаты, чтобы сбрасывать его настройки")
        else:
            update_user_settings(server, author, **default_settings)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                channel = author.voice.channel

                await channel.edit(name=default_settings["name"], user_limit=default_settings["user_limit"],
                                   bitrate=default_settings["bitrate"] * 1000)
                await channel.set_permissions(everyone, overwrite=Permissions(connect=True))

            await ctx.send(embed=SuccessfulMessage("Я сбросил настройки вашей комнаты"))

    @commands.group(name="setrooms", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def rooms_settings(self, ctx):
        """
        Настройка приватных комнат на сервере
        """

        await ctx.send_help(ctx.command.name)

    @rooms_settings.command(cls=BotCommand, name="enable")
    @commands.has_permissions(administrator=True)
    async def create_rooms_system(self, ctx):
        """
        Создать приватные комнаты на сервере
        """

        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server_id": server.id}

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        last_voice = result[0] if result is not None else None

        if last_voice is not None:
            cursor.close()
            db.close()

            raise CommandError("У вас уже есть приватные комнаты")
        else:
            message = SuccessfulMessage("Я успешно включил систему приватных комнат")

            category = await server.create_category_channel(name="Приватные комнаты")
            voice = await server.create_voice_channel(name="Создать комнату", category=category)

            data_sql["voice_id"] = voice.id

            cursor.execute("INSERT INTO rooms_server_settings(server_id, channel_id)\n"
                           "VALUES(%(server_id)s, %(voice_id)s)\n"
                           "ON DUPLICATE KEY UPDATE channel_id=%(voice_id)s", data_sql)

            cursor.close()
            db.close()

        await ctx.send(embed=message)

    @rooms_settings.command(cls=BotCommand, name="disable")
    @commands.has_permissions(administrator=True)
    async def remove_rooms_system(self, ctx):
        """
        Выключить и удалить приватные комнаты на сервере
        """

        server = ctx.guild

        db = mysql.connector.connect(**CONFIG["database"])
        db.autocommit = True
        cursor = db.cursor()

        data_sql = {"server_id": server.id}

        cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)
        result = cursor.fetchone()
        last_voice = result[0] if result is not None else None

        if last_voice is None:
            cursor.close()
            db.close()

            raise CommandError("На вашем сервере не поставлены приватные комнаты")
        else:
            message = SuccessfulMessage("Я успешно выключил и удалил систему приватных комнат")

            voice = server.get_channel(int(last_voice))
            category = voice.category

            if len(category.voice_channels) != 0:
                for channel in category.voice_channels:
                    await channel.delete()

            await category.delete()

            cursor.execute("DELETE FROM rooms_server_settings WHERE server_id=%(server_id)s", data_sql)

            cursor.close()
            db.close()

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Rooms(bot))
