from typing import Union, Any, List

import discord

from core.database import ServerSettingsOfRooms, UserSettingsOfRoom, UserPermissionsOfRoom
from main import Session


def get_server_settings(session: Session, server: discord.Guild) -> ServerSettingsOfRooms:
    """Request to database to get server's settings"""
    return session.query(ServerSettingsOfRooms).filter_by(server_id=str(server.id)).first()


def get_user_settings(session: Session, server: discord.Guild,
                      user: Union[discord.User, discord.Member]) -> UserSettingsOfRoom:
    """Request to database to get user's settings of room"""
    return session.query(UserSettingsOfRoom).filter_by(server_id=str(server.id), owner_id=str(user.id)).first()


def add_user_settings(session: Session, server: discord.Guild, user: Union[discord.User, discord.Member],
                      **kwargs: Any) -> UserSettingsOfRoom:
    """Request to database to add user's settings of room"""
    user = UserSettingsOfRoom(server_id=str(server.id), owner_id=str(user.id), **kwargs)
    session.add(user)
    return user


def get_all_permissions(session: Session, server: discord.Guild, user: Union[discord.User, discord.Member])\
        -> List[UserPermissionsOfRoom]:
    """Request to database to get list of room's permissions of certain user"""
    return session.query(UserPermissionsOfRoom).filter_by(server_id=str(server.id), owner_id=str(user.id)).all()
