# k0sNgin

A FastAPI application example.

## Running the Application

To run the FastAPI application with uvicorn:

```bash
uvicorn src.k0sngin.main:app --reload
```

This will start the development server with auto-reload enabled. The application will be available at `http://localhost:8000`.

### API Documentation

Once the server is running, you can access:
- Interactive API docs (Swagger UI): `http://localhost:8000/docs`
- Alternative API docs (ReDoc): `http://localhost:8000/redoc`

### Example Endpoint

- `GET /` - Returns a simple "Hello World" message
