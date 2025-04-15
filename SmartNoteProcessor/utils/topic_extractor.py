import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class TopicExtractor:
    """
    Extracts topics from document content with adjustable granularity.
    Uses Gemini LLM for intelligent topic extraction.
    """
    
    def __init__(self, gemini_client):
        """
        Initialize the topic extractor.
        
        Args:
            gemini_client: An instance of GeminiClient for LLM operations
        """
        self.gemini_client = gemini_client
    
    def extract_topics(self, document_content: str, granularity: int) -> Dict[str, Dict[str, Any]]:
        """
        Extract topics from document content with specified granularity.
        
        Args:
            document_content: Text content of the document
            granularity: Integer from 0-100 indicating granularity level
                - 0: macro-topics (few, broader topics)
                - 100: micro-topics (many, specific topics)
            
        Returns:
            Dictionary of topics with their details
                {
                    'topic_id': {
                        'name': 'Topic Name',
                        'description': 'Topic Description'
                    },
                    ...
                }
        """
        try:
            # Validate granularity value
            granularity = max(0, min(100, int(granularity)))
            
            # Use Gemini to extract topics
            topics = self.gemini_client.extract_topics(document_content, granularity)
            
            # Log the number of topics found
            logger.info(f"Extracted {len(topics)} topics at granularity level {granularity}")
            
            return topics
        except Exception as e:
            logger.error(f"Error in topic extraction: {str(e)}")
            # Return a single error topic in case of failure
            return {
                'error': {
                    'name': 'Error in Topic Extraction',
                    'description': f"Failed to extract topics: {str(e)}"
                }
            }
    
    def get_topic_relationships(self, topics: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Determine relationships between topics.
        
        Args:
            topics: Dictionary of topics as returned by extract_topics
            
        Returns:
            Dictionary mapping topic IDs to lists of related topic IDs
        """
        # Simple implementation based on word overlap in topic names and descriptions
        relationships = {}
        
        # Create list of topics for processing
        topic_list = [(topic_id, data) for topic_id, data in topics.items()]
        
        for i, (topic_id, topic_data) in enumerate(topic_list):
            related_topics = []
            
            # Get words from current topic (lowercase for case-insensitive comparison)
            current_words = set((topic_data['name'] + ' ' + topic_data['description']).lower().split())
            
            # Compare with all other topics
            for j, (other_id, other_data) in enumerate(topic_list):
                if i == j:  # Skip self-comparison
                    continue
                
                # Get words from other topic
                other_words = set((other_data['name'] + ' ' + other_data['description']).lower().split())
                
                # Calculate word overlap (Jaccard similarity)
                if current_words and other_words:  # Avoid division by zero
                    overlap = len(current_words.intersection(other_words)) / len(current_words.union(other_words))
                    
                    # Consider related if overlap exceeds threshold
                    if overlap > 0.1:  # Arbitrary threshold, can be adjusted
                        related_topics.append(other_id)
            
            relationships[topic_id] = related_topics
        
        return relationships
