

class GabUser:

    def __init__(self, user_id:int, created_at_month_label:str, name:str, username:str, follower_count:int,
                 following_count:int, post_count:int, picture_url:str, picture_url_full:str,
                 following:bool, followed:bool, verified:bool, is_pro:bool, is_donor:bool,
                 is_investor:bool, is_premium:bool, is_tippable:bool, is_private:bool,
                 is_accessible:bool, follow_pending:bool, bio:str, cover_url:str, score:int,
                 video_count:int, is_favorited:bool, subscribing:bool, is_muted:bool, distribution:list):

        self.user_id = user_id
        self.created_at_month_label = created_at_month_label
        self.name = name
        self.username = username
        self.follower_count = follower_count
        self.following_count = following_count
        self.post_count = post_count
        self.picture_url = picture_url
        self.picture_url_full = picture_url_full
        self.following = following
        self.followed = followed
        self.verified = verified
        self.is_pro = is_pro
        self.is_donor = is_donor
        self.is_investor = is_investor
        self.is_premium = is_premium
        self.is_tippable = is_tippable
        self.is_private = is_private
        self.is_accessible = is_accessible
        self.follow_pending = follow_pending
        self.bio = bio
        self.cover_url = cover_url
        self.score = score
        self.video_count = video_count
        self.is_favorited = is_favorited
        self.subscribing = subscribing
        self.is_muted = is_muted
        self.distribution = distribution

    @classmethod
    def from_json(cls, data:dict):
        return cls(data["id"],
                   data["created_at_month_label"],
                   data["name"],
                   data["username"],
                   data["follower_count"],
                   data["following_count"],
                   data["post_count"],
                   data["picture_url"],
                   data["picture_url_full"],
                   data["following"],
                   data["followed"],
                   data["verified"],
                   data["is_pro"],
                   data["is_donor"],
                   data["is_investor"],
                   data["is_premium"],
                   data["is_tippable"],
                   data["is_private"],
                   data["is_accessible"],
                   data["follow_pending"],
                   data["bio"],
                   data["cover_url"],
                   data["score"],
                   data["video_count"],
                   data["is_favorited"],
                   data["subscribing"],
                   data["is_muted"],
                   data["distribution"])