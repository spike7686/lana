from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Kline15m(Base):
    __tablename__ = "kline_15m"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    open_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    quote_volume: Mapped[Optional[float]] = mapped_column(Numeric(28, 12))
    trades: Mapped[Optional[int]] = mapped_column(Integer)


class Kline1h(Base):
    __tablename__ = "kline_1h"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    open_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(28, 12), nullable=False)
    quote_volume: Mapped[Optional[float]] = mapped_column(Numeric(28, 12))
    trades: Mapped[Optional[int]] = mapped_column(Integer)


class OI15m(Base):
    __tablename__ = "oi_15m"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    ts: Mapped[DateTime] = mapped_column(DateTime(timezone=True), primary_key=True)
    sum_open_interest: Mapped[Optional[float]] = mapped_column(Numeric(28, 12))
    sum_open_interest_value: Mapped[Optional[float]] = mapped_column(Numeric(28, 12))


class OI1h(Base):
    __tablename__ = "oi_1h"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    ts: Mapped[DateTime] = mapped_column(DateTime(timezone=True), primary_key=True)
    sum_open_interest: Mapped[Optional[float]] = mapped_column(Numeric(28, 12))
    sum_open_interest_value: Mapped[Optional[float]] = mapped_column(Numeric(28, 12))
