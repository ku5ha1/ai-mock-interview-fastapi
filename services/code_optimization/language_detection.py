"""
Language Detection Module

Provides fast and accurate language detection for Python and SQL code.
"""

import logging

logger = logging.getLogger(__name__)


def detect_language(code: str) -> str:
    """
    Fast language detection optimized for speed.
    Returns 'python' or 'sql'.
    """
    if not code:
        return "python"
    
    # Quick first check for obvious SQL
    if any(keyword in code.upper() for keyword in ["SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE"]):
        return "sql"
    
    # Quick first check for obvious Python
    if any(keyword in code for keyword in ["def ", "class ", "import ", "print("]):
        return "python"
    
    # If still unclear, do a simple count (faster than regex)
    sql_count = 0
    python_count = 0
    
    # Count SQL keywords
    for keyword in ["SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "JOIN", "GROUP BY", "ORDER BY", "HAVING", "UNION", "EXISTS", "IN", "BETWEEN"]:
        if keyword in code.upper():
            sql_count += 1
    
    # Count Python keywords
    for keyword in ["def ", "class ", "import ", "from ", "print(", "return ", "for ", "while ", "try:", "except:", "with ", "async def", "await "]:
        if keyword in code:
            python_count += 1
    
    # Determine language based on counts
    if sql_count > python_count:
        return "sql"
    else:
        return "python"
