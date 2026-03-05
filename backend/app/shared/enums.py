from enum import Enum

class CurrencyEnum(str, Enum):
    USD = "USD"
    EGP = "EGP"
    EUR = "EUR"

class PaymentMethodEnum(str, Enum):
    CARD = "card"
    WALLET = "wallet"
    BANK_TRANSFER = "bank_transfer"

class PaymentGatewayEnum(str, Enum):
    STRIPE = "stripe"
    PAYMOB = "paymob"
    PAYPAL = "paypal"

class PaymentStatusEnum(str, Enum):
    PAID = "paid"
    PENDING = "pending"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

class SubscriptionStatusEnum(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    PAST_DUE = "past_due"
    TRIALING = "trialing"
    UNPAID = "unpaid"

class languageEnum(str, Enum):
    ENGLISH = "en"
    ARABIC = "ar"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    PORTUGUESE = "pt"
    ITALIAN = "it"
    RUSSIAN = "ru"
    CHINESE = "zh"
    JAPANESE = "ja"
    KOREAN = "ko"
    AUTO = None  # Auto-detect

    
class modelSize(str, Enum):
    """Available Whisper model sizes."""
    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large-v3"



class AudioVideoExtension(str, Enum):
    MP3  = ".mp3"
    MP4  = ".mp4"
    WAV  = ".wav"
    M4A  = ".m4a"
    FLAC = ".flac"
    OGG  = ".ogg"
    WMA  = ".wma"
    AAC  = ".aac"
    MOV  = ".mov"
    MKV  = ".mkv"
    WEBM = ".webm"
    
    @classmethod
    def has_value(cls, value: str) -> bool:
        return value in cls._value2member_map_