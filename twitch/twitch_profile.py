class TwitchProfile:

    def __init__(self, id:str, login:str, display_name:str, acc_type:str, broadcaster_type:str,
                 description:str, profile_image_url:str, offline_image_url:str, view_count:int):
        self.id = id
        self.login = login
        self.display_name = display_name
        self.acc_type = acc_type
        self.broadcaster_type = broadcaster_type
        self.description = description
        self.profile_image_url = profile_image_url
        self.offline_image_url = offline_image_url
        self.view_count = view_count

    def to_json(self, id:str, login:str, display_name:str, acc_type:str, broadcaster_type:str,
                 description:str, profile_image_url:str, offline_image_url:str, view_count:int):
        return {
            "id" : self.id,
            "login" : self.login,
            "display_name" : self.display_name,
            "acc_type" : self.acc_type,
            "broadcaster_type" : self.broadcaster_type,
            "description" : self.description,
            "profile_image_url" : self.profile_image_url,
            "offline_image_url" : offline_image_url,
            "view_count" : self.view_count
        }

    @classmethod
    def from_json(cls, data:dict):
        data = data["data"][0]
        return cls(data["id"],
                   data["login"],
                   data["display_name"],
                   data["type"],
                   data["broadcaster_type"],
                   data["description"],
                   data["profile_image_url"],
                   data["offline_image_url"],
                   data["view_count"])