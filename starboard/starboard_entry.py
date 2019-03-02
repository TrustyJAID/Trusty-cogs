class StarboardEntry:
    def __init__(
        self,
        name: str,
        channel: int,
        emoji: str,
        colour: str = "user",
        enabled: bool = True,
        selfstar: bool = False,
        blacklist_role: list = [],
        whitelist_role: list = [],
        messages: list = [],
        blacklist_channel: list = [],
        whitelist_channel: list = [],
        threshold: int = 1,
    ):

        super().__init__()
        self.name = name
        self.channel = channel
        self.emoji = emoji
        self.colour = colour
        self.enabled = enabled
        self.selfstar = selfstar
        self.blacklist_role = blacklist_role
        self.whitelist_role = whitelist_role
        self.messages = messages
        self.blacklist_channel = blacklist_channel
        self.whitelist_channel = whitelist_channel
        self.threshold = threshold

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "channel": self.channel,
            "emoji": self.emoji,
            "colour": self.colour,
            "selfstar": self.selfstar,
            "blacklist_role": self.blacklist_role,
            "whitelist_role": self.whitelist_role,
            "messages": self.messages,
            "blacklist_channel": self.blacklist_channel,
            "whitelist_channel": self.whitelist_channel,
            "threshold": self.threshold,
        }

    @classmethod
    def from_json(cls, data: dict):
        colour = "user"
        selfstar = False
        if "selfstar" in data:
            selfstar = data["selfstar"]
        if "colour" in data:
            colour = data["colour"]
        return cls(
            data["name"],
            data["channel"],
            data["emoji"],
            colour,
            data["enabled"],
            selfstar,
            data["blacklist_role"],
            data["whitelist_role"],
            data["messages"],
            data["blacklist_channel"],
            data["whitelist_channel"],
            data["threshold"],
        )
