"""
Optimization Prompts Module

Contains language-specific prompts for code optimization.
"""


def get_language_specific_prompt(language: str, question: str, description: str, user_code: str, sample_input: str, sample_output: str) -> str:
    """
    Generate detailed, comprehensive optimization prompts for better results.
    """
    if language == "sql":
        return f"""
You are a **senior MySQL performance engineer**.  
Your job is to **optimize and reformat the given SQL query** without changing its functionality.  

### INPUT
Query to analyze:
```sql
{user_code}
```

Task: {question}
Description: {description}
Expected Output: {sample_output}

### CRITICAL REQUIREMENTS - YOU MUST OBEY:

**1. MANDATORY CHANGES REQUIRED:**
- You MUST change the query formatting, spacing, or structure
- You MUST improve readability with better indentation and alignment
- You MUST optimize performance where possible
- You CANNOT return identical code - this will be rejected

**2. Preserve Exact Logic:**
- Do NOT change joins, conditions, groupings, or calculations.
- Keep all selected columns, filters, and business rules intact.
- The query must produce EXACTLY the same results.

**3. Readability & Formatting:**
- Use consistent UPPERCASE for SQL keywords (SELECT, FROM, WHERE, etc.).
- Apply proper indentation and line breaks for each clause.
- Align JOINs and conditions clearly with consistent spacing.
- Break long lines for better readability.

**4. Performance Best Practices:**
- Push restrictive filters into the WHERE clause as early as possible.
- Use explicit JOINs instead of implicit joins.
- If aggregations exist, ensure only necessary columns are included in GROUP BY.
- Remove redundant ORDER BY, LIMIT, or DISTINCT if they don't affect results.
- Consider index-friendly WHERE clause ordering.

**5. Query Validity:**
- Ensure final query ends with a semicolon.
- Must be 100% executable in MySQL with no syntax errors.
- Do NOT introduce vendor-specific SQL (stick to MySQL).

### FINAL CHECK:
Before returning, verify that your optimized query is DIFFERENT from the input in at least 2 ways:
- Different formatting/spacing
- Different indentation/alignment
- Different line breaks/structure
- Different keyword casing

### OUTPUT REQUIREMENT

Return ONLY JSON in this format:
{{
"optimized_code": "the complete optimized SQL query here",
"optimization_note": "short note on what optimization has been made"
}}

**WARNING: If you return identical code, the system will reject it and return the original.**

The optimized SQL must produce the same output as the original, but be more readable and efficient.
"""

    else:  # Python
        return f"""
You are a **Senior Python Code Optimization Expert**.  
Your job is to **optimize the given Python code** for performance, readability, and best practices **without changing its functionality or outputs**.

### INPUT
Original Code:
```python
{user_code}
```

Task: {question}
Description: {description}
Expected Input: {sample_input}
Expected Output: {sample_output}

### CRITICAL REQUIREMENTS - YOU MUST OBEY:

**1. MANDATORY CHANGES REQUIRED:**
- You MUST change the code structure, formatting, or organization
- You MUST improve variable names, spacing, or comments
- You MUST make the code more readable or efficient
- You CANNOT return identical code - this will be rejected

**2. Preserve Exact Behavior:**
- Inputs must still produce the same outputs.
- Do NOT remove or alter print/return statements that display results.
- Keep function/class signatures the same unless there's a clear improvement.
- Do not add new imports to the code if they are not already present in the original.

**3. Readability & Style:**
- Follow PEP8 style guidelines (indentation, spacing, naming conventions).
- Use meaningful variable names where beneficial.
- Remove redundant comments, dead code, or debug prints.
- Improve code structure and organization.

**4. Performance Improvements:**
- Replace inefficient loops or operations with vectorized, built-in, or Pythonic alternatives.
- Avoid unnecessary recomputations or intermediate variables.
- Prefer comprehensions, built-in functions, and libraries over manual logic where appropriate.
- Optimize data structures and algorithms if possible.

**5. Best Practices:**
- Add missing imports if required (numpy, pandas, torch, etc.).
- Use type hints where they improve clarity (List[int], pd.DataFrame, etc.).
- Ensure error handling and edge cases are not broken.
- Improve code documentation and comments.

**6. Code Validity:**
- Final code must be syntactically valid and executable.
- Do NOT return incomplete code.
- Always include all necessary import statements.

### FINAL CHECK:
Before returning, verify that your optimized code is DIFFERENT from the input in at least 2 ways:
- Different formatting/spacing
- Different variable names
- Different structure/organization
- Different comments/documentation

### OUTPUT REQUIREMENT

Return ONLY JSON in this format:
{{
"optimized_code": "the complete optimized Python code here",
"optimization_note": "short note on what optimization has been made"
}}

**WARNING: If you return identical code, the system will reject it and return the original.**
"""

