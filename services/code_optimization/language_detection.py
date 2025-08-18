"""
Language Detection Module

Provides fast and accurate language detection for Python and SQL code.
"""

import logging
import re

logger = logging.getLogger(__name__)


def detect_language(code: str) -> str:
    """
    Fast language detection optimized for speed and accuracy.
    Returns 'python' or 'sql'.
    """
    if not code:
        logger.info("Empty code provided, defaulting to python")
        return "python"
    
    logger.info(f"Starting language detection for code of length: {len(code)}")
    
    # Clean the code - remove comments and strings to avoid false positives
    cleaned_code = _clean_code_for_detection(code)
    logger.info(f"Cleaned code length: {len(cleaned_code)}")
    
    # Check for obvious SQL patterns first
    if _is_definitely_sql(cleaned_code):
        logger.info("Code identified as definitely SQL")
        return "sql"
    
    # Check for obvious Python patterns
    if _is_definitely_python(cleaned_code):
        logger.info("Code identified as definitely Python")
        return "python"
    
    # If still unclear, do a weighted analysis
    logger.info("Language not obvious, performing weighted analysis")
    result = _weighted_language_detection(cleaned_code)
    logger.info(f"Weighted analysis result: {result}")
    return result


def _clean_code_for_detection(code: str) -> str:
    """
    Clean code by removing comments and strings to avoid false positives.
    """
    # Remove single-line comments
    code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
    
    # Remove multi-line comments (SQL style)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # Remove string literals (both single and double quotes)
    code = re.sub(r'["\'][^"\']*["\']', '', code)
    
    # Remove docstrings
    code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
    code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)
    
    return code.strip()


def _is_definitely_sql(code: str) -> bool:
    """
    Check if code is definitely SQL based on strong indicators.
    """
    # Strong SQL indicators that are unlikely to appear in Python
    strong_sql_patterns = [
        r'\bSELECT\b',
        r'\bFROM\b',
        r'\bWHERE\b',
        r'\bINSERT\s+INTO\b',
        r'\bUPDATE\s+\w+\s+SET\b',
        r'\bDELETE\s+FROM\b',
        r'\bCREATE\s+TABLE\b',
        r'\bALTER\s+TABLE\b',
        r'\bDROP\s+TABLE\b',
        r'\bJOIN\b',
        r'\bGROUP\s+BY\b',
        r'\bORDER\s+BY\b',
        r'\bHAVING\b',
        r'\bUNION\b',
        r'\bEXISTS\b',
        r'\bIN\s*\(',
        r'\bBETWEEN\b',
        r'\bAS\b',
        r'\bON\b',
        r'\bAND\b',
        r'\bOR\b',
        r'\bNOT\b',
        r'\bCASE\s+WHEN\b',
        r'\bEND\b',
        r'\bLIMIT\b',
        r'\bOFFSET\b'
    ]
    
    # Check if any strong SQL pattern exists
    for pattern in strong_sql_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            return True
    
    return False


def _is_definitely_python(code: str) -> bool:
    """
    Check if code is definitely Python based on strong indicators.
    """
    # Strong Python indicators
    strong_python_patterns = [
        r'\bdef\s+\w+\s*\(',
        r'\bclass\s+\w+',
        r'\bimport\s+',
        r'\bfrom\s+\w+\s+import\b',
        r'\bprint\s*\(',
        r'\breturn\s+',
        r'\bfor\s+\w+\s+in\b',
        r'\bwhile\s+',
        r'\btry\s*:',
        r'\bexcept\s*:',
        r'\bwith\s+',
        r'\basync\s+def\b',
        r'\bawait\s+',
        r'\bif\s+__name__\s*==\s*["\']__main__["\']',
        r'\bself\.',
        r'\b@\w+',
        r'\bTrue\b',
        r'\bFalse\b',
        r'\bNone\b',
        r'\blambda\s+',
        r'\byield\s+',
        r'\braise\s+',
        r'\bassert\s+',
        r'\bdel\s+',
        r'\bglobal\s+',
        r'\bnonlocal\s+'
    ]
    
    # Check if any strong Python pattern exists
    for pattern in strong_python_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            return True
    
    return False


def _weighted_language_detection(code: str) -> str:
    """
    Perform weighted analysis when language is not obvious.
    """
    sql_score = 0
    python_score = 0
    
    # SQL scoring
    sql_keywords = [
        'SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 
        'ALTER', 'DROP', 'JOIN', 'GROUP BY', 'ORDER BY', 'HAVING', 'UNION', 
        'EXISTS', 'IN', 'BETWEEN', 'AS', 'ON', 'AND', 'OR', 'NOT', 'CASE', 
        'WHEN', 'END', 'LIMIT', 'OFFSET', 'DISTINCT', 'COUNT', 'SUM', 'AVG', 
        'MAX', 'MIN', 'LIKE', 'IS NULL', 'IS NOT NULL'
    ]
    
    for keyword in sql_keywords:
        if re.search(rf'\b{re.escape(keyword)}\b', code, re.IGNORECASE):
            sql_score += 1
            logger.debug(f"SQL keyword found: {keyword}")
    
    # Python scoring
    python_keywords = [
        'def', 'class', 'import', 'from', 'print', 'return', 'for', 'while', 
        'try', 'except', 'with', 'async', 'await', 'if', 'else', 'elif', 
        'self', 'True', 'False', 'None', 'lambda', 'yield', 'raise', 'assert',
        'del', 'global', 'nonlocal', 'pass', 'break', 'continue', 'finally'
    ]
    
    for keyword in python_keywords:
        if re.search(rf'\b{re.escape(keyword)}\b', code, re.IGNORECASE):
            python_score += 1
            logger.debug(f"Python keyword found: {keyword}")
    
    # Additional Python patterns
    if re.search(r'\.\w+\s*\(', code):  # Method calls
        python_score += 2
        logger.debug("Python method call pattern found")
    
    if re.search(r'\[.*\]', code):  # List/dict access
        python_score += 1
        logger.debug("Python list/dict access pattern found")
    
    if re.search(r'f["\']', code):  # F-strings
        python_score += 3
        logger.debug("Python f-string pattern found")
    
    if re.search(r'__\w+__', code):  # Dunder methods
        python_score += 2
        logger.debug("Python dunder method pattern found")
    
    # Additional SQL patterns
    if re.search(r'`\w+`', code):  # Backticks (MySQL)
        sql_score += 2
        logger.debug("MySQL backtick pattern found")
    
    if re.search(r'\[\w+\]', code):  # Square brackets (SQL Server)
        sql_score += 2
        logger.debug("SQL Server bracket pattern found")
    
    logger.info(f"Final scores - SQL: {sql_score}, Python: {python_score}")
    
    # Determine winner
    if sql_score > python_score:
        logger.info("SQL score higher, returning SQL")
        return "sql"
    else:
        logger.info("Python score higher or equal, returning Python")
        return "python"
