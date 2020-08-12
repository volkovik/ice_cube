from .plugin import Levels
from .settings import LevelsSettings


def setup(bot):
    bot.add_cog(Levels(bot))
    bot.add_cog(LevelsSettings(bot))
