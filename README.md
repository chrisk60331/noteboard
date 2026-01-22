# NoteBoard

A Flask application that imports Apple Notes to Backboard.io, provides an Apple Notes-like editor interface, and enables LLM chat via Backboard.io API.

## What it does

- Imports Apple Notes from macOS
- Syncs notes to Backboard.io assistant memory
- Provides an Apple Notes-like editing interface
- Enables LLM chat with your notes

## How to run

1. Create a `.env` file with your configuration:
   ```
   BACKBOARD_API_KEY=your_api_key_here
   BACKBOARD_BASE_URL=https://app.backboard.io/api
   FLASK_ENV=development
   ```

2. Start the application:
   ```bash
   ./start.sh
   ```

The application will be available at http://localhost:9000
