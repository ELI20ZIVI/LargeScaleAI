from datetime import datetime
import uuid
import json
from database import db

class Document(db.Model):
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    topics = db.relationship('Topic', backref='document', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Document {self.title}>'


class Topic(db.Model):
    __tablename__ = 'topics'
    
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.String(100), nullable=False)  # Unique ID for the topic from Gemini
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    notes = db.relationship('Note', backref='topic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Topic {self.name}>'


class Note(db.Model):
    __tablename__ = 'notes'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    format = db.Column(db.String(50), nullable=False)  # markdown, latex, html
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Note for {self.topic.name} in {self.format} format>'


class ImageAnalysis(db.Model):
    __tablename__ = 'image_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(255), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=False)
    analysis_result = db.Column(db.Text, nullable=False)  # JSON string of analysis result
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    topic = db.relationship('Topic', backref='image_analyses')
    
    def __repr__(self):
        return f'<ImageAnalysis for {self.filename}>'
    
    def get_analysis_data(self):
        """Convert stored JSON string to Python dictionary"""
        try:
            return json.loads(self.analysis_result)
        except:
            return {}