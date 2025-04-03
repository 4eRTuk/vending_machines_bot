from aiogram import F, Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ContentType, CallbackQuery, Message, ReplyKeyboardMarkup, InlineKeyboardMarkup, FSInputFile
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from datetime import datetime
from sqlalchemy import or_
from typing import Any, Dict

from config import Config
from database import save_to_db, get_request_by_id, update_request, get_employees_by_groups, machine_exists, add_photo, add_comment, get_photos, get_comments, get_db_session, get_active_request, export_to_excel
from middleware import EmployeeMiddleware
from models import Request, Employee

import asyncio
import os
import pytz
import re


bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()


# States для клиента
class ClientStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_phone = State()
    waiting_for_machine = State()
    waiting_for_photo = State()
    confirmation = State()


# Обработчик команды /start для клиентов
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext, **kwargs):
    await state.clear()
    employee = kwargs.get('employee')
    text = kwargs.get('text')
    if employee:
        request = get_active_request(employee)
        if request:
            await show_work_menu(message, employee.group == 'engineer', text=f"Работа с заявкой №{request.id}:")
        else:
            await show_main_menu(message, employee.group == 'manager', text)
    else:
        await show_client_menu(message, text)


# Клавиатура с кнопкой "Создать заявку"
async def show_client_menu(message: types.Message, text: str = None):
    text = (
        "Вас приветствует система обратной связи по работе автоматов и аппаратов.\n"
        "Пожалуйста, заранее найдите номер автомата/аппарата рядом с купюроприемником."
    ) if not text else text
    menu = ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Создать заявку")]
        ],
        resize_keyboard=True
    )
    await message.answer(text, reply_markup=menu)


# Обработчик кнопки "Создать заявку"
@dp.message(lambda message: message.text == "Создать заявку")
async def start_application(message: types.Message, state: FSMContext):
    await message.answer("Введите номер автомата/аппарата:\n\nЧетырехзначный номер на прямоугольной шильде.\nПример: 0078", reply_markup=cancel_keyboard())
    await state.set_state(ClientStates.waiting_for_machine)


# Клавиатура с кнопкой "Отменить заявку"
def cancel_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Отменить заявку"))
    return builder.as_markup(resize_keyboard=True)


# Обработчик отмены на любом этапе
@dp.message(lambda message: message.text == "Отменить заявку")
async def cancel_application(message: types.Message, state: FSMContext, **kwargs):
    employee = kwargs.get('employee')
    await start_command(message, state, text="Заявка отменена", employee=employee)


# Обработчик ввода номера автомата
@dp.message(ClientStates.waiting_for_machine)
async def process_machine_number(message: types.Message, state: FSMContext):
    machine_number = message.text.strip()
    
    if not machine_exists(machine_number):
        await message.answer(
            f"🚨 Автомат/аппарат с номером {machine_number} не найден.\n"
            "Проверьте номер — он находится над купюроприемником — "
            "и введите еще раз:",
            reply_markup=cancel_keyboard()
        )
        return
    
    await state.update_data(machine=machine_number)
    await message.answer("Приложите фотографию неисправности:", reply_markup=skip_keyboard())
    await state.set_state(ClientStates.waiting_for_photo)


# Клавиатура с кнопкой "Пропустить"
def skip_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Пропустить"))
    return builder.as_markup(resize_keyboard=True)


# Обработчик пропуска на этапе фото
@dp.message(lambda message: message.text == "Пропустить")
async def skip_photo(message: types.Message, state: FSMContext):
    await message.answer("Введите Ваше имя:", reply_markup=cancel_keyboard())
    await state.set_state(ClientStates.waiting_for_full_name)


@dp.message(ClientStates.waiting_for_photo)
async def process_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id if message.photo else None
    await state.update_data(photo=photo_id)
    
    await message.answer("Введите Ваше имя:", reply_markup=cancel_keyboard())
    await state.set_state(ClientStates.waiting_for_full_name)


# Обработчик ввода ФИО
@dp.message(ClientStates.waiting_for_full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await message.answer("Введите Ваш номер телефона:\n\nНачинайте с 8 или +7, пожалуйста.", reply_markup=cancel_keyboard())
    await state.set_state(ClientStates.waiting_for_phone)


def validate_phone_number(phone_number):
    # Регулярное выражение для проверки номера
    pattern = r"^\+7\d{10}$|^8\d{10}$"
    # Убираем лишние символы (пробелы, дефисы, скобки)
    cleaned_number = re.sub(r"[^\d+]", "", phone_number)
    # Проверяем соответствие шаблону
    return bool(re.match(pattern, cleaned_number))


# Обработчик ввода телефона
@dp.message(ClientStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    
    if not validate_phone_number(phone):
        await message.answer(
            "Проверьте введенный номер — у телефонного номера неверный формат.",
            reply_markup=cancel_keyboard()
        )
        return
    
    user_data = await state.update_data(phone=phone)
    
    # Создаем клавиатуру подтверждения
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(
        text="Подтвердить заявку",
        callback_data="confirm_application")
    )
    builder.add(types.InlineKeyboardButton(
        text="Отменить заявку",
        callback_data="cancel_application")
    )
    
    confirmation_text = (
        "Подтвердите корректность данных:\n\n"
        f"Ваше имя: {user_data['full_name']}\n"
        f"Ваш телефон: {user_data['phone']}\n"
        f"Номер автомата/аппарата: {user_data['machine']}"
    )
    
    await message.answer(confirmation_text, reply_markup=builder.as_markup())
    await state.set_state(ClientStates.confirmation)


# Обработчик подтверждения заявки
@dp.callback_query(lambda c: c.data == "confirm_application", ClientStates.confirmation)
async def confirm_application(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    user_data = await state.get_data()
    employee = kwargs.get('employee')
    
    # Сохраняем данные в БД
    request_id = save_to_db(user_data)
    if request_id:
        await callback.message.edit_reply_markup(reply_markup=None)
        await start_command(callback.message, state, text="Благодарим за заявку! Служба заботы в ближайшее время даст обратную связь по указанному номеру телефона.", employee=employee)
        request = get_request_by_id(request_id)
        employees = get_employees_by_groups(['engineer', 'accountant', 'manager'])
        await send_notification(bot, request, employees, callback.from_user.id)
    else:
        await start_command(callback.message, state, text="Ошибка при сохранении заявки. Пожалуйста, попробуйте позже или позвоните на горячую линию.", employee=employee)


# Обработчик отмены через инлайн-кнопку
@dp.callback_query(lambda c: c.data == "cancel_application", ClientStates.confirmation)
async def cancel_confirmation(callback: types.CallbackQuery, state: FSMContext, **kwargs):
    await callback.message.edit_reply_markup(reply_markup=None)
    employee = kwargs.get('employee')
    await start_command(callback.message, state, text="Заявка отменена", employee=employee)


def format_datetime(date_time):
    # Форматирование даты по русской локали
    MONTHS = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
        7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    moscow_tz = pytz.timezone("Europe/Moscow")
    target_datetime = date_time.astimezone(moscow_tz)
    month = MONTHS[target_datetime.month]
    return target_datetime.strftime('%d month %Y, %H:%M').lower().replace('month', month)


def get_base_info(request):
    created_at = format_datetime(request.created_at)
    return (
        f"Заявка №{request.id}\n\n"
        f"Дата и время: {created_at}\n"
        f"ФИО клиента: {request.full_name}\n"
        f"Номер телефона: <a href='tel:{request.phone}'>{request.phone}</a>\n"
        f"Фото: {'Прикреплено' if request.photo else 'Отсутствует'}\n"
        f"Номер автомата/аппарата: {request.machine_number}\n"
        f"Модель: {request.machine.model if request.machine else ''}\n"
        f"Адрес: {request.machine.address if request.machine else ''}\n"
        f"Наименование установки: {request.machine.name if request.machine else ''}\n"
    )


def append_info(message_text, request):
    if request.machine.priority != None:
        message_text += f"Приоритет: {request.machine.priority}\n"
    if request.machine.pump != None:
        message_text += f"Помпа: {'есть' if request.machine.pump else 'нет'}\n"
    if request.machine.saturday != None or request.machine.sunday != None:
        message_text += f"Выходные сб/вс: {'да' if request.machine.saturday else 'нет'}/{'да' if request.machine.sunday else 'нет'}\n"
    if request.machine.ip != None:
        message_text += f"ИП: {request.machine.ip}\n"
    return message_text


def append_manager_info(report_text, request, photos_count):
    comments = get_comments(request.id)
    photo_text = f"Фото от сотрудника: {photos_count} шт."
    comments_engineers = "Комментарии:\n" + "\n".join([f"{c.text}" for c in comments if c.added_by == 'engineer']) if comments else "Комментарии отсутствуют"
    comments_accountants = "Комментарии:\n" + "\n".join([f"{c.text}" for c in comments if c.added_by == 'accountant']) if comments else "Комментарии отсутствуют"
    report_text += (
        f"Инженер закрыл: {request.engineer_closed_by or 'Не закрыта'}\n"
        f"Когда закрыл инженер: {format_datetime(request.engineer_closed_at) if request.engineer_closed_at else 'Не закрыта'}\n"
        f"{comments_engineers}\n"
        f"{photo_text}\n\n"
        f"Диспетчер закрыл: {request.accountant_closed_by or 'Не закрыта'}\n"
        f"Когда закрыл диспетчер: {format_datetime(request.accountant_closed_at) if request.accountant_closed_at else 'Не закрыта'}\n"
        f"{comments_accountants}"
    )
    return report_text


async def send_notification(bot: Bot, request: Request, employees: list, user_id: int = None):
    message_text = get_base_info(request)
    message_text = append_info(message_text, request)
    
    for employee in employees:
        appendix = ""
        builder = InlineKeyboardBuilder()
        
        # Кнопки для руководства
        if employee.group == 'manager':
            builder.row(
                types.InlineKeyboardButton(
                    text="Просмотреть отчет",
                    callback_data=f"view_report:{request.id}"
                )
            )
            if user_id:
                appendix = f"\nTelegram ID пользователя: {user_id}"
        else:  # Кнопки для инженеров и диспетчеров
            button = types.InlineKeyboardButton(
                text="Взять в работу",
                callback_data=f"take_request:{request.id}"
            )
            if request.accountant_status == 'closed' and employee.group == 'accountant' or request.engineer_status == 'closed' and employee.group == 'engineer':
                button = types.InlineKeyboardButton(
                    text="Переоткрыть заявку",
                    callback_data=f"reopen:{request.id}"
                )
            builder.row(button)
        
        keyboard = builder.as_markup()
        
        try:
            if request.photo:
                await bot.send_photo(
                    chat_id=employee.telegram_id,
                    photo=request.photo,
                    caption=message_text + appendix,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            else:
                await bot.send_message(
                    chat_id=employee.telegram_id,
                    text=message_text + appendix,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
        except Exception as e:
            print(f"Error sending notification: {e}")


@dp.callback_query(lambda c: c.data.startswith("take_request:"))
async def take_request_handler(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    employee = kwargs.get('employee')
    if not employee:
        await callback.answer("Доступ запрещен!")
        return
        
    if get_active_request(employee):
        await callback.answer("У вас уже есть заявка в работе!")
        return
        
    request_id = int(callback.data.split(":")[1])
    request = get_request_by_id(request_id)
    
    data = {}
    if employee.group == 'engineer':
        # Проверки
        if request.engineer_status == 'closed':
            await callback.answer("Заявка уже закрыта!")
            return
            
        if request.engineer_status == 'in_work':
            await callback.answer("Заявка уже обрабатывается!")
            return
        
        # Назначаем заявку
        data['engineer_id'] = employee.id
        data['engineer_status'] = 'in_work'
    
    if employee.group == 'accountant':
        # Проверки
        if request.accountant_status == 'closed':
            await callback.answer("Заявка уже закрыта!")
            return
        
        if request.accountant_status == 'in_work':
            await callback.answer("Заявка уже обрабатывается!")
            return
        
        # Назначаем заявку
        data['accountant_id'] = employee.id
        data['accountant_status'] = 'in_work'
        
    if update_request(request_id, **data):
        # Обновляем меню сотрудника
        await show_work_menu(callback.message, employee.group == 'engineer', text=f"Работа с заявкой №{request.id}:")
    else:
        await callback.message.answer("Ошибка при взятии заявки в работу!")


async def show_work_menu(message: types.Message, engineer: bool = False, text: str = None):
    buttons = [
        [types.KeyboardButton(text="Добавить комментарий")]
    ]
    if engineer:
        buttons.append([types.KeyboardButton(text="Добавить фото")])
    buttons.extend([
        [types.KeyboardButton(text="Закрыть заявку")],
        [types.KeyboardButton(text="Отказаться от заявки")]
    ])
    menu = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
    await message.answer("Рабочее меню:" if not text else text, reply_markup=menu)


@dp.message(F.text == "Отказаться от заявки")
async def cancel_request_handler(message: Message, **kwargs):
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer', 'accountant']:
        await callback.answer("Доступ запрещен!")
        return
    request = get_active_request(employee)
    if not request:
        await message.answer("У вас нет активных заявок!")
        return

    # Возвращаем заявку в статус "open"
    data = {}
    if employee.group == 'engineer':
        data['engineer_id'] = None
        data['engineer_status'] = 'open'
    if employee.group == 'accountant':
        data['accountant_id'] = None
        data['accountant_status'] = 'open'
    
    if update_request(request.id, **data):
        await message.answer(
            "Вы отказались от заявки!",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        await message.answer("Ошибка при отказе от заявки!")
    await show_main_menu(message, employee.group == 'manager')


# States для сотрудников
class EmployeeStates(StatesGroup):
    waiting_for_photo = State()
    waiting_for_comment = State()


async def show_main_menu(message: types.Message, manager: bool, text: str = None):
    buttons = [
        [types.KeyboardButton(text="Открытые заявки")],
        [types.KeyboardButton(text="Закрытые заявки")]
    ]
    if manager:
        buttons.extend([
            [types.KeyboardButton(text="Скачать отчет в Excel")],
            [types.KeyboardButton(text="Создать заявку")]
        ])

    menu = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )
    await message.answer("Главное меню:" if not text else text, reply_markup=menu)


# Обработчик для списка активных заявок
@dp.message(F.text == "Скачать отчет в Excel")
async def download_report(message: Message, **kwargs):
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['manager']:
        await message.answer("Доступ запрещен!")
        return
        
    file_path = export_to_excel()
    file = FSInputFile(file_path)
    await bot.send_document(message.from_user.id, file, caption="Ваш отчет готов!")
    os.remove(file_path)
    
    # Возвращаем основное меню
    await show_main_menu(message, employee.group == 'manager')


# Обработчик для списка активных заявок
@dp.message(F.text == "Открытые заявки")
async def show_open_requests(message: Message, **kwargs):
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer', 'accountant', 'manager']:
        await message.answer("Доступ запрещен!")
        return

    session = get_db_session()
    try:
        open_requests = None
        if employee.group == 'engineer':
            open_requests = session.query(Request).filter(
                Request.engineer_status == 'open'
            ).all()
        elif employee.group == 'accountant':
            open_requests = session.query(Request).filter(
                Request.accountant_status == 'open'
            ).all()
        elif employee.group == 'manager':
            open_requests = session.query(Request).filter(
                or_(
                    Request.accountant_status != 'closed',
                    Request.engineer_status != 'closed'
                )
            ).all()
        
        if not open_requests:
            await message.answer("Нет открытых заявок")
            return
            
        for request in open_requests:
            request = get_request_by_id(request.id)
            await send_notification(bot, request, [employee])
            
    except Exception as e:
        await message.answer("Ошибка при получении заявок")
        print(f"Error: {e}")
    finally:
        session.close()


# Обработчик для списка закрытых заявок
@dp.message(F.text == "Закрытые заявки")
async def show_closed_requests(message: Message, **kwargs):
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer', 'accountant', 'manager']:
        await message.answer("Доступ запрещен!")
        return

    session = get_db_session()
    try:
        closed_requests = None
        if employee.group == 'engineer':
            closed_requests = session.query(Request).filter(
                Request.engineer_id == employee.id,
                Request.engineer_status == 'closed'
            ).all()
        elif employee.group == 'accountant':
            closed_requests = session.query(Request).filter(
                Request.accountant_id == employee.id,
                Request.accountant_status == 'closed'
            ).all()
        elif employee.group == 'manager':
            closed_requests = session.query(Request).filter(
                Request.accountant_status == 'closed',
                Request.engineer_status == 'closed'
            ).all()

        if not closed_requests:
            await message.answer("Нет закрытых заявок")
            return

        for request in closed_requests:
            await send_notification(bot, request, [employee])
    except Exception as e:
        await message.answer("Ошибка при получении заявок")
        print(f"Error: {e}")
    finally:
        session.close()


@dp.callback_query(lambda c: c.data.startswith("reopen:"))
async def reopen_request_handler(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer', 'accountant']:
        await callback.answer("Доступ запрещен!")
        return
    
    request = get_active_request(employee)
    if request:
        await callback.answer("У вас уже есть заявка в работе!")
        return
    
    request_id = callback.data.split(":")[1]
    request = get_request_by_id(request_id)
    
    data = {}
    if employee.group == 'engineer' and request.engineer_id == employee.id:
        data['engineer_status'] = 'in_work'
    elif employee.group == 'accountant' and request.accountant_id == employee.id:
        data['accountant_status'] = 'in_work'
    else:
        await callback.answer("Вы не можете переоткрыть эту заявку!")
        return
    
    if update_request(request.id, **data):
        # Возвращаем основное меню
        await show_work_menu(callback.message, employee.group == 'engineer', text=f"Заявка №{request.id} переоткрыта:")
    else:
        await callback.message.answer("Ошибка при переоткрытии заявки!")


# Функция для создания клавиатуры Готово
def get_done_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="Готово")]],
        resize_keyboard=True
    )


# Обработчик добавления фото
@dp.message(F.text == "Добавить фото")
async def add_photo_handler(message: Message, state: FSMContext, **kwargs):
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer']:
        await message.answer("Доступ запрещен!")
        return
    request = get_active_request(employee)
    if not request:
        await message.answer("У вас нет активных заявок!")
        return
    
    await state.update_data(request_id=request.id)
    await message.answer("Отправьте фото:", reply_markup=get_done_keyboard())
    await state.set_state(EmployeeStates.waiting_for_photo)


# Обработчик фото
@dp.message(EmployeeStates.waiting_for_photo, F.content_type == ContentType.PHOTO)
async def process_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    request_id = data['request_id']
    photo_id = message.photo[-1].file_id
    
    add_photo(request_id, photo_id)
    
    await message.answer("Фото успешно добавлено! Отправьте еще или нажмите 'Готово'.", reply_markup=get_done_keyboard())


@dp.message(EmployeeStates.waiting_for_photo, F.text == "Готово")
async def finish_adding_photos(message: Message, state: FSMContext, **kwargs):
    employee = kwargs.get('employee')
    if not employee:
        await callback.answer("Доступ запрещен!")
        return
        
    await message.answer("Добавление фото завершено.", reply_markup=None)
    await state.clear()
    await show_work_menu(message, employee.group == 'engineer')


# Обработчик добавления комментария
@dp.message(F.text == "Добавить комментарий")
async def add_comment_handler(message: Message, state: FSMContext, **kwargs):
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer', 'accountant']:
        await message.answer("Доступ запрещен!")
        return
    request = get_active_request(employee)
    if not request:
        await message.answer("У вас нет активных заявок!")
        return
    
    await state.update_data(request_id=request.id, role=employee.group)
    await message.answer("Введите ваш комментарий:", reply_markup=get_done_keyboard())
    await state.set_state(EmployeeStates.waiting_for_comment)


# Обработчик комментария
@dp.message(EmployeeStates.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext, **kwargs):
    employee = kwargs.get('employee')
    if not employee:
        await callback.answer("Доступ запрещен!")
        return
        
    if message.text == "Готово":
        await message.answer("Добавление комментариев завершено.", reply_markup=None)
        await state.clear()
        await show_work_menu(message, employee.group == 'engineer')
        return

    data = await state.get_data()
    request_id = data['request_id']
    role = data['role']
    
    add_comment(request_id, message.text, role)
    
    await message.answer("Комментарий успешно добавлен! Введите еще или нажмите 'Готово'.", reply_markup=get_done_keyboard())


# Функция для создания клавиатуры подтверждения
def get_confirmation_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="Подтвердить", callback_data=f"confirm_close"),
                types.InlineKeyboardButton(text="Отменить", callback_data=f"cancel_close")
            ]
        ]
    )


# Обработчик для закрытия заявки
@dp.message(F.text == "Закрыть заявку")
async def close_request_handler(message: Message, **kwargs):
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer', 'accountant']:
        await message.answer("Доступ запрещен!")
        return
    
    request = get_active_request(employee)
    if not request:
        await message.answer("У вас нет активных заявок!")
        return
        
    # Отправляем сообщение с подтверждением
    await message.answer(
        f"Подтвердите закрытие заявки №{request.id}\n\nНомер автомата/аппарата: {request.machine_number}\nАдрес: {request.machine.address}",
        reply_markup=get_confirmation_keyboard()
    )


# Обработчик для подтверждения закрытия заявки
@dp.callback_query(lambda c: c.data.startswith("confirm_close"))
async def confirm_close_handler(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    employee = kwargs.get('employee')
    if not employee or employee.group not in ['engineer', 'accountant']:
        await callback.answer("Доступ запрещен!")
        return

    request = get_active_request(employee)
    data = {}
    if employee.group == 'engineer':
        data['engineer_status'] = 'closed'
        data['engineer_closed_at'] = datetime.now()
        data['engineer_closed_by'] = employee.full_name
    if employee.group == 'accountant':
        data['accountant_status'] = 'closed'
        data['accountant_closed_at'] = datetime.now()
        data['accountant_closed_by'] = employee.full_name
        
    if update_request(request.id, **data):
        await callback.message.answer(
            "Заявка успешно закрыта!",
            reply_markup=types.ReplyKeyboardRemove()
        )
        
        # Возвращаем основное меню
        await show_main_menu(callback.message, employee.group == 'manager')
    else:
        await callback.message.answer("Ошибка при закрытии заявки!")


# Обработчик для отмены закрытия заявки
@dp.callback_query(lambda c: c.data.startswith("cancel_close"))
async def cancel_close_handler(callback: types.CallbackQuery):
    await callback.answer()

    # Убираем клавиатуру подтверждения
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Закрытие заявки отменено")


@dp.callback_query(lambda c: c.data.startswith("view_report:"))
async def view_report_handler(callback: types.CallbackQuery, **kwargs):
    await callback.answer()
    employee = kwargs.get('employee')
    if not employee or employee.group != 'manager':
        await callback.answer("Доступ запрещен!")
        return

    request_id = int(callback.data.split(":")[1])
    request = get_request_by_id(request_id)
    
    if not request:
        await callback.message.answer("Заявка не найдена")
        return

    photos = get_photos(request_id)
    report_text = get_base_info(request)
    report_text = append_info(report_text, request)
    report_text = append_manager_info(report_text, request, len(photos))

    if request.photo:
        await callback.message.answer_photo(
            photo=request.photo,
            caption=report_text,
            parse_mode='HTML'
        )
    else:
        await callback.message.answer(report_text, parse_mode='HTML')
    
    if photos:
        media = [types.InputMediaPhoto(media=photo.file_id) for photo in photos[:10]]  # Ограничим 10 фото
        await callback.message.answer_media_group(media)
    

dp.message.middleware(EmployeeMiddleware())
dp.callback_query.middleware(EmployeeMiddleware())


# Запуск бота
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


