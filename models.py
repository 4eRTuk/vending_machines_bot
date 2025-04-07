from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


Base = declarative_base()


class Employee(Base):
    __tablename__ = 'employees'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    group = Column(String(20), nullable=False)  # engineer, accountant, manager


class Machine(Base):
    __tablename__ = 'machines'
    
    id = Column(Integer, primary_key=True)
    number = Column(String(20), unique=True, nullable=False)
    name = Column(String(100))
    model = Column(String(50))
    address = Column(String(200), nullable=False)
    responsible = Column(String(100))
    priority = Column(Integer)
    pump = Column(Boolean)
    saturday = Column(Boolean)
    sunday = Column(Boolean)
    ip = Column(String(15))
    engineer = Column(Integer)


class Photo(Base):
    __tablename__ = 'photos'

    id = Column(Integer, primary_key=True)
    file_id = Column(String, nullable=False)
    request_id = Column(Integer, ForeignKey('requests.id'), nullable=False)

    request = relationship("Request", back_populates="photos")


class Comment(Base):
    __tablename__ = 'comments'

    id = Column(Integer, primary_key=True)
    text = Column(String, nullable=False)
    request_id = Column(Integer, ForeignKey('requests.id'), nullable=False)
    added_by = Column(String, nullable=False)  # 'engineer' или 'accountant'
    created_at = Column(DateTime, default=datetime.utcnow)

    request = relationship("Request", back_populates="comments")


class Request(Base):
    __tablename__ = 'requests'
    
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False)
    full_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    machine_number = Column(String(20), ForeignKey('machines.number'), nullable=False)
    issue_description = Column(String)
    payment_method = Column(String)  # наличные, безналичные
    payment_type = Column(String)  # карта, qr код
    expense_amount = Column(Float)
    item_name = Column(String)
    expense_time = Column(String)
    comments = relationship("Comment", back_populates="request")
    photo = Column(String)  # Это фото из заявки от клиента
    photos = relationship("Photo", back_populates="request")  # Это фото от инженера
    engineer_id = Column(Integer, ForeignKey('employees.id'), nullable=True)  # Инженер, взявший заявку в работу
    engineer_status = Column(String(20), default='open')  # open, in_work, closed
    engineer_closed_at = Column(DateTime, nullable=True)  # Время закрытия инженером
    engineer_closed_by = Column(String, nullable=True)  # Имя инженера
    accountant_id = Column(Integer, ForeignKey('employees.id'), nullable=True)  # Диспетчер, взявший заявку в работу
    accountant_status = Column(String(20), default='open')  # open, in_work, closed
    accountant_closed_at = Column(DateTime, nullable=True)  # Время закрытия диспетчером
    accountant_closed_by = Column(String, nullable=True)  # Имя диспетчера
    # Связи
    assigned_engineer = relationship("Employee", foreign_keys=[engineer_id])  # Инженер
    assigned_accountant = relationship("Employee", foreign_keys=[accountant_id])  # Диспетчер

    machine = relationship("Machine", back_populates="requests")

Machine.requests = relationship("Request", order_by=Request.id, back_populates="machine")

