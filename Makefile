# Переменные
PYTHON = venv/bin/python3
PIP = venv/bin/pip
DOCKER_COMPOSE = docker-compose
APP_NAME = sset_parser
PTH = sset_parser/
.PHONY: install run uninstall docker_build docker_down docker_stop clean
include .env
export 
# --- ЛОКАЛЬНЫЙ ЗАПУСК ---

# Запуск бота из venv
run:
	$(PYTHON) $(PTH)main.py
# Создание venv и установка зависимостей
install:
	python3 -m venv venv
	$(PIP) install --upgrade pip
	$(PIP) install -e . -U
	mkdir -p data/sessions
	@echo "✅ Установка завершена. Используйте 'make run' для запуска."


# Полное удаление окружения и базы данных
uninstall:
	rm -rf venv
	rm -rf data/*.db
	@echo "⚠️ Окружение и база данных удалены."

# --- DOCKER ---

# Сборка и запуск контейнеров в фоне
docker_build:
	$(DOCKER_COMPOSE) up -d --build
	@echo "🚀 Контейнеры собраны и запущены."

# Остановка и удаление контейнеров, сетей и образов
docker_down:
	$(DOCKER_COMPOSE) down
	@echo "🛑 Контейнеры удалены."

# Просто остановка контейнеров (без удаления)
docker_stop:
	$(DOCKER_COMPOSE) stop
	@echo "⏸ Контейнеры остановлены."

# Очистка временных файлов Python
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "🧹 Временные файлы удалены."