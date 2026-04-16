from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, BigInteger, Float, Boolean
from datetime import datetime
from sqlalchemy import DateTime, func


class Base(DeclarativeBase):
    pass


class AppConfig(Base):
    __tablename__ = "app_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # tournament settings
    tank_id: Mapped[int] = mapped_column(Integer)
    tank_name: Mapped[str] = mapped_column(String)
    games_in_tournament: Mapped[int] = mapped_column(Integer, default=100)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)

    # WoT account
    username: Mapped[str] = mapped_column(String)
    account_id: Mapped[int] = mapped_column(BigInteger)


class PlayerTankSnapshot(Base):
    __tablename__ = "player_tank_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    player_id: Mapped[int] = mapped_column(Integer)
    tank_id: Mapped[int] = mapped_column(Integer)

    battles: Mapped[int] = mapped_column(Integer, default=0)
    total_damage: Mapped[int] = mapped_column(Integer, default=0)


class PlayerTournamentResult(Base):
    __tablename__ = "player_tournament_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    player_id: Mapped[int] = mapped_column(Integer)
    tank_id: Mapped[int] = mapped_column(Integer)

    battles: Mapped[int] = mapped_column(Integer, default=0)
    total_damage: Mapped[int] = mapped_column(Integer, default=0)

    gpg: Mapped[float] = mapped_column(Float, default=0.0)
    is_finished: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
