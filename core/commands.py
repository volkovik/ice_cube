import re

from discord.ext import commands


class Command(commands.Command):
    def __init__(self, func, **kwargs):
        super(Command, self).__init__(func, **kwargs)
        self.notes = re.findall(r":note: (.+)", self.help)  # contains notes for using command
        self.examples = re.findall(r":example: (.+)", self.help)  # contains examples linked with this command
        self.arguments = {}  # contains arguments with description, requirement, and note

        args_names = dict(re.findall(r":argname (\w+): (\w+)", self.help))
        args_descriptions = dict(re.findall(r":argdesc (\w+): (.+)", self.help))
        args_required = dict(re.findall(r":argreq (\w+): (True|False)", self.help))
        args_notes = dict(re.findall(r":argnote (\w+): (.+)", self.help))

        for k, v in args_names.items():
            if k in args_descriptions:
                description = args_descriptions[k]
            else:
                description = "нет описания"

            if k in args_required:
                required = True if args_required[k] == "True" else False
            else:
                required = False

            if k in args_notes:
                note = args_notes[k]
            else:
                note = ""

            self.arguments[v] = (description, required, note)

    @property
    def signature(self):
        """
        Возвращает аргументы команды
        """

        if self.arguments:
            result = [f"<{key}>" if params[1] is True else f"[{key}]" for key, params in self.arguments.items()]

            return " ".join(result)
        else:
            return ""


class Group(commands.Group):
    def __init__(self, func, **kwargs):
        super(Group, self).__init__(func, **kwargs)
        self.notes = re.findall(r":note: (.+)", self.help)  # contains notes for using command
        self.examples = re.findall(r":example: (.+)", self.help)  # contains examples linked with this command
        self.arguments = {}  # contains arguments with description, requirement, and note

        args_names = dict(re.findall(r":argname (\w+): (\w+)", self.help))
        args_descriptions = dict(re.findall(r":argdesc (\w+): (.+)", self.help))
        args_required = dict(re.findall(r":argreq (\w+): (True|False)", self.help))
        args_notes = dict(re.findall(r":argnote (\w+): (.+)", self.help))

        for k, v in args_names.items():
            if k in args_descriptions:
                description = args_descriptions[k]
            else:
                description = "нет описания"

            if k in args_required:
                required = True if args_required[k] == "True" else False
            else:
                required = False

            if k in args_notes:
                note = args_notes[k]
            else:
                note = ""

            self.arguments[v] = (description, required, note)

    @property
    def signature(self):
        """
        Возвращает аргументы команды
        """

        if self.arguments:
            result = [f"<{key}>" if params[1] is True else f"[{key}]" for key, params in self.arguments.items()]

            return " ".join(result)
        else:
            return ""


class Cog(commands.Cog):
    def __init__(self, bot):
        self.client = bot
        self.ru_name = self.qualified_name
