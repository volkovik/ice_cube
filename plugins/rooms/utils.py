from typing import Union, Any, List

from discord import Guild, Member, User

from core.database import ServerSettingsOfRooms, UserSettingsOfRoom, UserPermissionsOfRoom
from core.templates import PermissionsForRoom
from main import Session


def get_server_settings(session: Session, server: Guild) -> ServerSettingsOfRooms:
    """Request to database to get server's settings"""
    return session.query(ServerSettingsOfRooms).filter_by(server_id=str(server.id)).first()


def get_user_settings(session: Session, server: Guild,
                      user: Union[User, Member]) -> UserSettingsOfRoom:
    """Request to database to get user's settings of room"""
    return session.query(UserSettingsOfRoom).filter_by(server_id=str(server.id), owner_id=str(user.id)).first()


def add_user_settings(session: Session, server: Guild, user: Union[User, Member],
                      **kwargs: Any) -> UserSettingsOfRoom:
    """Request to database to add user's settings of room"""
    user = UserSettingsOfRoom(server_id=str(server.id), owner_id=str(user.id), **kwargs)
    session.add(user)
    return user


def get_all_permissions(session: Session, server: Guild, user: Union[User, Member])\
        -> List[UserPermissionsOfRoom]:
    """Request to database to get list of room's permissions of certain user"""
    return session.query(UserPermissionsOfRoom).filter_by(server_id=str(server.id), owner_id=str(user.id)).all()


def get_permissions(session: Session, server: Guild, owner: Union[User, Member], user: Union[User, Member])\
        -> UserPermissionsOfRoom:
    """Request to database to get room's permissions for certain user"""
    return session.query(UserPermissionsOfRoom).filter_by(
        server_id=str(server.id), owner_id=str(owner.id), user_id=str(user.id)
    ).first()


def add_permissions(session: Session, server: Guild, owner: Union[User, Member], user: Union[User, Member],
                    permission: PermissionsForRoom):
    """Request to database to add room's permissions for certain user"""
    session.add(UserPermissionsOfRoom(
        server_id=str(server.id), owner_id=str(owner.id), user_id=str(user.id), permissions=permission
    ))
