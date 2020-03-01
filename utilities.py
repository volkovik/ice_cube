from discord import ActivityType, Status


class ConvertEnums:
    """
    Конвертация Enums из discord.py на понятный текст
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
    def status(arg: Status) -> str:
        return {
            Status.online: "Онлайн",
            Status.idle: "Неактивный",
            Status.dnd or Status.do_not_disturb: "Не беспокоить",
            Status.offline or Status.invisible: "Не в сети"
        }.get(arg, arg)
