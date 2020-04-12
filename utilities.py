import discord
from itertools import groupby
from discord import ActivityType, Status, VoiceRegion, VerificationLevel
from discord.ext.commands import HelpCommand


class ConvertEnums:
    """
    Конвертация Enums из discord.py на русский язык
    """

    @staticmethod
    def activity_type(arg: ActivityType):
        return {
            ActivityType.playing: "Играет",
            ActivityType.listening: "Слушает",
            ActivityType.watching: "Смотрит",
            ActivityType.streaming: "Стримит"
        }.get(arg, arg)

    @staticmethod
    def status(arg: Status):
        return {
            Status.online: "Онлайн",
            Status.idle: "Неактивный",
            Status.dnd or Status.do_not_disturb: "Не беспокоить",
            Status.offline or Status.invisible: "Не в сети"
        }.get(arg, arg)

    @staticmethod
    def voice_region(arg: VoiceRegion) -> str:
        return {
            VoiceRegion.amsterdam: ":flag_nl: Амстердам",
            VoiceRegion.brazil: ":flag_br: Бразилия",
            VoiceRegion.dubai: ":flag_ae: Дубай",
            VoiceRegion.eu_central: ":flag_eu: Центральная Европа",
            VoiceRegion.eu_west: ":flag_eu: Западная Европа",
            VoiceRegion.europe: ":flag_eu: Европа",
            VoiceRegion.frankfurt: ":flag_de: Франкфурт",
            VoiceRegion.hongkong: ":flag_hk: Гонконг",
            VoiceRegion.india: ":flag_in: Индия",
            VoiceRegion.japan: ":flag_jp: Япония",
            VoiceRegion.london: ":flag_gb: Лондон",
            VoiceRegion.russia: ":flag_ru: Россия",
            VoiceRegion.singapore: ":flag_sg: Сингапур",
            VoiceRegion.southafrica: ":flag_za: Южная Африка",
            VoiceRegion.sydney: ":flag_au: Сидней",
            VoiceRegion.us_central: ":flag_us: Центральная Америка",
            VoiceRegion.us_east: ":flag_us: Восточная Америка",
            VoiceRegion.us_south: ":flag_us: Южная Америка",
            VoiceRegion.us_west: ":flag_us: Восточная Америка",
            VoiceRegion.vip_amsterdam: ":flag_nl: Амстердам (VIP)",
            VoiceRegion.vip_us_east: ":flag_us: Восточная Америка (VIP)",
            VoiceRegion.vip_us_west: ":flag_us: Западная Америка (VIP)"
        }.get(arg, arg)

    @staticmethod
    def verification_level(arg: VerificationLevel) -> str:
        return {
            VerificationLevel.none: "Нет",
            VerificationLevel.low: "Низкая",
            VerificationLevel.medium: "Средняя",
            VerificationLevel.high or VerificationLevel.table_flip: "Высокая",
            VerificationLevel.extreme or VerificationLevel.double_table_flip: "Экстримальная"
        }.get(arg, arg)


class CustomHelpCommand(HelpCommand):
    """
    Производный класс, который формирует вид команды help
    """

    def __init__(self, **options):
        """
        Настройка команды help

        :param **options: некоторые настройки
        """

        self.width = options.pop('width', 80)  # максимальное количество символов для описания
        self.sort_commands = options.pop('sort_commands', True)  # сортировка команд и категорий по алфавиту
        self.commands_heading = options.pop('commands_heading', "Команды")  # название колонки для групп команд
        self.embed = discord.Embed()  # Embed-шаблон

        super().__init__(**options)

        self.command_attrs["hidden"] = True  # не показывать команды, которые заведомо скрыты

    def shorten_text(self, text):
        """
        Сокращение строки до определённого количества символов

        :param text: строка
        :return: обработанная строка или та же строка, если строка меньше или равна лимиту символов
        """

        if len(text) > self.width:
            return text[:self.width - 3] + '...'

        return text

    def get_destination(self):
        """
        Получение канала для отправки сообщения

        :return: текстовый канал сервера
        """

        ctx = self.context

        return ctx.channel

    async def prepare_help_command(self, ctx, command=None):
        """
        Очистка Embed-шаблона
        """

        self.embed.title = ""
        self.embed.description = ""
        self.embed.clear_fields()

    async def send_bot_help(self, mapping):
        """
        Отправка списка команд бота в текстовый канал
        """

        ctx = self.context
        prefix = ctx.prefix
        bot = ctx.bot

        # Удаленяем все команды без категории и сортируем по категориям
        commands = groupby(filter(lambda c: c.cog_name is not None, bot.commands), key=lambda c: c.cog_name + ":")

        self.embed.title = self.commands_heading

        for category, cmds in commands:
            commands_descriptions = []

            for cmd in cmds:
                # Если команда является лишь второстепенной, то вывести её вместе с родительской командой
                if cmd.parent is not None:
                    commands_descriptions.append(f"{prefix}{cmd.parent}{cmd} - {cmd.short_doc}")
                else:
                    commands_descriptions.append(f"{prefix}{cmd} - {cmd.short_doc}")

            self.embed.add_field(
                name=category,
                value="\n".join(commands_descriptions),
                inline=False
            )

        await ctx.send(embed=self.embed)

    async def command_not_found(self, name: str):
        """
        Текст ошибки, при ненахождении введённой команды

        :param name: название команды
        :return: сообщение об ошибке
        """

        return f"Я не нашёл команду `{name}`"

    async def send_error_message(self, error):
        """
        Отправка ошибок, вызванные использованием команды

        :param error: сообщение об ошибке
        """

        self.embed.title = ":x: Ошибка"
        self.embed.description = error
        self.embed.colour = 0xDD2E44

        await self.get_destination().send(embed=self.embed)
