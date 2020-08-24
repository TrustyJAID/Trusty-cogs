class CleverbotError(Exception):
    pass


class NoCredentials(CleverbotError):
    pass


class InvalidCredentials(CleverbotError):
    pass


class APIError(CleverbotError):
    pass


class OutOfRequests(CleverbotError):
    pass
