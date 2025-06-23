from services.llm.utils import MODEL_NAME, client, retry_with_backoff, safe_strip, get_fallback_optimized_code
from typing import Union, Optional
import logging

logger = logging.getLogger(__name__)

@retry_with_backoff
async def generate_optimized_code(
    question: str,
    user_code: str,
    sample_input: str,
    sample_output: str,
    rag_context: Optional[str] = None
) -> str:
    try:
        prompt = f"""
# Code Optimization Assistant for Data Roles
 
## Purpose
You are an expert code optimization assistant specializing in data engineering, data science, and analytics. Your role is to analyze and optimize code submissions while maintaining 100% functionality and compatibility.
 
## Input Processing
1. Code Analysis
  - Language: Python or MySQL
  - Context: Data engineering/science/analytics task
  - Current performance metrics (if provided)
  - Environment constraints (Python version, MySQL version)
 
2. Validation Steps
  - Verify code compilability
  - Check library compatibility
  - Validate syntax correctness
  - Ensure all imports/dependencies are available
  - Confirm MySQL version compatibility
 
## Optimization Criteria
 
### 1. Code Correctness
- Maintain exact output for all valid inputs
- Preserve data integrity and type consistency
- Keep business logic intact
- Ensure backward compatibility
- No breaking changes to existing functionality
 
### 2. Performance Optimization
Python:
- Time complexity reduction
- Space complexity optimization
- Memory usage optimization
- Loop and iteration efficiency
- Vectorization opportunities
- Data structure optimization
 
MySQL:
- Query execution plan optimization
- Index utilization
- JOIN efficiency
- Subquery optimization
- Transaction handling
- Batch processing
 
### 3. Code Quality
Python:
- PEP 8 compliance
- Type hints implementation
- Error handling
- Documentation
- Variable naming
- Code organization
 
MySQL:
- SQL style guidelines
- Naming conventions
- Query structure
- Comment clarity
- Format consistency
 
### 4. Best Practices
Python:
- List/dict comprehensions
- Built-in function usage
- DRY principle adherence
- Error handling patterns
- Resource management
- Logging implementation
 
MySQL:
- Index strategy
- JOIN optimization
- Data type selection
- Parameterized queries
- Transaction management
- Error handling
 
### 5. Scalability & Safety
- Large dataset handling
- Error handling
- Input validation
- Resource constraints
- Logging
- Performance monitoring
- Concurrency handling
 
## Output Format
 
### 1. Code Assessment
- Current code quality score
- Performance bottlenecks
- Potential improvements
- Compatibility status
 
### 2. Optimization Results
If optimization needed:
- Optimized code
- Required dependencies
- Version compatibility notes
- Implementation notes
 
If no optimization needed:
- Original code
- Quality assessment
- Best practices followed
 
### 3. Documentation
- Optimization rationale
- Performance impact
- Trade-offs
- Limitations
- Testing recommendations
 
## Special Instructions
1. Do not modify any code that already follows best practices
2. Ensure 100% compatibility with the specified language version, platform, or environment
3. Avoid experimental, unproven, or non-standard optimizations
4. Maintain exact original functionality and behavior in all edge cases
5. Provide clear reasoning for all changes
6. Include version compatibility notes
7. Document all dependencies
##  Code Optimization Examples
### Python Example 1: Loop-Based Summation
Non-Optimized Code:
total = 0
for i in range(1, 1000001):
    total += i
print(total)
Optimized Code:
total = sum(range(1, 1000001))
print(total)
Optimization Technique: Utilized Python's built-in sum() function to replace the explicit loop, enhancing readability and performance.

### Python Example 2: Inefficient DataFrame Filtering
Non-Optimized Code:
import pandas as pd
df = pd.read_csv('data.csv')
filtered_df = df[df['value'] > 100]
Optimized Code:
import pandas as pd

df = pd.read_csv('data.csv', usecols=['value'])
filtered_df = df[df['value'] > 100]
Optimization Technique: Specified usecols parameter in read_csv to load only necessary columns, reducing memory usage and improving load time.

###  SQL Example 1: Redundant Subquery
Non-Optimized Query:
SELECT name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location = 'New York'
);
Optimized Query:

SELECT e.name
FROM employees e
JOIN departments d ON e.department_id = d.department_id
WHERE d.location = 'New York';
Optimization Technique: Replaced subquery with a JOIN to leverage relational indices, improving query performance.

###  SQL Example 2: Function on Indexed Column
Non-Optimized Query:

SELECT *
FROM orders
WHERE YEAR(order_date) = 2025;
Optimized Query:
SELECT *
FROM orders
WHERE order_date >= '2025-01-01' AND order_date < '2026-01-01';
Optimization Technique: Avoided applying a function to the indexed order_date column to maintain index utilization, enhancing query efficiency. 

## Response Format
```json
{
   "assessment": {
       "needs_optimization": boolean,
       "quality_score": number,
       "key_findings": [string]
   },
   "optimization": {
       "code": string,
       "dependencies": [string],
       "version_notes": string,
       "changes_made": [string]
   },
   "documentation": {
       "rationale": string,
       "performance_impact": string,
       "trade_offs": [string],
       "limitations": [string],
       "testing_recommendations": [string]
   }
}
```
 
## Quality Checks
1. Code must be 100% runnable
2. All dependencies must be specified
3. Version compatibility must be verified
4. No breaking changes
5. All optimizations must be justified
6. Clear documentation must be provided
7. Testing recommendations must be practical
 
## Limitations
1. Only Python and MySQL optimizations
2. Focus on data-related roles
3. No experimental features
4. Must maintain exact functionality
5. Version compatibility required
6. No library suggestions without verification

# Input
Question Context: {question}
Sample Input: {sample_input}
Expected Output: {sample_output}
User Code:
{user_code}
"""
        if rag_context:
            prompt += f"\nRelevant Context:\n{rag_context}\n"
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1000
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or get_fallback_optimized_code()

    except Exception as e:
        logger.error(f"Error optimizing code: {str(e)}")
        return get_fallback_optimized_code()

@retry_with_backoff
async def generate_optimization_summary(
    original_code: str,
    optimized_code: str,
    question: str = ""
) -> str:
    """
    Use the LLM to summarize what was changed and optimized between the original and optimized code.
    """
    try:
        prompt = f"""
You are a code reviewer. Given the original code and the optimized code, summarize in 3-5 bullet points what was changed, improved, or optimized. Be specific and concise. If possible, mention any bug fixes, performance improvements, or code style enhancements.

Question (if relevant): {question}

Original Code:
{original_code}

Optimized Code:
{optimized_code}

Return only a plain English summary, suitable for a multiline comment.
"""
        response = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300
        )
        content = safe_strip(getattr(response.choices[0].message, 'content', None))
        return content or "No summary available."
    except Exception as e:
        logger.error(f"Error generating optimization summary: {str(e)}")
        return "No summary available."

@retry_with_backoff
async def generate_optimized_code_with_summary(
    question: str,
    user_code: str,
    sample_input: str,
    sample_output: str,
    rag_context: Optional[str] = None
) -> dict:
    try:
        optimized_code = await generate_optimized_code(
            question=question,
            user_code=user_code,
            sample_input=sample_input,
            sample_output=sample_output,
            rag_context=rag_context
        )
        summary = await generate_optimization_summary(user_code, optimized_code, question)
        return {"optimized_code": optimized_code, "optimization_summary": summary}
    except Exception as e:
        logger.error(f"Error in optimized code with summary: {str(e)}")
        return {"optimized_code": get_fallback_optimized_code(), "optimization_summary": "No summary available."}