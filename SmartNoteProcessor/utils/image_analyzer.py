import os
import logging
import base64
from typing import Dict, List, Any, Optional, Tuple
from io import BytesIO
from PIL import Image

# Set up logging
logger = logging.getLogger(__name__)

class ImageAnalyzer:
    """
    Analyzes images using Google's Gemini Vision model to extract relevant information
    related to specific topics.
    """
    
    def __init__(self, gemini_client):
        """
        Initialize the image analyzer.
        
        Args:
            gemini_client: An instance of GeminiClient for LLM operations
        """
        self.gemini_client = gemini_client
    
    def extract_info_from_image(self, image_path: str, topics: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract information from an image that's relevant to the specified topics.
        
        Args:
            image_path: Path to the image file
            topics: Dictionary of topics extracted from the document
            
        Returns:
            Dictionary mapping topic IDs to extracted information from the image
        """
        try:
            # Encode image for Gemini Vision model
            encoded_image = self._encode_image(image_path)
            if not encoded_image:
                return {}
                
            # Prepare list of topic names for the prompt
            topic_names = [topic_data['name'] for topic_id, topic_data in topics.items()]
            topic_names_str = ", ".join([f'"{name}"' for name in topic_names])
            
            # Create prompt for Gemini Vision
            prompt = f"""
            Analyze this image and determine if it contains information relevant to any of the following topics:
            {topic_names_str}
            
            For each relevant topic, extract and summarize the visual information from the image that relates to that topic.
            If the image contains diagrams, charts, or other visual elements, describe how they relate to the topics.
            If the image is not relevant to any of the topics, respond with "No relevant information found".
            
            Format your response as a JSON object like this:
            {{
                "topic_name_1": "Description of how the image relates to this topic...",
                "topic_name_2": "Description of how the image relates to this topic...",
                ...
            }}
            
            Only include topics that are actually relevant to the image content.
            """
            
            # Call Gemini Vision API with image and prompt
            vision_response = self.gemini_client.generate_content_with_image(prompt, encoded_image)
            
            # Parse response to extract topic-relevant information
            info_by_topic = self._parse_vision_response(vision_response, topics)
            
            return info_by_topic
            
        except Exception as e:
            logger.error(f"Error analyzing image: {str(e)}")
            return {}
    
    def _encode_image(self, image_path: str) -> Optional[str]:
        """
        Encode an image to base64 for the Gemini Vision API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Base64 encoded image or None if encoding fails
        """
        try:
            # Open and resize image if needed
            with Image.open(image_path) as img:
                # Resize large images to reduce API costs
                max_size = 1024
                if max(img.width, img.height) > max_size:
                    if img.width > img.height:
                        new_width = max_size
                        new_height = int(img.height * (max_size / img.width))
                    else:
                        new_height = max_size
                        new_width = int(img.width * (max_size / img.height))
                    img = img.resize((new_width, new_height))
                
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save to BytesIO and encode
                buffer = BytesIO()
                img.save(buffer, format="JPEG")
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
                
        except Exception as e:
            logger.error(f"Error encoding image: {str(e)}")
            return None
    
    def _parse_vision_response(self, response: str, topics: Dict[str, Any]) -> Dict[str, str]:
        """
        Parse the response from Gemini Vision API to extract topic-relevant information.
        
        Args:
            response: Response text from Gemini Vision API
            topics: Dictionary of topics extracted from the document
            
        Returns:
            Dictionary mapping topic IDs to extracted information
        """
        info_by_topic = {}
        
        try:
            # Try to find a JSON object in the response
            import json
            import re
            
            # Find JSON-like structure in the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed_data = json.loads(json_str)
                
                # Match topic names to topic IDs
                name_to_id = {topic_data['name']: topic_id for topic_id, topic_data in topics.items()}
                
                # Map information to topic IDs
                for topic_name, info in parsed_data.items():
                    if topic_name in name_to_id:
                        info_by_topic[name_to_id[topic_name]] = info
            
        except Exception as e:
            logger.error(f"Error parsing vision response: {str(e)}")
        
        return info_by_topic
    
    def analyze_images_for_topics(self, images_folder: str, topics: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """
        Analyze multiple images in a folder and extract information relevant to topics.
        
        Args:
            images_folder: Path to folder containing images
            topics: Dictionary of topics extracted from the document
            
        Returns:
            Dictionary mapping topic IDs to dictionaries of image information
            {
                'topic_id_1': {
                    'image1.jpg': 'Information about topic from image1',
                    'image2.jpg': 'Information about topic from image2',
                },
                'topic_id_2': {
                    'image1.jpg': 'Information about topic from image1',
                }
            }
        """
        image_info_by_topic = {topic_id: {} for topic_id in topics}
        
        try:
            # Get list of image files
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}
            image_files = [
                f for f in os.listdir(images_folder) 
                if os.path.isfile(os.path.join(images_folder, f)) and 
                os.path.splitext(f)[1].lower() in image_extensions
            ]
            
            # Process each image
            for image_file in image_files:
                image_path = os.path.join(images_folder, image_file)
                
                # Extract information from image
                info_by_topic = self.extract_info_from_image(image_path, topics)
                
                # Add information to result
                for topic_id, info in info_by_topic.items():
                    if info:  # Only add non-empty information
                        image_info_by_topic[topic_id][image_file] = info
            
            return image_info_by_topic
            
        except Exception as e:
            logger.error(f"Error analyzing images in folder: {str(e)}")
            return image_info_by_topic