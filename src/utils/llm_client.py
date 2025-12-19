"""
LLM Client utility for interacting with LiteLLM API.
Includes exponential backoff for rate limit handling.
"""
import time
import logging
from typing import Optional
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

from src.config import config

logger = logging.getLogger(__name__)


class LLMClient:
    """Client for interacting with LiteLLM API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 5,
        base_delay: float = 1.0,
    ):
        self.api_key = api_key or config.litellm.api_key
        self.base_url = base_url or config.litellm.base_url
        self.model = model or config.litellm.model
        self.max_retries = max_retries
        self.base_delay = base_delay
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=60.0,  # 60 second timeout
        )
    
    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        Send a chat completion request with exponential backoff.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (defaults to configured model)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            The assistant's response content
        """
        model = model or self.model
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                logger.debug(f"LLM call successful after {attempt + 1} attempt(s)")
                return response.choices[0].message.content
            
            except RateLimitError as e:
                # Rate limited - retry with backoff
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(
                    f"Rate limited (429). Retrying in {wait_time}s "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                last_error = e
                time.sleep(wait_time)
                
            except APIConnectionError as e:
                # Connection error - retry with backoff
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(
                    f"Connection error. Retrying in {wait_time}s "
                    f"(attempt {attempt + 1}/{self.max_retries}): {e}"
                )
                last_error = e
                time.sleep(wait_time)
                
            except APITimeoutError as e:
                # Timeout - retry with backoff
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(
                    f"Request timeout. Retrying in {wait_time}s "
                    f"(attempt {attempt + 1}/{self.max_retries})"
                )
                last_error = e
                time.sleep(wait_time)
                
            except APIError as e:
                # Other API errors
                status_code = getattr(e, 'status_code', None)
                if status_code == 429:
                    wait_time = self.base_delay * (2 ** attempt)
                    logger.warning(
                        f"Rate limited (429). Retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    last_error = e
                    time.sleep(wait_time)
                elif status_code and status_code >= 500:
                    # Server error - retry
                    wait_time = self.base_delay * (2 ** attempt)
                    logger.warning(
                        f"Server error ({status_code}). Retrying in {wait_time}s "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )
                    last_error = e
                    time.sleep(wait_time)
                else:
                    # Client error - don't retry
                    logger.error(f"API Error: {e}")
                    raise
                    
            except Exception as e:
                logger.error(f"Unexpected error: {type(e).__name__}: {e}")
                raise
        
        # All retries exhausted
        error_msg = f"Failed after {self.max_retries} retries. Last error: {last_error}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    def structured_chat(
        self,
        system_prompt: str,
        user_message: str,
        **kwargs,
    ) -> str:
        """
        Convenience method for structured chat with system and user messages.
        
        Args:
            system_prompt: The system instruction
            user_message: The user's query
            **kwargs: Additional arguments passed to chat()
            
        Returns:
            The assistant's response content
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return self.chat(messages, **kwargs)


# Global LLM client instance
llm_client = LLMClient()