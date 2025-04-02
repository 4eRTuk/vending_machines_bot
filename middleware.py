from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Dict, Any, Callable, Awaitable

from database import get_db_session
from models import Employee


class EmployeeMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        session = get_db_session()
        
        try:
            employee = session.query(Employee).filter(
                Employee.telegram_id == user_id
            ).first()
            
            # Добавляем информацию о сотрудникe в data
            data['employee'] = employee
            
            # Продолжаем обработку для всех пользователей
            return await handler(event, data)
        finally:
            session.close()
