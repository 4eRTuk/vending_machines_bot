from datetime import datetime
from sqlalchemy import create_engine, MetaData, Table, and_
from sqlalchemy.orm import sessionmaker, joinedload

from models import Base, Request, Machine, Employee, Photo, Comment

import pandas as pd
import time


# Настройка подключения к SQLite
engine = create_engine('sqlite:///vending.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def get_db_session():
    return Session()


def machine_exists(machine_number: str) -> bool:
    with Session() as session:
        return session.query(Machine).filter(
            Machine.number == machine_number
        ).first() is not None


def save_to_db(user_data: dict):
    with Session() as session:
        try:
            # Создаем новую заявку
            new_request = Request(
                created_at=datetime.now(),
                full_name=user_data['full_name'],
                phone=user_data['phone'],
                machine_number=user_data['machine'],
                photo=user_data.get('photo')
            )
            
            # Добавляем связь с автоматом
            machine = session.query(Machine).filter(
                Machine.number == user_data['machine']
            ).first()
            
            if machine:
                new_request.machine = machine
                
            session.add(new_request)
            session.flush()  # Это нужно, чтобы получить id до коммита
            request_id = new_request.id
            session.commit()
            return request_id
        except Exception as e:
            session.rollback()
            print(f"Database error: {e}")
            return None


def get_request_by_id(request_id: int):
    with Session() as session:
        request = session.query(Request).options(joinedload(Request.machine)).get(request_id)
        # Если нужно использовать объект вне сессии, можно сделать его отдельную копию
        session.expunge(request)
        return request


def update_request(request_id: int, **kwargs):
    with Session() as session:
        try:
            request = session.query(Request).get(request_id)
            for key, value in kwargs.items():
                setattr(request, key, value)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Update error: {e}")
            return False


def get_employees_by_groups(groups: list):
    with Session() as session:
        return session.query(Employee).filter(
            Employee.group.in_(groups)
        ).all()


def get_active_request(employee):
    with Session() as session:
        if employee.group == 'engineer':
            return session.query(Request).filter(
                and_(
                    Request.engineer_id == employee.id,
                    Request.engineer_status == 'in_work'
                )
            ).first()
        if employee.group == 'accountant':
            return session.query(Request).filter(
                and_(
                    Request.accountant_id == employee.id,
                    Request.accountant_status == 'in_work'
                )
            ).first()
        else:
            return None


def add_photo(request_id, photo_id):
    new_photo = Photo(file_id=photo_id, request_id=request_id)
    session = get_db_session()
    session.add(new_photo)
    session.commit()
    session.close()


def add_comment(request_id, text, role):
    new_comment = Comment(text=text, request_id=request_id, added_by=role)
    session = get_db_session()
    session.add(new_comment)
    session.commit()
    session.close()


def get_photos(request_id):
    with Session() as session:
        return session.query(Photo).filter(Photo.request_id == request_id).order_by(Photo.id).all()


def get_comments(request_id):
    with Session() as session:
        return session.query(Comment).filter(Comment.request_id == request_id).order_by(Comment.id).all()


def localize_tz_column(df, name):
    df[name] = pd.to_datetime(df[name])  # Преобразуем в формат datetime
    df[name] = df[name].dt.tz_localize('UTC')  # Указываем исходный часовой пояс (например, UTC)
    df[name] = df[name].dt.tz_convert('Europe/Moscow')  # Сдвигаем в нужный часовой пояс
    df[name] = df[name].dt.tz_localize(None)  # Убираем информацию о часовом поясе для совместимости с Excel


def export_to_excel():
    with Session() as session:
        # Загружаем метаданные и выбираем таблицу
        metadata = MetaData()
        metadata.reflect(bind=engine)
        table = metadata.tables['requests']  # Замените на имя вашей таблицы

        # Указываем конкретные столбцы для выборки
        columns_to_select = [table.c.id, table.c.created_at, table.c.full_name, table.c.phone, table.c.machine_number, table.c.engineer_closed_by, table.c.engineer_status, table.c.engineer_closed_at, table.c.accountant_closed_by, table.c.accountant_status, table.c.accountant_closed_at]
        
        # Выполняем запрос на выбор данных
        query = session.query(*columns_to_select)
        result = query.all()

        df = pd.DataFrame(result, columns=['Номер заявки', 'Создана', 'Имя клиента', 'Телефон', 'Номер автомата', 'Инженер', 'Статус от инженера', 'Когда закрыто инженером', 'Диспетчер', 'Статус от диспетчера', 'Когда закрыто диспетчером'])
        
        localize_tz_column(df, 'Создана')
        localize_tz_column(df, 'Когда закрыто инженером')
        localize_tz_column(df, 'Когда закрыто диспетчером')

        # Экспортируем данные в Excel
        random_file_name = f"{int(time.time())}.xlsx"
        df.to_excel(random_file_name, index=False)
        return random_file_name
