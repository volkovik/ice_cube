import enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, Integer, Boolean, Enum


Base = declarative_base()


class PermissionsForRoom(enum.Enum):
    banned = False
    default = None
    allowed = True


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    bio = Column(String(512))


class Server(Base):
    __tablename__ = "servers"

    server_id = Column(Integer, primary_key=True)
    prefix = Column(String(32), nullable=True)


class ServerSettingsOfRooms(Base):
    __tablename__ = "servers_settings_of_rooms"

    server_id = Column(Integer, primary_key=True)
    channel_id_creates_rooms = Column(Integer, unique=True)


class UserSettingsOfRoom(Base):
    __tablename__ = "users_settings_of_room"

    server_id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, primary_key=True)
    name = Column(String(32), nullable=True, default=None)
    user_limit = Column(Integer, default=0, nullable=False)
    bitrate = Column(Integer, default=64, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)


class UserPermissionsOfRoom(Base):
    __tablename__ = "users_permissions_of_room"

    server_id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, primary_key=True)
    permissions = Column(Enum(PermissionsForRoom), default=PermissionsForRoom.default, nullable=False)
