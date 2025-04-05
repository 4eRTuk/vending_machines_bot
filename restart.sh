#!/bin/bash

# 1. Поиск и завершение процесса "python3 bot.py"
PID=$(pgrep -f "python3 bot.py")
if [ -n "$PID" ]; then
    echo "Завершаем процесс $PID..."
    kill -9 "$PID"
else
    echo "Процесс не найден."
fi

# 2. Переход в директорию с кодом (замените путь на ваш)
cd /home/bot/vending_machines_bot || exit

# 3. Активация виртуального окружения (замените путь на ваш)
source /home/bot/vending_machines_bot/venv/bin/activate

# 4. Запуск нового процесса с перенаправлением вывода
nohup python3 bot.py > telegram-bot.log 2>&1 &
echo "Процесс запущен. PID: $!"
