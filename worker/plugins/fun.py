from random import choice
from discord.ext import commands
from discord.ext.commands import CommandError

from worker.core.commands import Cog, Command
from worker.core.templates import DefaultEmbed as Embed


class Fun(Cog, name="Развлечения"):
    @commands.command(
        cls=Command, name="8ball",
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
            raise CommandError("Вы не ввели вопрос")
        else:
            message = Embed(
                title=":8ball: 8ball",
                description="> " + question
            )
            message.add_field(
                name="Ответ",
                value=choice(answers),
                inline=False
            )

        await ctx.send(embed=message)


def setup(bot):
    bot.add_cog(Fun(bot))
