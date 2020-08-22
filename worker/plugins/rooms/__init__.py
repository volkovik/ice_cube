from .plugin import Rooms
from .settings import RoomsSettings


def setup(bot):
    bot.add_cog(Rooms(bot))
    bot.add_cog(RoomsSettings(bot))
