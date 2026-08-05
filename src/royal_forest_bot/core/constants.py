"""Constants for conversation states and other fixed values."""

# States для ConversationHandler бронирования
CHOOSE_PROGRAM = 0
CHOOSE_DATE = 1
CHOOSE_TIME = 2
GET_PEOPLE = 3
GET_NAME = 4
GET_PHONE = 5

# Дополнительные состояния
GET_BOOKING_ID_TO_CANCEL = 7
GET_BOOKING_ID_TO_PAYMENT = 8
CHOOSE_PAYMENT_METHOD = 9

# States для ConversationHandler рассылки
BROADCAST_MENU = 0
BROADCAST_TYPE = 1
BROADCAST_MESSAGE = 2
BROADCAST_CONFIRM = 3

# Статусы бронирования
BOOKING_STATUS_PENDING = "pending"
BOOKING_STATUS_CONFIRMED = "confirmed"
BOOKING_STATUS_CANCELLED = "cancelled"
BOOKING_STATUS_COMPLETED = "completed"

# Статусы оплаты
PAYMENT_STATUS_UNPAID = "unpaid"
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_REFUNDED = "refunded"

# Типы программ
PROGRAM_MC_CHOCOLATE = "mc_chocolate"
PROGRAM_MC_CANDY = "mc_candy"
PROGRAM_TEA_RENT = "tea_rent"
PROGRAM_TEA_CEREMONY = "tea_ceremony"
PROGRAM_TEA_CACAO = "tea_cacao"
PROGRAM_TEA_SELF_CHOCOLATE = "tea_self_chocolate"
PROGRAM_TEA_SELF_CANDY = "tea_self_candy"

# Максимальные значения
MAX_PEOPLE_COUNT = 20
MAX_DATE_DAYS_AHEAD = 60

# Сообщения
WELCOME_MESSAGE = """
🌳 Добро пожаловать в Royal Forest! 🌳

Здесь вы можете забронировать:
🍫 Мастер-классы по шоколаду и конфетам
🍵 Чайную зону для церемоний и встреч

Выберите раздел в меню ниже 👇
"""

CONTACTS_MESSAGE = """
📞 Наши контакты:

📍 Адрес: г. Москва, ул. Лесная, д. 5
📱 Телефон: +7 (999) 123-45-67
🌐 Сайт: www.royalforest.ru
⏰ Режим работы: 10:00 - 22:00
"""
