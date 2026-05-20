import re
from bs4 import BeautifulSoup

def clean_html(html_content: str) -> str:
    """
    Strips HTML tags from raw job description content and cleans up spacing.
    
    Args:
        html_content: The raw HTML string.
        
    Returns:
        A cleaned plain text string.
    """
    if not html_content:
        return ""
    
    # Use BeautifulSoup to parse and extract text
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Get text and replace multiple spaces/newlines with single ones
    text = soup.get_text(separator="\n")
    
    # Normalize multiple newlines to max two to preserve paragraph breaks but remove excess vertical space
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Normalize inline spaces
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text.strip()
