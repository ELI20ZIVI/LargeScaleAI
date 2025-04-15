import os
import logging
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import tempfile
import shutil
import json
from datetime import datetime

from utils.document_processor import DocumentProcessor
from utils.gemini_client import GeminiClient
from utils.topic_extractor import TopicExtractor
from utils.format_converter import FormatConverter
from utils.image_analyzer import ImageAnalyzer
from database import db

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")

# Configure database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///smartnotes.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize database with app
db.init_app(app)

# Import models after db is initialized to avoid circular imports
from models import Document, Topic, Note, ImageAnalysis

# Initialize components
gemini_client = GeminiClient(api_key=os.environ.get("GEMINI_API_KEY", ""))
topic_extractor = TopicExtractor(gemini_client)
document_processor = DocumentProcessor(topic_extractor)
format_converter = FormatConverter()
image_analyzer = ImageAnalyzer(gemini_client)

# In-memory storage for user sessions (will gradually be replaced by DB)
# Structure: { session_id: { 'document_content': str, 'topics': {}, 'current_granularity': int } }
sessions_data = {}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'md'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # Create a unique session ID if not exists
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        sessions_data[session['session_id']] = {
            'document_content': '',
            'topics': {},
            'current_granularity': 50
        }
    
    # Get all documents from database for display
    documents = Document.query.order_by(Document.created_at.desc()).all()
    
    return render_template('index.html', documents=documents)


@app.route('/load_document/<int:document_id>')
def load_document(document_id):
    # Load a previously saved document from the database
    try:
        # Get document from database
        document = Document.query.get_or_404(document_id)
        
        # Get topics for this document
        topics = Topic.query.filter_by(document_id=document.id).all()
        
        # Create topics dictionary
        topics_dict = {}
        for topic in topics:
            topics_dict[topic.topic_id] = {
                'name': topic.name,
                'description': topic.description or ''
            }
        
        # Create session ID if not exists
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        else:
            # If switching documents, create a new session
            session['session_id'] = str(uuid.uuid4())
        
        # Setup session data
        sessions_data[session['session_id']] = {
            'document_content': document.content,
            'topics': topics_dict,
            'current_granularity': 50,  # Default granularity
            'document_id': document.id
        }
        
        # Get previously generated notes for display
        notes_data = {}
        for topic in topics:
            # Get notes for this topic
            notes = Note.query.filter_by(topic_id=topic.id).all()
            if notes:
                for note in notes:
                    if topic.topic_id not in notes_data:
                        notes_data[topic.topic_id] = {
                            'name': topic.name,
                            'content': note.content,
                            'format': note.format
                        }
        
        # Store notes in session if available
        if notes_data:
            sessions_data[session['session_id']]['generated_notes'] = notes_data
        
        flash('Document loaded successfully!', 'success')
        return redirect(url_for('results'))
    except Exception as e:
        logger.error(f"Error loading document: {str(e)}")
        flash(f'Error loading document: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        session_id = session.get('session_id')
        
        # Create a unique folder for this session's uploads
        upload_folder = os.path.join(tempfile.gettempdir(), f"smart_notes_{session_id}")
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        # Make a subfolder for images if it doesn't exist
        images_folder = os.path.join(upload_folder, "images")
        if not os.path.exists(images_folder):
            os.makedirs(images_folder)
        
        # Save the file
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        try:
            # Process document
            document_content = document_processor.extract_text(file_path, file.filename)
            
            # Extract images if it's a PDF file
            if filename.lower().endswith('.pdf'):
                try:
                    # Import PDF specific libraries here
                    from pdfminer.high_level import extract_text as pdf_extract
                    from pdfminer.layout import LAParams
                    import fitz  # PyMuPDF
                    
                    # Extract images from PDF using PyMuPDF
                    pdf_document = fitz.open(file_path)
                    
                    # Iterate through pages and extract images
                    image_count = 0
                    for page_num in range(len(pdf_document)):
                        page = pdf_document[page_num]
                        image_list = page.get_images(full=True)
                        
                        for img_index, img in enumerate(image_list):
                            xref = img[0]
                            base_image = pdf_document.extract_image(xref)
                            image_bytes = base_image["image"]
                            
                            # Determine file extension based on image type
                            image_ext = base_image["ext"]
                            image_filename = f"page{page_num+1}_img{img_index+1}.{image_ext}"
                            
                            with open(os.path.join(images_folder, image_filename), "wb") as img_file:
                                img_file.write(image_bytes)
                                image_count += 1
                    
                    logger.info(f"Extracted {image_count} images from the PDF")
                    
                except ImportError as ie:
                    logger.warning(f"PDF image extraction skipped: {str(ie)}")
                except Exception as pdf_err:
                    logger.error(f"Error extracting images from PDF: {str(pdf_err)}")
            
            # Ensure session ID exists in sessions_data dictionary
            if session_id not in sessions_data:
                sessions_data[session_id] = {
                    'document_content': '',
                    'topics': {},
                    'current_granularity': 50
                }
            
            # Store in session data for temporary use
            sessions_data[session_id]['document_content'] = document_content
            sessions_data[session_id]['upload_folder'] = upload_folder
            
            # Extract topics with default granularity
            granularity = 50  # Default granularity
            topics_dict = topic_extractor.extract_topics(document_content, granularity)
            sessions_data[session_id]['topics'] = topics_dict
            sessions_data[session_id]['current_granularity'] = granularity
            
            # Store document in database
            title = filename.rsplit('.', 1)[0]  # Use filename without extension as title
            file_type = filename.rsplit('.', 1)[1].lower()
            
            # Create new Document record
            document = Document(
                title=title,
                content=document_content,
                filename=filename,
                file_type=file_type
            )
            
            # Add and commit to get the document ID
            db.session.add(document)
            db.session.commit()
            
            # Store document ID in session for future reference
            sessions_data[session_id]['document_id'] = document.id
            
            # Create Topic records for each extracted topic
            for topic_id, topic_data in topics_dict.items():
                topic = Topic(
                    topic_id=topic_id,
                    name=topic_data['name'],
                    description=topic_data.get('description', ''),
                    document_id=document.id
                )
                db.session.add(topic)
            
            # Commit all topic records
            db.session.commit()
            
            flash('Document uploaded and processed successfully!', 'success')
            return redirect(url_for('results'))
        
        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            flash(f'Error processing document: {str(e)}', 'danger')
            # Clean up temp folder on error
            try:
                shutil.rmtree(upload_folder)
            except:
                pass
            return redirect(url_for('index'))
    else:
        flash(f'Invalid file type. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/results')
def results():
    session_id = session.get('session_id')
    if not session_id or session_id not in sessions_data:
        flash('No active session found. Please upload a document.', 'warning')
        return redirect(url_for('index'))
    
    session_data = sessions_data[session_id]
    if not session_data.get('document_content'):
        flash('No document content found. Please upload a document.', 'warning')
        return redirect(url_for('index'))
    
    return render_template(
        'results.html',
        topics=session_data.get('topics', {}),
        granularity=session_data.get('current_granularity', 50)
    )

@app.route('/update_granularity', methods=['POST'])
def update_granularity():
    try:
        session_id = session.get('session_id')
        granularity = int(request.form.get('granularity', 50))
        
        if session_id and session_id in sessions_data:
            document_content = sessions_data[session_id]['document_content']
            document_id = sessions_data[session_id].get('document_id')
            
            # Re-extract topics with new granularity
            topics_dict = topic_extractor.extract_topics(document_content, granularity)
            sessions_data[session_id]['topics'] = topics_dict
            sessions_data[session_id]['current_granularity'] = granularity
            
            # If this is a document from the database, update its topics
            if document_id:
                # First, get existing topics to update or remove
                existing_topics = Topic.query.filter_by(document_id=document_id).all()
                existing_topic_ids = {topic.topic_id: topic for topic in existing_topics}
                
                # Add new topics and update existing ones
                for topic_id, topic_data in topics_dict.items():
                    if topic_id in existing_topic_ids:
                        # Update existing topic
                        existing_topic = existing_topic_ids[topic_id]
                        existing_topic.name = topic_data['name']
                        existing_topic.description = topic_data.get('description', '')
                    else:
                        # Create new topic
                        new_topic = Topic(
                            topic_id=topic_id,
                            name=topic_data['name'],
                            description=topic_data.get('description', ''),
                            document_id=document_id
                        )
                        db.session.add(new_topic)
                
                # Remove topics that no longer exist
                for old_topic_id, old_topic in existing_topic_ids.items():
                    if old_topic_id not in topics_dict:
                        db.session.delete(old_topic)
                
                # Commit changes
                db.session.commit()
            
            return redirect(url_for('results'))
        else:
            flash('No active session found. Please upload a document.', 'warning')
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error updating granularity: {str(e)}")
        flash(f'Error updating granularity: {str(e)}', 'danger')
        return redirect(url_for('results'))

@app.route('/generate_notes', methods=['POST'])
def generate_notes():
    try:
        session_id = session.get('session_id')
        output_format = request.form.get('format', 'markdown')
        process_images = request.form.get('process_images', 'false') == 'true'
        
        if session_id and session_id in sessions_data:
            session_data = sessions_data[session_id]
            topics_dict = session_data.get('topics', {})
            document_content = session_data.get('document_content', '')
            document_id = session_data.get('document_id')
            
            if not topics_dict:
                flash('No topics found. Please adjust granularity and try again.', 'warning')
                return redirect(url_for('results'))
            
            # Get database topics for this document
            db_topics = Topic.query.filter_by(document_id=document_id).all()
            # Create a mapping of topic_id to database topic object
            topic_map = {topic.topic_id: topic for topic in db_topics}
            
            # Get previously generated notes
            previously_generated = {}
            if 'generated_notes' in session_data:
                previously_generated = session_data['generated_notes']
            
            # Process only a single topic at a time to avoid timeout issues
            # Choose the first topic that hasn't been processed yet
            topic_to_process = None
            for topic_id, topic_data in topics_dict.items():
                if topic_id not in previously_generated:
                    topic_to_process = (topic_id, topic_data)
                    break
            
            # If all topics have been processed, inform the user
            if not topic_to_process:
                flash('All topics have been processed. You can download the notes now.', 'info')
                return render_template(
                    'results.html', 
                    topics=topics_dict,
                    granularity=session_data.get('current_granularity', 50),
                    notes=previously_generated,
                    selected_format=output_format
                )
            
            topic_id, topic_data = topic_to_process
            logger.info(f"Processing topic: {topic_data['name']}")
            
            # Check if a note for this topic already exists in the database
            existing_db_note = None
            if topic_id in topic_map:
                existing_db_note = Note.query.filter_by(
                    topic_id=topic_map[topic_id].id,
                    format=output_format
                ).first()
                
                if existing_db_note:
                    logger.info(f"Using existing note from database for topic: {topic_data['name']}")
                    # Use existing note
                    previously_generated[topic_id] = {
                        'name': topic_data['name'],
                        'content': existing_db_note.content,
                        'format': output_format
                    }
                    
                    # Update session data
                    session_data['generated_notes'] = previously_generated
                    sessions_data[session_id] = session_data
                    
                    flash(f'Retrieved existing note for "{topic_data["name"]}". Processing more topics...', 'info')
                    return render_template(
                        'results.html', 
                        topics=topics_dict,
                        granularity=session_data.get('current_granularity', 50),
                        notes=previously_generated,
                        selected_format=output_format
                    )
            
            # Extract information for the topic
            logger.info(f"Extracting information for topic: {topic_data['name']}")
            topic_info = document_processor.extract_topic_information(
                document_content, 
                topic_data['name'],
                gemini_client
            )
            
            # Check for quota errors
            if isinstance(topic_info, str) and topic_info.startswith("Error: Quota limit reached"):
                logger.warning("API quota limit reached during topic extraction")
                flash('API quota limit reached. Please try again later or use a different API key.', 'warning')
                return redirect(url_for('results'))
            
            # Enhance information with LLM
            logger.info(f"Enhancing information for topic: {topic_data['name']}")
            enhanced_info = gemini_client.enhance_topic_info(
                topic_data['name'],
                topic_info
            )
            
            # Check for quota errors
            if isinstance(enhanced_info, str) and enhanced_info.startswith("Error: Quota limit reached"):
                logger.warning("API quota limit reached during information enhancement")
                flash('API quota limit reached. Please try again later or use a different API key.', 'warning')
                return redirect(url_for('results'))
            
            # Process images if requested and available (limited to 1 image at a time)
            image_content = ""
            if process_images and 'upload_folder' in session_data:
                try:
                    upload_folder = session_data.get('upload_folder')
                    images_folder = os.path.join(upload_folder, 'images')
                    if upload_folder and os.path.exists(images_folder):
                        logger.info(f"Looking for images related to topic: {topic_data['name']}")
                        
                        # Get image files
                        image_files = []
                        if os.path.exists(images_folder):
                            image_files = [f for f in os.listdir(images_folder) 
                                        if os.path.isfile(os.path.join(images_folder, f)) 
                                        and f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                        
                        # Process just one image to avoid timeouts
                        if image_files:
                            # Look for existing image analyses in the database
                            existing_analyses = {}
                            if topic_id in topic_map:
                                db_analyses = ImageAnalysis.query.filter_by(
                                    topic_id=topic_map[topic_id].id
                                ).all()
                                existing_analyses = {a.filename: a.analysis_result for a in db_analyses}
                            
                            # Find first unprocessed image
                            for img_file in image_files:
                                if img_file not in existing_analyses:
                                    logger.info(f"Processing image: {img_file}")
                                    
                                    # Process just this single image
                                    single_topic = {topic_id: topic_data}
                                    single_image_path = os.path.join(images_folder, img_file)
                                    
                                    # Create temporary folder with just this image
                                    temp_image_folder = os.path.join(upload_folder, 'temp_image')
                                    os.makedirs(temp_image_folder, exist_ok=True)
                                    temp_image_path = os.path.join(temp_image_folder, img_file)
                                    shutil.copy(single_image_path, temp_image_path)
                                    
                                    # Process the image
                                    topic_images = image_analyzer.analyze_images_for_topics(
                                        temp_image_folder, 
                                        single_topic
                                    )
                                    
                                    # Cleanup temp folder
                                    shutil.rmtree(temp_image_folder, ignore_errors=True)
                                    
                                    # If analysis successful, add to content
                                    if (topic_images and topic_id in topic_images and 
                                        topic_images[topic_id] and img_file in topic_images[topic_id]):
                                        
                                        description = topic_images[topic_id][img_file]
                                        
                                        # Check for quota errors
                                        if isinstance(description, str) and description.startswith("Error: Quota limit reached"):
                                            logger.warning("API quota limit reached during image analysis")
                                            flash('API quota limit reached during image analysis. Image processing skipped.', 'warning')
                                            break
                                        
                                        # Add to content
                                        if not image_content:
                                            image_content = "\n\n## Related Visual Content\n\n"
                                        image_content += f"### Figure: {img_file}\n\n{description}\n\n"
                                        
                                        # Store in database
                                        if topic_id in topic_map:
                                            img_analysis = ImageAnalysis(
                                                filename=img_file,
                                                path=single_image_path,
                                                topic_id=topic_map[topic_id].id,
                                                analysis_result=description
                                            )
                                            db.session.add(img_analysis)
                                            
                                    # Process only one image at a time
                                    break
                                else:
                                    # Use existing analysis
                                    logger.info(f"Using existing analysis for image: {img_file}")
                                    description = existing_analyses[img_file]
                                    if description and not description.startswith('Error:'):
                                        if not image_content:
                                            image_content = "\n\n## Related Visual Content\n\n"
                                        image_content += f"### Figure: {img_file}\n\n{description}\n\n"
                                    
                                    # Include only one image at a time to avoid large responses
                                    break
                
                except Exception as img_err:
                    logger.error(f"Error processing images: {str(img_err)}")
                    # Continue without image processing
            
            # Combine content
            combined_content = enhanced_info
            if image_content:
                combined_content += image_content
            
            # Convert to specified format
            formatted_content = format_converter.convert(
                topic_data['name'],
                combined_content,
                output_format
            )
            
            # Create note record
            new_note = {
                'name': topic_data['name'],
                'content': formatted_content,
                'format': output_format
            }
            
            # Save note to database
            if topic_id in topic_map:
                # Check if a note with this format already exists
                existing_note = Note.query.filter_by(
                    topic_id=topic_map[topic_id].id,
                    format=output_format
                ).first()
                
                if existing_note:
                    # Update existing note
                    existing_note.content = formatted_content
                    existing_note.updated_at = datetime.utcnow()
                else:
                    # Create new note
                    note = Note(
                        content=formatted_content,
                        format=output_format,
                        topic_id=topic_map[topic_id].id
                    )
                    db.session.add(note)
            
            # Commit database changes for this topic
            db.session.commit()
            
            # Add to generated notes
            previously_generated[topic_id] = new_note
            
            # Update session data
            session_data['generated_notes'] = previously_generated
            session_data['selected_format'] = output_format
            sessions_data[session_id] = session_data
            
            # Use hyperlinks for all processed notes
            notes_with_links = format_converter.add_hyperlinks(
                previously_generated, 
                topics_dict,
                output_format
            )
            
            # Update hyperlinks in database
            for linked_topic_id, linked_note_data in notes_with_links.items():
                if linked_topic_id in topic_map:
                    db_note = Note.query.filter_by(
                        topic_id=topic_map[linked_topic_id].id,
                        format=output_format
                    ).first()
                    
                    if db_note:
                        db_note.content = linked_note_data['content']
            
            # Final commit for hyperlinks
            db.session.commit()
            
            # Update session with hyperlinked notes
            session_data['generated_notes'] = notes_with_links
            sessions_data[session_id] = session_data
            
            # Check if we have processed all topics
            remaining = len(topics_dict) - len(previously_generated)
            if remaining > 0:
                flash(f'Generated note for "{topic_data["name"]}". {remaining} topics remaining. Click "Generate Notes" to continue.', 'info')
            else:
                flash('All notes generated successfully!', 'success')
            
            return render_template(
                'results.html', 
                topics=topics_dict,
                granularity=session_data.get('current_granularity', 50),
                notes=notes_with_links,
                selected_format=output_format
            )
        else:
            flash('No active session found. Please upload a document.', 'warning')
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error generating notes: {str(e)}")
        flash(f'Error generating notes: {str(e)}', 'danger')
        return redirect(url_for('results'))

@app.route('/download/<topic_id>', methods=['GET'])
def download_topic(topic_id):
    session_id = session.get('session_id')
    if not session_id or session_id not in sessions_data:
        flash('No active session found. Please upload a document.', 'warning')
        return redirect(url_for('index'))
    
    session_data = sessions_data[session_id]
    generated_notes = session_data.get('generated_notes', {})
    
    if topic_id not in generated_notes:
        flash('Topic not found', 'danger')
        return redirect(url_for('results'))
    
    topic_data = generated_notes[topic_id]
    format_extension = {
        'markdown': '.md',
        'html': '.html',
        'latex': '.tex'
    }.get(topic_data['format'], '.txt')
    
    filename = f"{topic_data['name'].replace(' ', '_')}{format_extension}"
    content = topic_data['content']
    
    # Create response with file
    from flask import Response
    response = Response(
        content,
        mimetype={
            'markdown': 'text/markdown',
            'html': 'text/html',
            'latex': 'application/x-latex'
        }.get(topic_data['format'], 'text/plain')
    )
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response

@app.route('/download_all', methods=['GET'])
def download_all():
    session_id = session.get('session_id')
    if not session_id or session_id not in sessions_data:
        flash('No active session found. Please upload a document.', 'warning')
        return redirect(url_for('index'))
    
    session_data = sessions_data[session_id]
    generated_notes = session_data.get('generated_notes', {})
    
    if not generated_notes:
        flash('No notes generated yet', 'danger')
        return redirect(url_for('results'))
    
    # Create a zip file with all notes
    import io
    import zipfile
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        for topic_id, topic_data in generated_notes.items():
            format_extension = {
                'markdown': '.md',
                'html': '.html',
                'latex': '.tex'
            }.get(topic_data['format'], '.txt')
            
            filename = f"{topic_data['name'].replace(' ', '_')}{format_extension}"
            zf.writestr(filename, topic_data['content'])
    
    memory_file.seek(0)
    
    from flask import send_file
    return send_file(
        memory_file, 
        mimetype='application/zip',
        as_attachment=True,
        download_name='smart_notes.zip'
    )

@app.route('/view/<topic_id>', methods=['GET'])
def view_topic(topic_id):
    session_id = session.get('session_id')
    if not session_id or session_id not in sessions_data:
        flash('No active session found. Please upload a document.', 'warning')
        return redirect(url_for('index'))
    
    session_data = sessions_data[session_id]
    generated_notes = session_data.get('generated_notes', {})
    
    if topic_id not in generated_notes:
        flash('Topic not found', 'danger')
        return redirect(url_for('results'))
    
    topic_data = generated_notes[topic_id]
    
    return render_template(
        'results.html',
        topics=session_data.get('topics', {}),
        granularity=session_data.get('current_granularity', 50),
        notes=generated_notes,
        selected_format=topic_data['format'],
        viewing_topic=topic_data
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
