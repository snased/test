# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем системные зависимости для pygame и X11
RUN apt-get update && apt-get install -y \
    python3-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev \
    libavformat-dev \
    libavcodec-dev \
    libfreetype6-dev \
    x11-apps \
    x11-xserver-utils \
    xauth \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:0

# Создаём рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY main.py gui.py logic.py ./

# Устанавливаем права на выполнение
RUN chmod +x gui.py

# Точка входа - запускаем игру
CMD ["python", "gui.py"]

