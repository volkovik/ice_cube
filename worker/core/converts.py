from discord import ActivityType, Status, VoiceRegion, VerificationLevel


def convert_activity_type(arg: ActivityType):
    return {
        ActivityType.playing: "Играет",
        ActivityType.listening: "Слушает",
        ActivityType.watching: "Смотрит",
        ActivityType.streaming: "Стримит"
    }.get(arg, arg)


def convert_status(arg: Status):
    return {
        Status.online: "Онлайн",
        Status.idle: "Неактивный",
        Status.dnd or Status.do_not_disturb: "Не беспокоить",
        Status.offline or Status.invisible: "Не в сети"
    }.get(arg, arg)


def convert_voice_region(arg: VoiceRegion):
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


def convert_verification_level(arg: VerificationLevel):
    return {
        VerificationLevel.none: "Нет",
        VerificationLevel.low: "Низкая",
        VerificationLevel.medium: "Средняя",
        VerificationLevel.high or VerificationLevel.table_flip: "Высокая",
        VerificationLevel.extreme or VerificationLevel.double_table_flip: "Экстримальная"
    }.get(arg, arg)
