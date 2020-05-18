import discord
import mysql.connector
from discord.ext import commands
from discord import PermissionOverwrite as Permissions
from discord.ext.commands import CommandError

from main import CONFIG
from core.commands import BotCommand
from core.templates import SuccessfulMessage

# Настройки войса для пользователя, которым им владеет
OWNER_PERMISSIONS = Permissions(manage_channels=True, connect=True, speak=True)


def get_user_settings(server, user):
    """
    Выдаёт настройки из базы данных комнаты пользователя на определённом сервере

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param user: пользователь владеющей комнатой
    :type user: discord.Member or discord.User
    :return: настроки комнаты, если есть данные в базе данных
    :rtype: dict or None
    """

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    sql_format = {
        "server": server.id,
        "user": user.id
    }

    cursor.execute("SELECT * FROM rooms_user_settings WHERE server_id=%(server)s AND user_id=%(user)s", sql_format)
    result = cursor.fetchone()

    if result is not None:
        result = result[2:]

        settings = {
            "name": result[0] if result[0] is not None else user.display_name,
            "user_limit": result[1],
            "bitrate": result[2],
            "is_locked": True if result[3] else False
        }
    else:
        settings = None

    db.close()
    cursor.close()

    return settings


def update_user_settings(server, user, **settings):
    """
    Обновление пользовательских настроек комнат в базе данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param user: пользователь владеющей комнатой
    :type user: discord.Member or discord.User
    :param settings: параметры, которые должны быть изменены
    """

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    sql_format = {
        "server": server.id,
        "user": user.id
    }

    if user.voice is not None and user.voice.channel.overwrites_for(user) == OWNER_PERMISSIONS:
        # Настройки из войса пользователя

        room = user.voice.channel
        perms_connection = Permissions(connect=False)

        settings.setdefault("is_locked", room.overwrites_for(server.default_role) == perms_connection)
        settings.setdefault("user_limit", room.user_limit)
        settings.setdefault("bitrate", room.bitrate)
        settings.setdefault("name", room.name if room.name != user.display_name else None)
    else:
        settings_db = get_user_settings(server, user)

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

    sql_format.update(settings)

    cursor.execute(
        "INSERT INTO rooms_user_settings(server_id, user_id, name, user_limit, bitrate, is_locked) "
        "VALUES(%(server)s, %(user)s, %(name)s, %(user_limit)s, %(bitrate)s, %(is_locked)s) "
        "ON DUPLICATE KEY UPDATE name=%(name)s, user_limit=%(user_limit)s, bitrate=%(bitrate)s, "
        "is_locked=%(is_locked)s",
        sql_format
    )

    db.close()
    cursor.close()


def get_permissions_for_all_users(server, user):
    """
    Выдаёт список пользователей, которые у который есть право подключаться к комнате user

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param user: пользователь владеющей комнатой
    :type user: discord.Member or discord.User
    :return: список пользователей
    :rtype: list
    """

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    sql_format = {
        "server": server.id,
        "user": user.id
    }

    cursor.execute(
        "SELECT allowed_user_id FROM rooms_user_permissions "
        "WHERE server_id=%(server)s AND user_id=%(user)s",
        sql_format
    )
    result = cursor.fetchall()

    allowed_users = []

    for line in result:
        id = line[0]
        member = server.get_member(int(id))

        if member is not None:
            allowed_users.append(member)
        else:
            sql_format["allowed_user"] = id

            cursor.execute(
                "DELETE FROM rooms_user_permissions WHERE allowed_user_id=%(allowed_user)s",
                sql_format
            )

    cursor.close()
    db.cursor()

    return allowed_users if len(allowed_users) != 0 else None


def update_permissions_for_all_users(server, user, *allowed_users):
    """
    Обновляет список пользователей, сопостовляя его со списком из базы данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param user: пользователь владеющей комнатой
    :type user: discord.Member or discord.User
    :param allowed_users: список пользователей, которые нужно заменить на текущий список в базе данных
    :type allowed_users: discord.Member or discord.User
    """

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    allowed_users_db = get_permissions_for_all_users(server, user)

    sql_format = {
        "server": server.id,
        "user": user.id
    }

    # Ищет пользователей, которые имеют доступ к комнате
    for member in allowed_users:
        if (allowed_users_db is not None and member not in allowed_users_db) or allowed_users_db is None:
            sql_format["allowed_user"] = member.id

            cursor.execute(
                "INSERT INTO rooms_user_permissions(server_id, user_id, allowed_user_id) "
                "VALUES (%(server)s, %(user)s, %(allowed_user)s)",
                sql_format
            )

    # Удаляет пользователей из базы данных, которые не были в войсе
    if allowed_users_db is not None:
        for m in set(allowed_users_db) - set(allowed_users):
            sql_format["allowed_user"] = m.id

            cursor.execute(
                "DELETE FROM rooms_user_permissions WHERE server_id=%(server)s "
                "AND user_id=%(user)s AND allowed_user_id=%(allowed_user)s",
                sql_format
            )

    cursor.close()
    db.close()


def add_permissions_for_user(server, user, allowed_user):
    """
    Даёт права доступа пользователю в базе данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param user: пользователь владеющей комнатой
    :type user: discord.Member or discord.User
    :param allowed_user: пользователь, которому нужно дать доступ
    :type allowed_user: discord.Member or discord.User
    """

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    sql_format = {
        "server": server.id,
        "user": user.id,
        "allowed_user": allowed_user.id
    }

    cursor.execute(
        "INSERT IGNORE INTO rooms_user_permissions(server_id, user_id, allowed_user_id) "
        "VALUES (%(server)s, %(user)s, %(allowed_user)s)",
        sql_format
    )

    cursor.close()
    db.close()


def remove_permissions_for_user(server, user, allowed_user):
    """
    Забирает права доступа у пользователя в базе данных

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param user: пользователь владеющей комнатой
    :type user: discord.Member or discord.User
    :param allowed_user: пользователь, у которого нужно убрать доступ к комнате
    :type allowed_user: discord.Member or discord.User
    """

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    sql_format = {
        "server": server.id,
        "user": user.id,
        "allowed_user": allowed_user.id
    }

    cursor.execute(
        "DELETE FROM rooms_user_permissions "
        "WHERE server_id=%(server)s AND user_id=%(user)s AND allowed_user_id=%(allowed_user)s",
        sql_format
    )

    cursor.close()
    db.close()


def get_room_creator(server):
    """
    Выдача канала, который создаёт комнаты для пользователя

    :param server: сервер, на котром нужно найти канал
    :type server: discord.Guild
    :return: голосовой канал, если в базе данных есть данные
    :rtype: discord.VoiceChannel or None
    """

    db = mysql.connector.connect(**CONFIG["database"])
    cursor = db.cursor()

    sql_format = {
        "server": server.id
    }

    cursor.execute("SELECT channel_id FROM rooms_server_settings WHERE server_id=%(server)s", sql_format)
    result = cursor.fetchone()

    cursor.close()
    db.close()

    return server.get_channel(int(result[0])) if result is not None else None


async def delete_room_creator(channel):
    """
    Удаляет войс, который должен создавать комнаты из базы данных в дискорде

    :param channel: голосовой канал, который нужно удалить
    :type channel: discord.VoiceChannel
    """

    db = mysql.connector.connect(**CONFIG["database"])
    db.autocommit = True
    cursor = db.cursor()

    sql_format = {
        "server": channel.guild.id
    }

    cursor.execute("DELETE FROM rooms_server_settings WHERE server_id=%(server)s", sql_format)

    cursor.close()
    db.close()

    await channel.delete()


def check_room_settings(server, user, channel, settings):
    """
    Проверяет настройки войса и настроек из settings. Если есть различия, то в базе данных обновляются данные

    :param server: сервер, на котором находится комната
    :type server: discord.Guild
    :param user: пользователь владеющей комнатой
    :type user: discord.Member or discord.User
    :param channel: войс, из которого берутся настройки
    :type channel: discord.VoiceChannel
    :param settings: настройки, с которыми сравниваются настройки войса
    :type settings: dict
    """

    everyone = server.default_role

    settings_from_voice = {
        "name": channel.name if channel.name != user.display_name else None,
        "user_limit": channel.user_limit,
        "bitrate": channel.bitrate // 1000,
        "is_locked": channel.overwrites_for(everyone) == Permissions(connect=False)
    }

    # Если настройки из базы данных несостыкуются с настройками текущего войса или же настройки не
    # зафиксированны в базе данных, то записать изменения в базу данных
    if settings != settings_from_voice:
        update_user_settings(server, user, **settings_from_voice)

    def check(p):
        return type(p[0]) is discord.Member and p[1] == Permissions(connect=True) and p[0].id != user.id

    # Пользователи, у который есть доступ к каналу, из текущего войса и из базы данных
    allowed_users_from_voice = list(map(lambda u: u[0], filter(check, channel.overwrites.items())))
    allowed_users_from_db = get_permissions_for_all_users(server, user)

    # Если список пользователей из войса и из базы данных не сходятся, то обновить список в базе данных
    if allowed_users_from_voice != allowed_users_from_db:
        update_permissions_for_all_users(server, user, *allowed_users_from_voice)


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

        :param user: пользователь, у которого был обновлён VoiceState
        :param before: VoiceState до обновления
        :param after: VoiceState после обновления
        """

        server = after.channel.guild if before.channel is None else before.channel.guild
        creator = get_room_creator(server)

        # если канал не найден, то завершить процесс
        if creator is None:
            return

        # если канала нет на сервере или он не имеет категории, то удалить этот канал в базе данных и завершить процесс
        if creator is None or creator.category is None:
            await delete_room_creator(creator)

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
                allowed_users = get_permissions_for_all_users(server, user)
                everyone = server.default_role

                if settings is None:
                    settings = {
                        "name": user.display_name,
                        "user_limit": 0,
                        "is_locked": False,
                        "bitrate": 64
                    }

                permissions_for_room = {
                    user: OWNER_PERMISSIONS,
                    everyone: Permissions(connect=not settings["is_locked"])
                }

                # Если в базе данных имеются данные о правах пользователя, то добавить их в список
                if allowed_users is not None:
                    permissions = [Permissions(connect=True)] * len(allowed_users)
                    permissions_for_room.update(dict(zip(allowed_users, permissions)))

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

        :param channel: удалённый канал
        """

        creator = get_room_creator(channel.guild)

        # Если удалённый был каналом, который создаёт комнаты, то удалить его в базе данных
        if channel.id == creator:
            await delete_room_creator(channel)

    @commands.Cog.listener("on_guild_channel_update")
    async def voice_master_checker_updated_channels(self, before, after):
        """
        Проверка изменённого канала на канал, который создаёт приватные комнаты

        :param before: канало до обновления
        :param after: канал после обновления
        """

        creator = get_room_creator(before.guild)

        # Если у канала удалили категорию или его переместили в другую, то удалить канал в базе данных и на сервере
        if before.id == creator and after.category is None:
            delete_room_creator(before)

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

        # Если команда была использована без сабкоманды, то отправить информацию об комнате
        if ctx.invoked_subcommand is None:
            author = ctx.author
            server = ctx.guild
            name, user_limit, bitrate, is_locked = get_user_settings(server, author).values()

            message = discord.Embed(title=f"Информация о комнате пользователя \"{author.display_name}\"")
            message.set_footer(text=f"Посмотреть все доступные команды для управления комнатой можно "
                                    f"через {ctx.prefix}help user")

            allowed_members = get_permissions_for_all_users(server, author)

            # Информация о комнате
            message.description = f"**Название: ** {name}\n" \
                                  f"**Доступ:** {'закрытый' if is_locked else 'открытый'}\n" \
                                  f"**Лимит пользователей:** {user_limit if user_limit != 0 else 'нет'}\n" \
                                  f"**Битрейт:** {bitrate} кбит/с"

            # Перечесление пользователей с правами доступа
            if allowed_members is not None:
                allowed_members.sort(key=lambda m: m.name)

                message.add_field(
                    name="Список пользователей с доступом",
                    value="\n".join([f"**{m}** (ID: {m.id})" for m in allowed_members])
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

            if author.voice is None or author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
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
        cls=BotCommand, name="add",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def give_permissions_to_member(self, ctx, user: commands.MemberConverter):
        """
        Дать доступ пользователю заходить в комнату
        """

        author = ctx.author
        server = ctx.guild
        allowed_users = get_permissions_for_all_users(server, author)

        if user in allowed_users:
            raise CommandError("Этот участник уже имеет доступ к вашей комнате")
        else:
            add_permissions_for_user(server, author, user)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.set_permissions(user, overwrite=Permissions(connect=True))

            await ctx.send(embed=SuccessfulMessage(f"Я дал доступ `{user.display_name}` к вашей комнате"))

    @room_settings.command(
        cls=BotCommand, name="remove",
        usage={"пользователь": ("упоминание или ID участника сервера", True)}
    )
    async def remove_permissions_to_member(self, ctx, user: commands.MemberConverter):
        """
        Забрать доступ у пользователя заходить в комнату
        """

        author = ctx.author
        server = ctx.guild
        allowed_users = get_permissions_for_all_users(server, author)

        if user not in allowed_users:
            raise CommandError("Этот участник не имеет доступ к каналу")
        else:
            remove_permissions_for_user(server, author, user)

            if author.voice is not None and author.voice.channel.overwrites_for(author) == OWNER_PERMISSIONS:
                await author.voice.channel.set_permissions(user, overwrite=Permissions(connect=None))

            await ctx.send(embed=SuccessfulMessage(f"Я забрал доступ у `{user.display_name}` к вашей комнате"))

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


def setup(bot):
    bot.add_cog(Rooms(bot))
