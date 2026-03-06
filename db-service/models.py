"""SQLAlchemy declarative models."""
from sqlalchemy import Column, Integer, String, Numeric, Date, Time
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date)
    week_day = Column(String)
    hour = Column(Time)
    ticket_number = Column(String)
    waiter = Column(Integer)
    product_name = Column(String)
    quantity = Column(Integer)
    unitary_price = Column(Numeric(10, 2))
    total = Column(Numeric(10, 2))
