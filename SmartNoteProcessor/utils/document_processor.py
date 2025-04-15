import os
import logging
from typing import Dict, List, Any, Optional, Tuple
import re

# Import file type specific libraries
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except ImportError:
    pdfminer_extract_text = None

try:
    import docx
except ImportError:
    docx = None

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    Handles document processing, including text extraction from various file formats
    and topic information extraction from the document content.
    """
    
    def __init__(self, topic_extractor):
        """
        Initialize the document processor.
        
        Args:
            topic_extractor: An instance of TopicExtractor for topic extraction
        """
        self.topic_extractor = topic_extractor
    
    def extract_text(self, file_path: str, original_filename: str) -> str:
        """
        Extract text from a document file based on its format.
        
        Args:
            file_path: Path to the temporary file
            original_filename: Original name of the uploaded file
            
        Returns:
            Extracted text from the document
        
        Raises:
            ValueError: If the file format is not supported or extraction fails
        """
        file_extension = os.path.splitext(original_filename)[1].lower()
        
        # Extract text based on file extension
        if file_extension == '.txt' or file_extension == '.md':
            return self._extract_text_from_txt(file_path)
        elif file_extension == '.pdf':
            return self._extract_text_from_pdf(file_path)
        elif file_extension == '.docx':
            return self._extract_text_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
    
    def _extract_text_from_txt(self, file_path: str) -> str:
        """
        Extract text from a plain text file.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Text content of the file
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # Try different encodings if UTF-8 fails
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    return file.read()
            except Exception as e:
                logger.error(f"Error reading text file with latin-1 encoding: {str(e)}")
                raise ValueError(f"Failed to read text file: {str(e)}")
        except Exception as e:
            logger.error(f"Error reading text file: {str(e)}")
            raise ValueError(f"Failed to read text file: {str(e)}")
    
    def _extract_text_from_pdf(self, file_path: str) -> str:
        """
        Extract text from a PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text from the PDF
            
        Raises:
            ValueError: If PDF extraction libraries are not available or extraction fails
        """
        text = ""
        
        # Try PyPDF2 first
        if PyPDF2:
            try:
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    for page_num in range(len(reader.pages)):
                        page = reader.pages[page_num]
                        text += page.extract_text() + "\n\n"
                
                # If we got reasonable text, return it
                if len(text.strip()) > 100:
                    return text
            except Exception as e:
                logger.warning(f"PyPDF2 extraction failed: {str(e)}")
        
        # Fall back to pdfminer if PyPDF2 fails or gets too little text
        if pdfminer_extract_text:
            try:
                text = pdfminer_extract_text(file_path)
                return text
            except Exception as e:
                logger.error(f"pdfminer extraction failed: {str(e)}")
        
        # If both failed
        if not text.strip():
            raise ValueError("Failed to extract text from PDF. Ensure the PDF contains extractable text.")
        
        return text
    
    def _extract_text_from_docx(self, file_path: str) -> str:
        """
        Extract text from a DOCX file.
        
        Args:
            file_path: Path to the DOCX file
            
        Returns:
            Extracted text from the DOCX
            
        Raises:
            ValueError: If python-docx library is not available or extraction fails
        """
        if not docx:
            raise ValueError("python-docx library is not available. Cannot extract text from DOCX files.")
        
        try:
            doc = docx.Document(file_path)
            text = ""
            for para in doc.paragraphs:
                text += para.text + "\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting text from DOCX: {str(e)}")
            raise ValueError(f"Failed to extract text from DOCX: {str(e)}")
    
    def extract_topic_information(self, document_content: str, topic_name: str, gemini_client) -> str:
        """
        Extract information related to a specific topic from the document content.
        
        Args:
            document_content: The full text content of the document
            topic_name: The name of the topic to extract information for
            gemini_client: Instance of GeminiClient for LLM operations
            
        Returns:
            Extracted information related to the topic
        """
        try:
            # Ask Gemini to extract information for the specific topic
            prompt = f"""
            Extract all information related to the topic "{topic_name}" from the following document content.
            Focus only on relevant sentences, paragraphs, and details that directly relate to this topic.
            Organize the information in a clear and coherent manner.
            
            Document content:
            {document_content[:50000]}  # Limit to avoid token limits
            """
            
            topic_info = gemini_client.generate_content(prompt)
            
            # If no meaningful information was found
            if not topic_info or len(topic_info.strip()) < 50:
                return f"No detailed information found for the topic '{topic_name}' in the document."
            
            return topic_info
        except Exception as e:
            logger.error(f"Error extracting topic information: {str(e)}")
            return f"Error extracting information for topic '{topic_name}': {str(e)}"
