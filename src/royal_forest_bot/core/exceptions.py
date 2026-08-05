"""Custom exceptions for the bot."""


class BotException(Exception):
    """Базовое исключение для бота."""

    def __init__(self, message: str, code: str = "BOT_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class BookingException(BotException):
    """Исключение при ошибках бронирования."""

    def __init__(self, message: str, code: str = "BOOKING_ERROR"):
        super().__init__(message, code)


class UserException(BotException):
    """Исключение при ошибках пользователя."""

    def __init__(self, message: str, code: str = "USER_ERROR"):
        super().__init__(message, code)


class BroadcastException(BotException):
    """Исключение при ошибках рассылки."""

    def __init__(self, message: str, code: str = "BROADCAST_ERROR"):
        super().__init__(message, code)


class PaymentException(BotException):
    """Исключение при ошибках оплаты."""

    def __init__(self, message: str, code: str = "PAYMENT_ERROR"):
        super().__init__(message, code)


class DatabaseException(BotException):
    """Исключение при ошибках базы данных."""

    def __init__(self, message: str, code: str = "DATABASE_ERROR"):
        super().__init__(message, code)


class ValidationException(BotException):
    """Исключение при ошибках валидации."""

    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(message, code)
