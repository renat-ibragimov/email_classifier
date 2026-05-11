# email_classifier
REST API service that accepts .eml files, parses email content, and classifies it using LLM (OpenAI). Classifications are stored in PostgreSQL and deduplicated by content hash. Built with FastAPI, SQLAlchemy 2.0, and Docker Compose.
