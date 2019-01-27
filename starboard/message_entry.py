class StarboardMessage:
    def __init__(
        self,
        original_message: int,
        original_channel: int,
        new_message: int,
        new_channel: int,
        author: int,
    ):
        self.original_message = original_message
        self.original_channel = original_channel
        self.new_message = new_message
        self.new_channel = new_channel
        self.author = author

    def to_json(self) -> dict:
        return {
            "original_message": self.original_message,
            "original_channel": self.original_channel,
            "new_message": self.new_message,
            "new_channel": self.new_channel,
            "author": self.author,
        }

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            data["original_message"],
            data["original_channel"],
            data["new_message"],
            data["new_channel"],
            data["author"],
        )
