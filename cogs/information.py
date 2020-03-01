import discord
from utilities import ConvertEnums
from discord.ext import commands


class Information(commands.Cog):
    def __init__(self, bot):
        self.client = bot
        self.color = 0xFFCC4D

    @commands.command(name="user")
    async def user_information(self, ctx, user: commands.MemberConverter = None):
        """
        Показывает некоторую информацию о пользователе

        :param user: упоминнание или ID пользователя
        """

        if user is None:
            user = ctx.author

        status = ConvertEnums.status(user.status)
        created_at = user.created_at.strftime("%d.%m.%Y, %H:%M:%S")
        joined_at = user.joined_at.strftime("%d.%m.%Y, %H:%M:%S")

        if type(user.activity) is discord.CustomActivity:
            activity = f"**Пользовательский статус:** {user.activity}\n"

            if len(user.activities) > 1:
                activity += f"**{ConvertEnums.activity_type(user.activities[1].type)}** {user.activities[1]}\n"
        else:
            activity = f"**{ConvertEnums.activity_type(user.activity.type)}** " \
                       f"{user.activity.name}\n" if user.activity else ""

        message = discord.Embed(
            title=f"Информация о \"{user.display_name}\"",
            description="Пустое поле.",
            color=self.color
        )
        message.add_field(
            name="Основная информация",
            value=f"**Никнейм:** {user.name}#{user.discriminator}\n"
                  f"**Статус:** {status}\n{activity}"
                  f"**Дата регистрации:** {created_at}\n"
                  f"**Дата присоеденения:** {joined_at}",
        )
        message.set_thumbnail(url=user.avatar_url_as(static_format="jpg"))
        message.set_footer(text=f"ID: {user.id}")

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Information(bot))
