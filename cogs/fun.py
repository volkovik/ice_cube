import discord
from random import choice
from discord.ext import commands

from core.commands import BotCommand
from core.templates import ErrorMessage


class Fun(commands.Cog, name="Развлечения"):
    def __init__(self, bot):
        self.client = bot
        self.color = 0x32a852

    @commands.command(
        cls=BotCommand, name="8ball",
        usage={"вопрос": ("закрытый вопрос (на который можно ответить да или нет)", True)}
    )
    async def eight_ball_game(self, ctx, *, question=None):
        """
        Игра "Волшебный шар"
        """

        answers = (":white_check_mark: Бесспорно", ":white_check_mark: Предрешено",
                   ":white_check_mark: Никаких сомнений", ":white_check_mark: Определённо да",
                   ":white_check_mark: Можешь быть уверен в этом", ":white_check_mark: Мне кажется — «да»",
                   ":white_check_mark: Вероятнее всего", ":white_check_mark: Хорошие перспективы",
                   ":white_check_mark: Да", ":white_check_mark: Знаки говорят — «да»",
                   ":question: Пока не ясно, попробуй снова", ":question: Спроси позже",
                   ":question: Лучше не рассказывать", ":question: Сейчас нельзя предсказать",
                   ":question: Сконцентрируйся и спроси опять", ":x: Даже не думай", ":x: Мой ответ — «нет»",
                   ":x: По моим данным — «нет»", ":x: Перспективы не очень хорошие", ":x: Весьма сомнительно")

        if question is None:
            message = ErrorMessage("Вы не ввели вопрос")
        else:
            message = discord.Embed(
                title=":8ball: 8ball",
                description="> " + question,
                color=self.color
            )
            message.add_field(
                name="Ответ",
                value=choice(answers),
                inline=False
            )

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Fun(bot))
