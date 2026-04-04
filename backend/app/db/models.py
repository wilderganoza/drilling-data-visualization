from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=True)
    email = Column(String(200), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class Well(Base):
    __tablename__ = "wells"

    id = Column(Integer, primary_key=True, index=True)
    well_name = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=True)
    total_rows = Column(Integer, nullable=True)
    total_columns = Column(Integer, nullable=True)
    date_imported = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Well(id={self.id}, well_name='{self.well_name}')>"


class WellDataBase:
    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)


class ProcessedDataset(Base):
    __tablename__ = "processed_datasets"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(String(500), nullable=True)
    pipeline_config = Column(JSONB, nullable=False)
    metrics = Column(JSONB, nullable=True)
    status = Column(String(50), default="completed")
    record_count = Column(Integer, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    well = relationship("Well", backref="processed_datasets")
    creator = relationship("User", backref="processed_datasets", foreign_keys=[created_by])
    records = relationship("ProcessedRecord", back_populates="dataset", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ProcessedDataset(id={self.id}, well_id={self.well_id}, name='{self.name}')>"


class ProcessedRecord(Base):
    __tablename__ = "processed_records"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("processed_datasets.id"), nullable=False, index=True)
    source_record_id = Column(Integer, nullable=True)
    data = Column(JSONB, nullable=False)
    scaled_data = Column(JSONB, nullable=True)
    component_scores = Column(JSONB, nullable=True)
    is_outlier = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("ProcessedDataset", back_populates="records")

    def __repr__(self):
        return f"<ProcessedRecord(id={self.id}, dataset_id={self.dataset_id})>"


