from abc import ABC

from redbot.core import Config
from redbot.core.bot import Red


class MixinMeta(ABC):
    """
    Base class for well behaved type hint detection with composite class.

    Basically, to keep developers sane when not all attributes are defined in each mixin.

    This is modified from
    https://github.com/Cog-Creators/Red-DiscordBot/blob/V3/develop/redbot/cogs/mod/abc.py
    """

    def __init__(self, *_args):
        self.bot: Red
        self.config: Config
