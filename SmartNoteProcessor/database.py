from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Define base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass

# Create db instance without binding to app yet
db = SQLAlchemy(model_class=Base)