"""
Code Execution Routes

This module provides endpoints for executing Python and MySQL code.
Replaces the One Compiler API functionality.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
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
    files: List[dict]  # Array of files with name and content
    stdin: Optional[str] = None

# Remove this model - we don't need it anymore

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
        # Extract code from files array (like One Compiler does)
        if not request.files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        code = request.files[0].get("content", "")
        if not code:
            raise HTTPException(status_code=400, detail="No code content provided")
        
        # Always execute the code as-is (maintain One Compiler compatibility)
        if request.language.lower() == "python":
            return await execute_python_code(code, request.stdin)
        elif request.language.lower() == "mysql":
            logging.info(f"MySQL execution requested")
            return await execute_sql_code(code)
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

# Remove this endpoint - we'll handle coding questions in the main execute-code endpoint

async def execute_python_code(code: str, stdin: Optional[str] = None) -> CodeExecutionResponse:
    """Execute Python code with optional stdin input."""
    try:
        # Log the code for debugging
        logging.info(f"Executing Python code with length: {len(code)}")
        logging.info(f"Stdin provided: {repr(stdin) if stdin is not None else 'None'}")
        
        # Execute code directly (no test execution wrapper needed)
        result = await run_python_code(code, stdin)
        
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

async def execute_sql_code(code: str) -> CodeExecutionResponse:
    """Execute SQL code."""
    try:
        # Execute SQL with automatic database setup detection
        result = await run_sql_code(code)
        
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

def is_coding_question(code: str) -> bool:
    """Detect if the code is a coding question (has function definition)."""
    # Universal detection: if code contains function definition, it's a coding question
    return "def " in code

def detect_question_type_and_get_test_cases(code: str) -> dict:
    """Universal function analyzer - detects function signature and generates appropriate test cases."""
    import re
    
    # Find all function definitions
    function_pattern = r'def\s+(\w+)\s*\(([^)]*)\)\s*->?\s*([^:]*):'
    matches = re.findall(function_pattern, code)
    
    if not matches:
        return {"test_cases": ["test"], "function_name": "unknown"}
    
    function_name, params, return_type = matches[0]
    
    # Parse parameters
    param_list = [p.strip() for p in params.split(',') if p.strip()]
    
    # Generate test cases based on function signature
    test_cases = generate_universal_test_cases(function_name, param_list, return_type)
    
    return {
        "test_cases": test_cases,
        "function_name": function_name,
        "parameters": param_list,
        "return_type": return_type
    }

def generate_universal_test_cases(function_name: str, parameters: list, return_type: str) -> list:
    """Generate test cases based on function signature analysis."""
    
    # Remove type hints and default values from parameters
    clean_params = []
    for param in parameters:
        # Remove type hints (e.g., "x: int" -> "x")
        if ':' in param:
            param = param.split(':')[0].strip()
        # Remove default values (e.g., "x=5" -> "x")
        if '=' in param:
            param = param.split('=')[0].strip()
        clean_params.append(param)
    
    # Generate test cases based on parameter types and function name
    test_cases = []
    
    # String-based functions (palindrome, reverse, etc.)
    if any('str' in return_type.lower() or 'string' in return_type.lower() or 
           any('str' in p.lower() for p in parameters)):
        test_cases.extend([
            "madam", "racecar", "hello", "", "a", "aa", "ab", "12321", "!@#@!"
        ])
    
    # Numeric functions (factorial, fibonacci, etc.)
    elif any('int' in return_type.lower() or 'float' in return_type.lower() or
             any('int' in p.lower() or 'float' in p.lower() for p in parameters)):
        test_cases.extend([
            "1", "2", "3", "5", "10", "0", "-1"
        ])
    
    # DataFrame functions (pandas)
    elif any('df' in p.lower() or 'dataframe' in p.lower() or 'pd.' in p.lower() for p in parameters):
        test_cases.append("dataframe_test")
    
    # List/Array functions
    elif any('list' in p.lower() or 'array' in p.lower() for p in parameters):
        test_cases.extend([
            "[1, 2, 3]", "[1, 1, 1]", "[]", "[5]"
        ])
    
    # Default case
    if not test_cases:
        test_cases = ["test_input"]
    
    return test_cases

def create_executable_code(student_code: str, question_info: dict) -> str:
    """Create executable code by combining student code with test execution logic."""
    
    # Remove 'pass' statement if it exists
    if "pass" in student_code:
        student_code = student_code.replace("pass", "")
    
    function_name = question_info.get("function_name", "unknown")
    test_cases = question_info.get("test_cases", ["test"])
    parameters = question_info.get("parameters", [])
    
    # Create the executable code - use regular string formatting to avoid f-string conflicts
    executable_code = f"""{student_code}

# Test execution logic
import sys

# Run test cases
test_cases = {repr(test_cases)}
function_name = "{function_name}"
parameters = {repr(parameters)}

for i, test_input in enumerate(test_cases, 1):
    try:
        print("Test Case " + str(i) + ": Input = " + repr(test_input))
        
        # Universal function testing based on parameter count and types
        if test_input == "dataframe_test":
            print("Testing DataFrame function...")
            
            # Create sample DataFrame for testing
            import pandas as pd
            sample_data = {{
                "col1": [1, 2, 3, 4, 5],
                "col2": ["a", "b", "c", "d", "e"],
                "col3": [10.5, 20.5, 30.5, 40.5, 50.5]
            }}
            sample_df = pd.DataFrame(sample_data)
            print("Sample DataFrame:")
            print(sample_df)
            print()
            
            # Test the student's function
            try:
                result = {function_name}(sample_df)
                print("Function result:")
                print(result)
                print("[PASS] Function executed successfully")
            except Exception as func_error:
                print("[ERROR] Function execution error: " + str(func_error))
                
        elif len(parameters) == 1:
            # Single parameter function
            try:
                result = {function_name}(test_input)
                print("Result: " + str(result))
            except Exception as func_error:
                print("[ERROR] Function execution error: " + str(func_error))
                
        elif len(parameters) == 2:
            # Two parameter function
            try:
                result = {function_name}(test_input, "param2")
                print("Result: " + str(result))
            except Exception as func_error:
                print("[ERROR] Function execution error: " + str(func_error))
                
        elif len(parameters) == 3:
            # Three parameter function
            try:
                result = {function_name}(test_input, "param2", "param3")
                print("Result: " + str(result))
            except Exception as func_error:
                print("[ERROR] Function execution error: " + str(func_error))
                
        else:
            # Multiple parameters - try with the test input as first parameter
            try:
                # Create a list of parameters, starting with test_input
                args = [test_input] + ["default_param"] * (len(parameters) - 1)
                result = {function_name}(*args)
                print("Result: " + str(result))
            except Exception as func_error:
                print("[ERROR] Function execution error: " + str(func_error))
        
        print("-" * 40)
    except Exception as e:
        print("Error in test case " + str(i) + ": " + str(e))
        print("-" * 40)
"""
    
    return executable_code

# This function is no longer needed since we execute code directly

async def run_python_code(code: str, stdin: Optional[str] = None) -> dict:
    """Execute Python code safely using subprocess."""
    try:
        # Log required packages for debugging (packages are pre-installed)
        required_packages = extract_required_packages(code)
        if required_packages:
            logging.info(f"Code requires packages: {required_packages}")
        
        # Create temporary file with UTF-8 encoding
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            # Clean the code by replacing problematic characters
            cleaned_code = code.replace('×', '*').replace('→', '->').replace('≤', '<=').replace('≥', '>=')
            f.write(cleaned_code)
            temp_file = f.name
        
        logging.info(f"Created temporary file: {temp_file}")
        logging.info(f"Code content preview: {code[:200]}...")
        
        # Verify file was created and has content
        if os.path.exists(temp_file):
            file_size = os.path.getsize(temp_file)
            logging.info(f"Temporary file size: {file_size} bytes")
            
            # Read and log the file content for debugging
            with open(temp_file, 'r') as f:
                file_content = f.read()
                logging.info(f"File content: {repr(file_content)}")
        else:
            logging.error("Temporary file was not created!")
            return {
                "stdout": "",
                "stderr": "Failed to create temporary file",
                "exception": "File creation failed"
            }
        
        try:
            # Check if python command exists
            import shutil
            python_cmd = shutil.which('python') or shutil.which('python3') or 'python'
            logging.info(f"Using Python command: {python_cmd}")
            
            # Use synchronous subprocess for Windows compatibility
            import subprocess
            import threading
            import time
            
            # Create a thread to run the subprocess with timeout
            result = {"stdout": "", "stderr": "", "exception": None}
            process = None
            
            def run_subprocess():
                nonlocal result, process
                try:
                    # Always create stdin pipe, but pass empty string if no stdin provided
                    process = subprocess.Popen(
                        [python_cmd, temp_file],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    # If stdin is None or empty, pass a newline to prevent blocking
                    # Also ensure empty string gets a newline to prevent readline() from blocking
                    if stdin is None or stdin == "":
                        input_data = "\n"
                    else:
                        # Ensure stdin ends with newline if it doesn't already
                        input_data = stdin if stdin.endswith('\n') else stdin + '\n'
                    
                    logging.info(f"Input data being sent to subprocess: {repr(input_data)}")
                    stdout, stderr = process.communicate(input=input_data, timeout=15.0)
                    
                    result["stdout"] = stdout
                    result["stderr"] = stderr
                    result["exception"] = None
                    
                except subprocess.TimeoutExpired:
                    if process:
                        process.kill()
                    result["exception"] = "TimeoutError"
                    result["stderr"] = "Execution timed out after 15 seconds"
                except Exception as e:
                    result["exception"] = str(e)
                    result["stderr"] = str(e)
            
            # Run in thread with timeout
            thread = threading.Thread(target=run_subprocess)
            thread.start()
            thread.join(timeout=16.0)  # Slightly longer than subprocess timeout
            
            if thread.is_alive():
                if process:
                    process.kill()
                thread.join(timeout=1.0)
                result["exception"] = "TimeoutError"
                result["stderr"] = "Execution timed out after 15 seconds"
            
            logging.info(f"Process completed with result: {result}")
            
            return result
            
        except Exception as e:
            logging.error(f"Subprocess execution error: {str(e)}")
            logging.error(f"Exception type: {type(e).__name__}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
            return {
                "stdout": "",
                "stderr": str(e),
                "exception": str(e)
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
        logging.error(f"Exception type: {type(e).__name__}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
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

async def run_sql_code(code: str) -> dict:
    """Execute SQL code using SQLite database."""
    temp_db = None
    conn = None
    cursor = None
    
    try:
        import sqlite3
        import tempfile
        import os
        
        logging.info(f"Starting SQL execution with code length: {len(code)}")
        
        # Handle concatenated content from frontend (One Compiler format)
        db_setup = None
        if "CREATE TABLE" in code:
            logging.info("Detected concatenated setup + query format from frontend")
            sql_parts = [part.strip() for part in code.split(';') if part.strip()]
            
            setup_commands = []
            user_query = ""
            
            # Separate setup commands from user query
            for part in sql_parts:
                if part.upper().startswith(('CREATE', 'INSERT', 'DROP', 'ALTER')):
                    setup_commands.append(part)
                else:
                    user_query = part
                    break
            
            if setup_commands:
                logging.info(f"Extracted {len(setup_commands)} setup commands and user query")
                db_setup = '; '.join(setup_commands)
                code = user_query  # Use only the user's query part
                logging.info(f"User query: {repr(user_query)}")
        
        if db_setup:
            logging.info(f"Database setup commands preview: {db_setup[:200]}...")
        else:
            logging.info("No database setup commands detected")
        
        # Create a temporary SQLite database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            temp_db = f.name
        
        logging.info(f"Created temporary database: {temp_db}")
        
        # Connect to the temporary database
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        logging.info("Successfully connected to temporary database")
        
        # Execute database setup commands first
        if db_setup:
            # Split by semicolon and filter out empty commands
            setup_commands = []
            for cmd in db_setup.split(';'):
                cmd = cmd.strip()
                if cmd and not cmd.startswith('--'):  # Skip empty commands and comments
                    setup_commands.append(cmd)
            
            logging.info(f"Executing {len(setup_commands)} database setup commands")
            for i, setup_cmd in enumerate(setup_commands):
                try:
                    logging.info(f"Executing setup command {i+1}: {repr(setup_cmd)}")
                    cursor.execute(setup_cmd)
                    conn.commit()  # Commit after each command to ensure it's applied
                    logging.info(f"Setup command {i+1} executed successfully")
                except sqlite3.OperationalError as e:
                    # Skip commands that might fail (like CREATE TABLE IF NOT EXISTS)
                    if "already exists" not in str(e).lower():
                        logging.warning(f"Setup command failed: {setup_cmd} - {e}")
                        # For debugging, let's see what the actual error is
                        logging.warning(f"Error details: {str(e)}")
        else:
            logging.info("No database setup commands provided")
        
        # Verify that the reviews table exists (for debugging)
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'")
            table_exists = cursor.fetchone()
            logging.info(f"Reviews table exists: {table_exists is not None}")
            if table_exists:
                cursor.execute("SELECT COUNT(*) FROM reviews")
                row_count = cursor.fetchone()[0]
                logging.info(f"Reviews table has {row_count} rows")
        except Exception as e:
            logging.warning(f"Could not verify table existence: {e}")
        
        # Execute the user's SQL query
        logging.info("Executing user SQL query")
        cursor.execute(code)
        logging.info("User SQL query executed successfully")
        
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
        
        return {
            "stdout": stdout,
            "stderr": "",
            "exception": None
        }
        
    except Exception as e:
        logging.error(f"SQL execution error: {str(e)}")
        return {
            "stdout": "",
            "stderr": str(e),
            "exception": str(e)
        }
    finally:
        # Ensure proper cleanup in the correct order
        try:
            if cursor:
                cursor.close()
        except Exception as e:
            logging.warning(f"Error closing cursor: {e}")
        
        try:
            if conn:
                conn.close()
        except Exception as e:
            logging.warning(f"Error closing connection: {e}")
        
        # Clean up temporary database file after connection is closed
        try:
            if temp_db and os.path.exists(temp_db):
                # Force close any remaining handles
                import gc
                gc.collect()
                
                # Try to remove the file
                os.unlink(temp_db)
                logging.info(f"Successfully cleaned up temporary database: {temp_db}")
        except Exception as e:
            logging.warning(f"Error cleaning up temporary database {temp_db}: {e}")
            # Sometimes we need to wait a bit for file handles to be released
            try:
                import time
                time.sleep(0.2)  # Increased delay for better reliability
                if os.path.exists(temp_db):
                    os.unlink(temp_db)
                    logging.info(f"Successfully cleaned up temporary database after delay: {temp_db}")
            except Exception as e2:
                logging.error(f"Failed to clean up temporary database {temp_db} even after delay: {e2}")
                # On EC2/Linux, we can try using system commands as a last resort
                try:
                    import subprocess
                    subprocess.run(['rm', '-f', temp_db], capture_output=True, timeout=5)
                    logging.info(f"Used system command to clean up temporary database: {temp_db}")
                except Exception as e3:
                    logging.error(f"All cleanup methods failed for {temp_db}: {e3}")
