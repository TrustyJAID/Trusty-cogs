class ConversionsError(Exception):
    """Base Error class for conversions cog."""


class CoinMarketCapError(ConversionsError):
    """Error class for coinmarketcap errors."""
