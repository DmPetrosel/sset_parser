# Используем стабильную версию Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости для работы с БД и сетью
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install --no-cache-dir poetry

# Копируем только файлы зависимостей для кэширования слоев
COPY pyproject.toml poetry.lock* ./

# Конфигурируем Poetry: не создавать виртуальное окружение внутри контейнера
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Копируем весь код проекта
COPY . .

# Создаем папку для данных и сессий (если ее нет)
RUN mkdir -p data/sessions

# Запускаем приложение
CMD ["python", "sset_parser/main.py"]