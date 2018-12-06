class TwitchFollower:

    def __init__(self, from_id:int, to_id:int, followed_at:str):
        self.from_id = from_id
        self.to_id = to_id
        self.followed_at = followed_at

    @classmethod
    def from_json(cls, data:dict):
        return cls(data["from_id"], data["to_id"], data["followed_at"])