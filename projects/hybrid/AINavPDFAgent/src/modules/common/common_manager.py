from datetime import timedelta, datetime


class CommonManager:
    def __init__(self):
        pass

    @staticmethod
    def plural_form(number: int, forms: tuple[str, str, str]) -> str:
        # Вспомогательная функция для склонений
        number = abs(number) % 100
        if 11 <= number <= 19:
            return forms[2]
        i = number % 10
        if i == 1:
            return forms[0]
        if 2 <= i <= 4:
            return forms[1]
        return forms[2]

    def get_estimated_time_str(self, count: int, avg_per_link: int = 40) -> str:
        """
        Рассчитывает примерное время выполнения и возвращает строку в формате:
        'Примерное время выполнения: 13 часов 18 минут 30 секунд (до 14:30:15)'
        с правильными склонениями.

        :param count: количество ссылок
        :param avg_per_link: среднее время (в секундах) на обработку одной ссылки
        """

        total_seconds = count * avg_per_link
        finish_time = datetime.now() + timedelta(seconds=total_seconds)

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if hours:
            parts.append(f"{hours} {self.plural_form(hours, ('час', 'часа', 'часов'))}")
        if minutes:
            parts.append(f"{minutes} {self.plural_form(minutes, ('минута', 'минуты', 'минут'))}")
        if seconds or not parts:
            parts.append(f"{seconds} {self.plural_form(seconds, ('секунда', 'секунды', 'секунд'))}")

        duration_str = " ".join(parts)
        return f"Примерное время выполнения: {duration_str} (до {finish_time.strftime('%H:%M:%S')})"
