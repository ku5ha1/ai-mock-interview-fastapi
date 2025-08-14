"""
Code Execution Routes

This module provides endpoints for executing Python and MySQL code.
Replaces the One Compiler API functionality.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import logging
import asyncio
import subprocess
import tempfile
import os
import json
import re
from services.db.database import get_db
from bson import ObjectId

router = APIRouter(prefix="/code-execution", tags=["code-execution"])

# Request/Response Models
class CodeExecutionRequest(BaseModel):
    language: str
    code: str
    question_id: str
    db_setup: Optional[str] = None

class CodeExecutionResponse(BaseModel):
    status: str
    stdout: str
    stderr: str
    exception: Optional[str] = None

@router.post("/execute-code")
async def execute_code(request: CodeExecutionRequest):
    """
    Execute code based on language and return results.
    Replaces One Compiler API functionality.
    """
    try:
        if request.language.lower() == "python":
            return await execute_python_code(request.code, request.question_id)
        elif request.language.lower() == "mysql":
            return await execute_sql_code(request.code, request.question_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported language: {request.language}")
    except Exception as e:
        logging.error(f"Code execution error: {str(e)}")
        return CodeExecutionResponse(
            status="error",
            stdout="",
            stderr="",
            exception=str(e)
        )

async def execute_python_code(code: str, question_id: str) -> CodeExecutionResponse:
    """Execute Python code with test cases from question data."""
    try:
        # Get question data from MongoDB
        question_data = await get_question_data(question_id)
        
        # Log for debugging
        logging.info(f"Question data retrieved: {question_data is not None}")
        if question_data:
            logging.info(f"Question has input: {bool(question_data.get('input'))}")
            logging.info(f"Question has output: {bool(question_data.get('output'))}")
        
        # Generate test execution code
        test_execution = generate_python_test_execution(
            code, 
            question_data.get("input", "") if question_data else "",
            question_data.get("output", "") if question_data else ""
        )
        
        # Combine user code + test execution
        full_code = f"{code}\n\n{test_execution}"
        
        # Log the full code for debugging
        logging.info(f"Executing Python code with length: {len(full_code)}")
        
        # Execute code
        result = await run_python_code(full_code)
        
        return CodeExecutionResponse(
            status="success",
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            exception=result.get("exception")
        )
        
    except Exception as e:
        logging.error(f"Python execution error: {str(e)}")
        return CodeExecutionResponse(
            status="error",
            stdout="",
            stderr="",
            exception=str(e)
        )

async def execute_sql_code(code: str, question_id: str) -> CodeExecutionResponse:
    """Execute SQL code with database setup from question data."""
    try:
        # Get question data from MongoDB
        question_data = await get_question_data(question_id)
        if not question_data:
            raise Exception("Question not found")
        
        # Get database setup commands
        db_setup = question_data.get("dbSetupCommands", "")
        
        # Execute SQL
        result = await run_sql_code(code, db_setup)
        
        return CodeExecutionResponse(
            status="success",
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            exception=result.get("exception")
        )
        
    except Exception as e:
        logging.error(f"SQL execution error: {str(e)}")
        return CodeExecutionResponse(
            status="error",
            stdout="",
            stderr="",
            exception=str(e)
        )

async def get_question_data(question_id: str) -> dict:
    """Get question data from MongoDB."""
    try:
        logging.info(f"Attempting to retrieve question data for ID: {question_id}")
        
        db = await get_db()
        collection = db.mainquestionbanks
        
        # Convert string ID to ObjectId if needed
        try:
            object_id = ObjectId(question_id)
            question = await collection.find_one({"_id": object_id})
            logging.info(f"Question found with ObjectId: {question is not None}")
        except Exception as e:
            logging.warning(f"ObjectId conversion failed: {str(e)}, trying string ID")
            # If conversion fails, try with string ID
            question = await collection.find_one({"_id": question_id})
            logging.info(f"Question found with string ID: {question is not None}")
            
        if question:
            logging.info(f"Question retrieved successfully. Has input: {bool(question.get('input'))}, Has output: {bool(question.get('output'))}")
        else:
            logging.warning(f"No question found for ID: {question_id}")
            
        return question
    except Exception as e:
        logging.error(f"Database error: {str(e)}")
        return None

def generate_python_test_execution(code: str, input_data: str, expected_output: str) -> str:
    """Generate test execution code for Python functions."""
    
    # Check if code contains a function definition
    if "def " in code:
        # Extract function name from first def statement
        lines = code.split('\n')
        function_name = None
        for line in lines:
            if line.strip().startswith('def '):
                function_name = line.split('def ')[1].split('(')[0].strip()
                break
        
        if function_name and input_data:
            # Generate test execution
            test_code = f"""
# Test execution
if __name__ == "__main__":
    try:
        # Execute the function with sample input
        result = {input_data}
        
        # Display the result
        if result is not None:
            print(result)
        else:
            print("Function executed successfully (returned None)")
            
    except Exception as e:
        print(f"Error: {{e}}")
"""
            return test_code
        elif function_name:
            # Function exists but no input data - just call the function
            test_code = f"""
# Test execution
if __name__ == "__main__":
    try:
        # Function defined but no test input provided
        print("Function defined successfully. No test input provided.")
        print("Function signature:", "{function_name}")
        
    except Exception as e:
        print(f"Error: {{e}}")
"""
            return test_code
    
    # Fallback: execute the code directly
    return f"""
# Test execution
if __name__ == "__main__":
    try:
        # Execute the code directly
        {code}
    except Exception as e:
        print(f"Error: {{e}}")
"""

async def run_python_code(code: str) -> dict:
    """Execute Python code safely using subprocess."""
    try:
        # Log required packages for debugging (packages are pre-installed)
        required_packages = extract_required_packages(code)
        if required_packages:
            logging.info(f"Code requires packages: {required_packages}")
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        logging.info(f"Created temporary file: {temp_file}")
        logging.info(f"Code content preview: {code[:200]}...")
        
        try:
            # Execute with timeout
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    'python', temp_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                ),
                timeout=15.0  # Reduced timeout since no package installation
            )
            
            stdout, stderr = await process.communicate()
            
            logging.info(f"Process completed with return code: {process.returncode}")
            logging.info(f"STDOUT: {stdout.decode('utf-8', errors='ignore')}")
            logging.info(f"STDERR: {stderr.decode('utf-8', errors='ignore')}")
            
            return {
                "stdout": stdout.decode('utf-8', errors='ignore'),
                "stderr": stderr.decode('utf-8', errors='ignore'),
                "exception": None
            }
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file):
                os.unlink(temp_file)
                logging.info(f"Cleaned up temporary file: {temp_file}")
                
    except asyncio.TimeoutError:
        logging.error("Python execution timed out")
        return {
            "stdout": "",
            "stderr": "Execution timed out after 15 seconds",
            "exception": "TimeoutError"
        }
    except Exception as e:
        logging.error(f"Python execution error: {str(e)}")
        return {
            "stdout": "",
            "stderr": str(e),
            "exception": str(e)
        }

def extract_required_packages(code: str) -> list:
    """Extract required packages from import statements."""
    import re
    
    # Common data science packages that might need installation
    common_packages = {
        'torch': 'torch',
        'torchvision': 'torchvision', 
        'pandas': 'pandas',
        'numpy': 'numpy',
        'matplotlib': 'matplotlib',
        'seaborn': 'seaborn',
        'scikit-learn': 'scikit-learn',
        'scipy': 'scipy',
        'tensorflow': 'tensorflow',
        'keras': 'keras',
        'plotly': 'plotly',
        'requests': 'requests',
        'beautifulsoup4': 'beautifulsoup4',
        'selenium': 'selenium',
        'opencv-python': 'opencv-python',
        'pillow': 'pillow'
    }
    
    required = []
    
    # Check for import statements
    import_patterns = [
        r'import\s+(\w+)',
        r'from\s+(\w+)\s+import',
        r'import\s+(\w+)\s+as'
    ]
    
    for pattern in import_patterns:
        matches = re.findall(pattern, code)
        for match in matches:
            if match in common_packages:
                package_name = common_packages[match]
                if package_name not in required:
                    required.append(package_name)
    
    return required

# Package installation function removed - packages are pre-installed

async def run_sql_code(code: str, db_setup: str) -> dict:
    """Execute SQL code using SQLite database."""
    try:
        import sqlite3
        import tempfile
        import os
        
        # Create a temporary SQLite database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        try:
            # Connect to the temporary database
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            
            # Execute database setup commands first
            if db_setup:
                setup_commands = [cmd.strip() for cmd in db_setup.split(';') if cmd.strip()]
                for setup_cmd in setup_commands:
                    if setup_cmd:
                        try:
                            cursor.execute(setup_cmd)
                        except sqlite3.OperationalError as e:
                            # Skip commands that might fail (like CREATE TABLE IF NOT EXISTS)
                            if "already exists" not in str(e).lower():
                                logging.warning(f"Setup command failed: {setup_cmd} - {e}")
            
            # Execute the user's SQL query
            cursor.execute(code)
            
            # Get results
            try:
                results = cursor.fetchall()
                columns = [description[0] for description in cursor.description] if cursor.description else []
                
                # Format output
                output_lines = []
                if columns:
                    output_lines.append("Columns: " + " | ".join(columns))
                    output_lines.append("-" * (len("Columns: ") + len(" | ".join(columns))))
                
                for row in results:
                    output_lines.append(" | ".join(str(cell) for cell in row))
                
                if not results:
                    output_lines.append("Query executed successfully. No results returned.")
                
                stdout = "\n".join(output_lines)
                
            except sqlite3.OperationalError:
                # For non-SELECT queries (INSERT, UPDATE, DELETE, CREATE, etc.)
                stdout = f"Query executed successfully. {cursor.rowcount} rows affected."
            
            conn.commit()
            conn.close()
            
            return {
                "stdout": stdout,
                "stderr": "",
                "exception": None
            }
            
        finally:
            # Clean up temporary database
            if os.path.exists(temp_db):
                os.unlink(temp_db)
                
    except Exception as e:
        logging.error(f"SQL execution error: {str(e)}")
        return {
            "stdout": "",
            "stderr": str(e),
            "exception": str(e)
        }
