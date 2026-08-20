from uuid import NAMESPACE_URL, UUID, uuid5


def normalize_domestic_stock_code(stock_code: str) -> str:
    normalized = stock_code.strip()
    if len(normalized) != 6 or not normalized.isascii() or not normalized.isdecimal():
        raise ValueError("stock_code must be a six-digit domestic stock code")
    return normalized


def subscription_id(user_id: UUID, stock_code: str) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        f"kis-auto-trading:signal-subscription:{user_id}:{stock_code}",
    )
