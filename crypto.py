import requests
import logging
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, CallbackContext
from settings import TELEGRAM_TOKEN, CHAT_ID
from datetime import datetime, timezone

# Настроим логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаем объект бота
bot = Bot(token=TELEGRAM_TOKEN)


def is_token_recent(pair_created_at, max_minutes=5):
    """
    Проверяет, является ли токен новым (создан менее max_minutes назад)
    """
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    time_diff = current_time - pair_created_at
    minutes_old = time_diff / (1000 * 60)
    return minutes_old <= max_minutes


def get_token_info(token_address):
    # Предыдущий код остается без изменений
    solscan_url = f"https://public-api.solscan.io/token/meta?tokenAddress={token_address}"
    try:
        response = requests.get(solscan_url)
        if response.status_code == 200:
            token_data = response.json()

            total_supply = float(token_data.get('supply', 0))
            circulating_supply = float(token_data.get('circulatingSupply', 0))
            burned_tokens = total_supply - circulating_supply
            burn_percentage = (burned_tokens / total_supply * 100) if total_supply > 0 else 0

            return {
                "total_supply": total_supply,
                "circulating_supply": circulating_supply,
                "burned_tokens": burned_tokens,
                "burn_percentage": burn_percentage
            }
    except Exception as e:
        logger.error(f"Ошибка при получении данных о токене: {e}")
    return None


def get_tokens_from_api():
    # Предыдущий код остается без изменений
    url = "https://api.dexscreener.com/token-profiles/latest/v1"
    logger.info(f"Отправляем запрос к API для получения токенов: {url}")
    response = requests.get(url)
    if response.status_code != 200:
        logger.error(f"Ошибка при получении токенов: {response.status_code}")
        return []
    tokens = response.json()
    logger.info(f"Получены токены: {tokens}")
    return tokens


def check_token_pair(token_address):
    # Признаки скама
    scam_indicators = []

    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    logger.info(f"Отправляем запрос к API для проверки пары: {url}")

    response = requests.get(url)
    if response.status_code != 200:
        logger.error(f"Ошибка при проверке пары: {response.status_code}")
        return None

    data = response.json()
    if not data.get("pairs"):
        return None

    pair = data["pairs"][0]

    # Проверяем возраст пары
    pair_created_at = pair.get("pairCreatedAt", 0)
    if not is_token_recent(pair_created_at):
        return None  # Пропускаем токены старше 5 минут

    # Остальной код функции check_token_pair остается без изменений...
    token_info = get_token_info(token_address)

    if token_info:
        burn_percentage = token_info["burn_percentage"]
        if burn_percentage > 90:
            scam_indicators.append(f"⚠️ Экстремально высокий процент сожженных токенов: {burn_percentage:.2f}%")
        elif burn_percentage == 0:
            scam_indicators.append("ℹ️ Нет сожженных токенов")

    # Базовые данные
    base_token = pair["baseToken"]
    price_usd = float(pair.get("priceUsd", 0))
    formatted_price = f"{price_usd:.6f}"
    liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0))
    token_url = pair.get("url", "Не найдено")

    # Анализ транзакций
    txns_24h = pair.get("txns", {}).get("h24", {})
    buys_24h = txns_24h.get("buys", 0)
    sells_24h = txns_24h.get("sells", 0)

    # Анализ объемов
    volume_24h = float(pair.get("volume", {}).get("h24", 0))

    # Анализ изменения цены
    price_change_24h = float(pair.get("priceChange", {}).get("h24", 0))
    price_change_1h = float(pair.get("priceChange", {}).get("h1", 0))

    # Точный расчет возраста пары
    current_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    time_diff = current_time - pair_created_at

    # Расчет минут
    total_minutes = time_diff / (1000 * 60)
    minutes = int(total_minutes)

    time_str = f"{minutes} минут"
    scam_indicators.append(f"🆕 Новая пара! Возраст: {minutes} минут")

    price_change_5m = round(float(pair.get("priceChange", {}).get("m5", 0)), 2)
    price_change_1h = round(float(pair.get("priceChange", {}).get("h1", 0)), 2)
    price_change_6h = round(float(pair.get("priceChange", {}).get("h6", 0)), 2)
    price_change_24h = round(float(pair.get("priceChange", {}).get("h24", 0)), 2)

    # Формируем сообщение
    message = (
        f"🔍 Анализ НОВОГО токена: {base_token['name']} ({base_token['symbol']})\n"
        f"📍 Адрес: {token_address}\n"
        f"💲 Цена: {formatted_price} USD\n"
        f"💧 Ликвидность: ${liquidity_usd:,.2f}\n"
    )

    # Добавляем информацию о токенах, если она доступна
    if token_info:
        message += (
            f"📊 Информация о токенах:\n"
            f"   • Всего выпущено: {token_info['total_supply']:,.0f}\n"
            f"   • В обращении: {token_info['circulating_supply']:,.0f}\n"
            f"   • Сожжено: {token_info['burned_tokens']:,.0f}\n"
            f"   • Процент сожжённых: {token_info['burn_percentage']:.2f}%\n"
        )

    # Добавляем остальную информацию
    message += (
        f"📈 Изменение цены:\n"
        f"   • 5м: {price_change_5m:>7.2f}%\n"
        f"   • 1ч: {price_change_1h:>7.2f}%\n"
        f"   • 6ч: {price_change_6h:>7.2f}%\n"
        f"   • 24ч: {price_change_24h:>7.2f}%\n"
        f"⏱ Возраст пары: {time_str}\n"
        f"🔄 Транзакции 24ч: {buys_24h} покупок / {sells_24h} продаж\n"
        f"🔗 Dexscreener: {token_url}\n"
    )

    if scam_indicators:
        message += "\n⚠️ ПРЕДУПРЕЖДЕНИЯ:\n" + "\n".join(scam_indicators)

    return message


async def monitor_pairs(update: Update, context: CallbackContext):
    await update.message.reply_text("🔍 Начинаю поиск новых токенов (младше 5 минут)...")

    # Получаем список токенов с API
    tokens = get_tokens_from_api()

    # Фильтруем токены Solana
    solana_tokens = [token for token in tokens if token.get("chainId") == "solana"]
    logger.info(f"Токены Solana: {solana_tokens}")

    if not solana_tokens:
        await update.message.reply_text("Токены Solana не найдены.")
        return

    found_new_tokens = False
    # Для каждого токена Solana выполняем проверку
    for token in solana_tokens:
        token_address = token.get("tokenAddress")
        if token_address:
            result = check_token_pair(token_address)
            if result:
                found_new_tokens = True
                # Отправляем сообщение в Telegram
                await bot.send_message(chat_id=CHAT_ID, text=result)

    if not found_new_tokens:
        await update.message.reply_text("❌ Новых токенов младше 5 минут не найдено.")
    else:
        await update.message.reply_text("✅ Мониторинг завершен.")


# Запуск бота
def main():
    # Создаем приложение
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики команд
    app.add_handler(CommandHandler("monitor", monitor_pairs))

    print("Бот запущен. Ожидание команд...")
    app.run_polling()


if __name__ == "__main__":
    main()