class Destiny2APIError(Exception):
    pass


class ServersUnavailable(Destiny2APIError):
    pass


class Destiny2InvalidParameters(Destiny2APIError):
    pass


class Destiny2APICooldown(Destiny2APIError):
    pass


class Destiny2RefreshTokenError(Destiny2APIError):
    pass


class Destiny2MissingAPITokens(Destiny2APIError):
    pass


class Destiny2MissingManifest(Destiny2APIError):
    pass
