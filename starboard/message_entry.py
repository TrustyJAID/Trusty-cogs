class StarboardMessage:

    def __init__(self, original_message, new_message, count):
        super().__init__()
        self.original_message = original_message
        self.new_message = new_message
        self.count = count

    def to_json(self) -> dict:
        return {
            "original_message": self.original_message,
            "new_message": self.new_message,
            "count": self.count
        }

    @classmethod
    def from_json(cls, data: dict):
        return cls(data["original_message"], data["new_message"], data["count"])


