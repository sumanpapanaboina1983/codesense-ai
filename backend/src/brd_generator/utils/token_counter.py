"""Token estimation utilities."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """
    Estimate token count using simple heuristic.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    # Simple heuristic: ~4 characters per token
    # For more accuracy, use tiktoken library
    return len(text) // 4


def estimate_tokens_for_messages(messages: list[dict]) -> int:
    """
    Estimate token count for a list of messages.

    Args:
        messages: List of message dicts with 'content' key

    Returns:
        Estimated total token count
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        # Add overhead for message structure (~4 tokens per message)
        total += estimate_tokens(content) + 4
    return total


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """
    Truncate text to fit within token limit.

    Args:
        text: Text to truncate
        max_tokens: Maximum tokens allowed

    Returns:
        Truncated text
    """
    estimated = estimate_tokens(text)
    if estimated <= max_tokens:
        return text

    # Estimate character limit
    char_limit = max_tokens * 4
    return text[:char_limit] + "\n... [truncated]"
