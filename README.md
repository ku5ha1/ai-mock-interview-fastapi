# AI Mock Interview API

A comprehensive FastAPI backend for AI-powered mock interviews with personalized feedback, code optimization, and approach analysis capabilities.

## 🚀 Features

### Core Interview Functionality
- **Dynamic Question Generation**: AI-powered question generation based on user skill level and interview type
- **Real-time Feedback**: Instant feedback on answers with detailed explanations
- **Session Management**: Persistent interview sessions with progress tracking
- **Personalized Experience**: Adaptive difficulty and question selection based on user performance

### Advanced AI Services
- **Code Optimization**: AI-powered code review and optimization suggestions
- **Approach Analysis**: Detailed analysis of problem-solving approaches
- **RAG (Retrieval-Augmented Generation)**: Enhanced responses using document knowledge base
- **Clarification System**: Intelligent follow-up questions for better understanding

### Technical Capabilities
- **MongoDB Integration**: Robust data persistence with MongoDB
- **Vector Database**: Qdrant for efficient similarity search and RAG
- **Async Operations**: High-performance asynchronous API endpoints
- **AWS Lambda Ready**: Deployable to AWS Lambda with Mangum adapter

## 📋 Prerequisites

- Python 3.8+
- MongoDB instance
- OpenAI API key
- Qdrant vector database (optional, for RAG features)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd lambda-fastapi
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```env
   MONGODB_URL=mongodb://localhost:27017
   OPENAI_API_KEY=your_openai_api_key
   QDRANT_URL=http://localhost:6333
   QDRANT_API_KEY=your_qdrant_api_key
   ```

## 🚀 Quick Start

1. **Start the development server**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Access the API documentation**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

3. **Test the API**
   ```bash
   curl http://localhost:8000/health
   ```

## 📚 API Endpoints

### Interview Management
- `POST /interview/start` - Start a new interview session
- `POST /interview/answer` - Submit an answer and get feedback
- `GET /interview/session/{session_id}` - Get session details
- `GET /interview/sessions/{user_id}` - Get user's interview history

### Code Optimization
- `POST /code/optimize` - Get code optimization suggestions
- `POST /code/review` - Comprehensive code review

### Approach Analysis
- `POST /approach/analyze` - Analyze problem-solving approach
- `GET /approach/patterns/{user_id}` - Get user's approach patterns

### RAG (Retrieval-Augmented Generation)
- `POST /rag/query` - Query the knowledge base
- `POST /rag/upload` - Upload documents to knowledge base

### User Management
- `POST /user/create` - Create new user
- `GET /user/{user_id}` - Get user profile
- `PUT /user/{user_id}` - Update user profile

## 🏗️ Project Structure

```
lambda-fastapi/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── template.yaml          # AWS SAM template for Lambda deployment
├── Dockerfile             # Docker configuration
├── API_DOCUMENTATION.md   # Detailed API documentation
├── routes/                # API route handlers
│   ├── mock_interview.py  # Interview endpoints
│   ├── code_optimization.py # Code optimization endpoints
│   ├── approach_analysis.py # Approach analysis endpoints
│   └── rag.py            # RAG endpoints
├── services/              # Business logic services
│   ├── interview.py       # Interview service
│   ├── code_optimizer.py  # Code optimization service
│   ├── approach_analysis.py # Approach analysis service
│   ├── llm/              # LLM utilities
│   ├── rag/              # RAG services
│   └── db/               # Database operations
├── models/                # Pydantic models
│   └── schemas.py        # API request/response schemas
└── data/                 # Data files and scripts
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `MONGODB_URL` | MongoDB connection string | Yes | - |
| `OPENAI_API_KEY` | OpenAI API key | Yes | - |
| `QDRANT_URL` | Qdrant vector database URL | No | http://localhost:6333 |
| `QDRANT_API_KEY` | Qdrant API key | No | - |
| `LOG_LEVEL` | Logging level | No | INFO |

### MongoDB Collections

The application uses the following MongoDB collections:
- `users` - User profiles and preferences
- `interview_sessions` - Interview session data
- `questions` - Question bank
- `user_interactions` - User interaction history

## 🚀 Deployment

### Local Development
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Deployment
```bash
docker build -t ai-mock-interview-api .
docker run -p 8000:8000 ai-mock-interview-api
```

### AWS Lambda Deployment
```bash
sam build
sam deploy --guided
```

## 📊 Usage Examples

### Starting an Interview
```python
import requests

# Start a new interview
response = requests.post("http://localhost:8000/interview/start", json={
    "user_id": "user123",
    "interview_type": "technical",
    "skill_level": "intermediate",
    "topic": "algorithms"
})

session_id = response.json()["session_id"]
question = response.json()["question"]
```

### Submitting an Answer
```python
# Submit an answer
response = requests.post("http://localhost:8000/interview/answer", json={
    "session_id": session_id,
    "answer": "I would use a hash map to solve this problem...",
    "question_id": "q123"
})

feedback = response.json()["feedback"]
score = response.json()["score"]
```

### Code Optimization
```python
# Get code optimization suggestions
response = requests.post("http://localhost:8000/code/optimize", json={
    "code": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
    "language": "python",
    "optimization_type": "performance"
})

optimized_code = response.json()["optimized_code"]
suggestions = response.json()["suggestions"]
```

## 🔍 Testing

Run the test suite:
```bash
python -m pytest tests/
```

## 📈 Monitoring and Logging

The application includes comprehensive logging:
- Request/response logging
- Performance metrics
- Error tracking
- User interaction analytics

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the [API Documentation](API_DOCUMENTATION.md)
- Review the [Troubleshooting Guide](TROUBLESHOOTING.md)

## 🔄 Version History

- **v1.0.0** - Initial release with core interview functionality
- **v1.1.0** - Added code optimization and approach analysis
- **v1.2.0** - Implemented RAG capabilities
- **v1.3.0** - Enhanced personalization and session management

---

**Built with ❤️ using FastAPI, OpenAI, and MongoDB**

