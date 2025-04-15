import os
import logging
import time
import base64
from typing import Dict, List, Any, Optional
import json
import importlib.util

# Configure logging
logger = logging.getLogger(__name__)

# Check if Google Gemini API is available and import it
genai = None
try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    logger.info("Successfully imported Google Generative AI library")
except ImportError as e:
    logger.warning(f"Could not import Google Generative AI library: {str(e)}")
except Exception as e:
    logger.warning(f"Error initializing Google Generative AI: {str(e)}")

class GeminiClient:
    """
    Client for interacting with Google's Gemini LLM.
    Handles API calls, rate limiting, and error handling.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Gemini client.
        
        Args:
            api_key: Google Gemini API key (optional, can be set via env var)
        
        Raises:
            ImportError: If Google generativeai package is not installed
            ValueError: If API key is not provided and not found in environment
        """
        if genai is None:
            logger.error("Google generativeai package is not installed")
            raise ImportError(
                "Google generativeai package is not installed. "
                "Install it with 'pip install google-generativeai'"
            )
        
        # Get API key from parameter or environment variable
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        
        if not self.api_key:
            logger.error("No Gemini API key found")
            raise ValueError(
                "Gemini API key is required. Either pass it to the constructor "
                "or set GEMINI_API_KEY environment variable."
            )
        
        logger.info("Configuring Gemini API")
        
        # Configure the Gemini API
        try:
            genai.configure(api_key=self.api_key)
            
            # Set model configuration
            self.model_name = "gemini-1.5-pro"  # Updated to latest model
            logger.info(f"Using Gemini model: {self.model_name}")
            
            # Create a generation config
            gen_config = {
                "temperature": 0.2,  # Low temperature for more deterministic outputs
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
            
            # Initialize model
            self.model = genai.GenerativeModel(model_name=self.model_name, generation_config=gen_config)
            logger.info("Gemini model initialized successfully")
            
            # Rate limiting parameters
            self.requests_per_minute = 10  # Conservative limit
            self.last_request_time = 0
            
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {str(e)}")
            raise ValueError(f"Failed to initialize Gemini client: {str(e)}")
    
    def _handle_rate_limiting(self):
        """
        Implement rate limiting to avoid API throttling.
        Ensures at least 60/requests_per_minute seconds between requests.
        """
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        # Ensure we're not exceeding the rate limit
        min_interval = 60.0 / self.requests_per_minute
        
        if time_since_last_request < min_interval:
            # Sleep to respect rate limit
            sleep_time = min_interval - time_since_last_request
            logger.debug(f"Rate limiting: Sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        # Update last request time
        self.last_request_time = time.time()
    
    def generate_content(self, prompt: str, retry_count: int = 1) -> str:
        """
        Generate content using Gemini LLM.
        
        Args:
            prompt: The text prompt to send to Gemini
            retry_count: Number of retries on failure
            
        Returns:
            Generated text response
            
        Raises:
            Exception: If generation fails after all retries
        """
        # Check for quota error trigger words in error messages
        quota_errors = [
            "quota exceeded", 
            "exceeded your current quota", 
            "rate limit exceeded",
            "429"
        ]
        
        for attempt in range(retry_count + 1):
            try:
                # Apply rate limiting but with shorter times for web requests
                current_time = time.time()
                time_since_last_request = current_time - self.last_request_time
                
                # Ensure we're not exceeding the rate limit
                min_interval = 60.0 / self.requests_per_minute
                
                if time_since_last_request < min_interval:
                    # Sleep to respect rate limit, but max 5 seconds for web requests
                    sleep_time = min(min_interval - time_since_last_request, 5)
                    logger.debug(f"Rate limiting: Sleeping for {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
                
                # Update last request time
                self.last_request_time = time.time()
                
                # Call the Gemini API
                response = self.model.generate_content(prompt)
                
                # Extract and return text
                if hasattr(response, 'text'):
                    return response.text
                elif hasattr(response, 'parts'):
                    text_parts = [part.text for part in response.parts]
                    return ''.join(text_parts)
                else:
                    raise ValueError("Unexpected response format from Gemini API")
                
            except Exception as e:
                error_str = str(e).lower()
                logger.error(f"Gemini API error (attempt {attempt+1}/{retry_count+1}): {str(e)}")
                
                # Check if this is a quota error
                is_quota_error = any(err in error_str for err in quota_errors)
                
                if is_quota_error:
                    logger.warning("Quota limit reached for Gemini API")
                    return "Error: Quota limit reached for Gemini API. Please try again later or check your API key quota."
                
                if attempt < retry_count:
                    # Short backoff for web requests
                    wait_time = 1
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    # Return error message on final failure
                    error_msg = f"Failed to generate content: {str(e)}"
                    logger.error(error_msg)
                    return f"Error: {error_msg}"
    
    def extract_topics(self, text: str, granularity: int) -> Dict[str, Dict[str, Any]]:
        """
        Extract topics from text with specified granularity level.
        
        Args:
            text: Document text to extract topics from
            granularity: Integer from 0-100 indicating granularity level
                - 0: macro-topics (few, broader topics)
                - 100: micro-topics (many, specific topics)
            
        Returns:
            Dictionary of topics with their details
        """
        # Construct prompt based on granularity
        granularity_description = self._get_granularity_description(granularity)
        
        prompt = f"""
        Analyze the following document and extract the main topics at a granularity level of {granularity}/100.
        {granularity_description}
        
        DOCUMENT TEXT:
        {text[:10000]}  # Limit text to avoid token limits
        
        Extract topics and return them in the following JSON format:
        {{
            "topics": [
                {{
                    "id": "unique_id_1",
                    "name": "Topic Name 1",
                    "description": "Brief description of the topic"
                }},
                ...
            ]
        }}
        
        Only respond with the JSON. Do not include any explanations or additional text before or after the JSON.
        """
        
        # Get response from Gemini
        response_text = self.generate_content(prompt)
        
        # Extract JSON from response
        try:
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")
                
            json_str = response_text[json_start:json_end]
            
            # Parse the JSON
            response_json = json.loads(json_str)
            
            # Convert list to dictionary with IDs as keys
            topics_dict = {}
            for topic in response_json.get('topics', []):
                topic_id = topic.get('id', f"topic_{len(topics_dict)}")
                topics_dict[topic_id] = {
                    'name': topic.get('name', 'Unnamed Topic'),
                    'description': topic.get('description', '')
                }
            
            return topics_dict
        except Exception as e:
            logger.error(f"Error parsing topics JSON: {str(e)}")
            logger.debug(f"Response was: {response_text}")
            
            # Return a single error topic if parsing fails
            return {
                'error_topic': {
                    'name': 'Error Extracting Topics',
                    'description': f"Failed to extract topics from document: {str(e)}"
                }
            }
    
    def _get_granularity_description(self, granularity: int) -> str:
        """
        Get a description of the requested granularity level.
        
        Args:
            granularity: Integer from 0-100
            
        Returns:
            Text description of granularity for the prompt
        """
        if granularity < 20:
            return "Extract only the broadest, most general macro-topics (very few top-level topics)."
        elif granularity < 40:
            return "Extract general macro-topics (a small number of broad topics)."
        elif granularity < 60:
            return "Extract a balanced mix of general topics and some specific sub-topics."
        elif granularity < 80:
            return "Extract more specific sub-topics with moderate detail."
        else:
            return "Extract highly specific, detailed micro-topics (many fine-grained topics)."
    
    def enhance_topic_info(self, topic_name: str, topic_info: str) -> str:
        """
        Enhance topic information with additional context and explanations.
        
        Args:
            topic_name: Name of the topic
            topic_info: Raw information extracted for the topic
            
        Returns:
            Enhanced, well-structured information about the topic
        """
        prompt = f"""
        You are an educational content expert. You need to enhance the following information about the topic "{topic_name}".
        
        Original information:
        {topic_info}
        
        Please enhance this information by:
        1. Adding clear explanations for complex concepts
        2. Organizing the content with appropriate headings and structure
        3. Adding examples or analogies where helpful
        4. Ensuring the information is accurate and complete
        
        The enhanced content should be well-structured and easy to understand for a student studying this topic.
        Format the content using Markdown syntax with appropriate headers, lists, and emphasis.
        """
        
        enhanced_info = self.generate_content(prompt)
        return enhanced_info
        
    def generate_content_with_image(self, prompt: str, image_data: str, retry_count: int = 1) -> str:
        """
        Generate content using Gemini Vision model with both text prompt and image.
        
        Args:
            prompt: The text prompt to send to Gemini
            image_data: Base64-encoded image data
            retry_count: Number of retries on failure
            
        Returns:
            Generated text response
            
        Raises:
            Exception: If generation fails after all retries
        """
        # Check for quota error trigger words in error messages
        quota_errors = [
            "quota exceeded", 
            "exceeded your current quota", 
            "rate limit exceeded",
            "429"
        ]
        
        for attempt in range(retry_count + 1):
            try:
                # Use Gemini-1.5-Pro for vision capabilities (latest model)
                vision_model_name = "gemini-1.5-pro"
                logger.info(f"Using vision model: {vision_model_name}")
                
                vision_model = genai.GenerativeModel(
                    model_name=vision_model_name,
                    generation_config={
                        "temperature": 0.2,
                        "top_p": 0.95,
                        "top_k": 40,
                        "max_output_tokens": 4096,  # Reduced to avoid longer processing times
                    }
                )
                
                # Create multipart content (text + image)
                parts = [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_data
                        }
                    }
                ]
                
                # Apply rate limiting but with shorter times for web requests
                current_time = time.time()
                time_since_last_request = current_time - self.last_request_time
                
                # Ensure we're not exceeding the rate limit
                min_interval = 60.0 / self.requests_per_minute
                
                if time_since_last_request < min_interval:
                    # Sleep to respect rate limit, but max 5 seconds for web requests
                    sleep_time = min(min_interval - time_since_last_request, 5)
                    logger.debug(f"Rate limiting: Sleeping for {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
                
                # Update last request time
                self.last_request_time = time.time()
                
                # Generate content using the vision model
                response = vision_model.generate_content(parts)
                
                # Extract and return text
                if hasattr(response, 'text'):
                    return response.text
                elif hasattr(response, 'parts'):
                    text_parts = [part.text for part in response.parts]
                    return ''.join(text_parts)
                else:
                    raise ValueError("Unexpected response format from Gemini Vision API")
                    
            except Exception as e:
                error_str = str(e).lower()
                logger.error(f"Gemini Vision API error (attempt {attempt+1}/{retry_count+1}): {str(e)}")
                
                # Check if this is a quota error
                is_quota_error = any(err in error_str for err in quota_errors)
                
                if is_quota_error:
                    logger.warning("Quota limit reached for Gemini Vision API")
                    return "Error: Quota limit reached for Gemini API. Please try again later or check your API key quota."
                
                if attempt < retry_count:
                    # Short backoff for web requests
                    wait_time = 1
                    logger.info(f"Retrying vision API in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    # Return error message on final failure
                    error_msg = f"Failed to analyze image: {str(e)}"
                    logger.error(error_msg)
                    return f"Error analyzing image: {error_msg}"
