import json
from flask import request, jsonify
from app.api import api_bp
from app.services.backboard import BackboardClient
from app.config import SETTINGS_FILE

# Cache for threads by assistant_id
_thread_cache = {}


def invalidate_thread_cache(assistant_id: str = None):
    """Invalidate the thread cache for a specific assistant or all assistants"""
    global _thread_cache
    if assistant_id:
        _thread_cache.pop(assistant_id, None)
    else:
        _thread_cache.clear()


def get_backboard_client() -> BackboardClient:
    """Get Backboard client from settings"""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r") as f:
                settings_data = json.load(f)
                api_key = settings_data.get("api_key", "")
                base_url = settings_data.get("base_url", "https://app.backboard.io/api")
                assistant_id = settings_data.get("assistant_id")
                return BackboardClient(api_key, base_url, assistant_id=assistant_id)
    except:
        pass
    
    # Fallback to defaults
    from app.config import Config
    return BackboardClient(Config.BACKBOARD_API_KEY, Config.BACKBOARD_BASE_URL)


@api_bp.route("/chat", methods=["POST"])
def chat():
    """Send a chat message to the LLM"""
    try:
        data = request.get_json()
        message = data.get("message", "")
        context_notes = data.get("context_notes", None)
        assistant_id = data.get("assistant_id", None)
        thread_id = data.get("thread_id", None)
        categories = data.get("categories", None)  # Optional list of categories to filter memories
        
        if not message:
            return jsonify({"error": "Message is required"}), 400
        
        client = get_backboard_client()
        result = client.chat(message, context_notes, assistant_id=assistant_id, thread_id=thread_id, categories=categories)
        
        # Invalidate thread cache for this assistant since a new message was sent
        if assistant_id:
            invalidate_thread_cache(assistant_id)
        else:
            # If no assistant_id provided, invalidate all caches to be safe
            invalidate_thread_cache()
        
        # Handle both old string return and new dict return for backward compatibility
        if isinstance(result, dict):
            return jsonify(result), 200
        else:
            return jsonify({
                "response": result,
                "thread_id": None
            }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/threads", methods=["GET"])
def list_threads():
    """List all threads for an assistant (cached)"""
    global _thread_cache
    
    try:
        assistant_id = request.args.get("assistant_id", None)
        search = request.args.get("search", None)
        force_refresh = request.args.get("force_refresh", "false").lower() == "true"
        
        # Create cache key
        cache_key = assistant_id or "default"
        
        # Return cached result if available and no search filter and not forcing refresh
        if cache_key in _thread_cache and not search and not force_refresh:
            return jsonify(_thread_cache[cache_key]), 200
        
        # Fetch from API
        client = get_backboard_client()
        threads = client.list_threads(assistant_id=assistant_id, search=search)
        
        # Cache the result (only if no search filter, as search results shouldn't be cached)
        if not search:
            _thread_cache[cache_key] = threads
        
        return jsonify(threads), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/threads/<thread_id>", methods=["DELETE"])
def delete_thread(thread_id: str):
    """Delete a single thread"""
    try:
        client = get_backboard_client()
        success = client.delete_thread(thread_id)
        
        if success:
            # Invalidate thread cache
            invalidate_thread_cache()
            return jsonify({"message": "Thread deleted"}), 200
        else:
            return jsonify({"error": "Thread not found"}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to delete thread: {str(e)}"}), 500


@api_bp.route("/threads/bulk", methods=["DELETE"])
def delete_threads_bulk():
    """Delete multiple threads"""
    try:
        data = request.get_json()
        if not data or "thread_ids" not in data:
            return jsonify({"error": "thread_ids array is required"}), 400
        
        thread_ids = data.get("thread_ids", [])
        if not isinstance(thread_ids, list):
            return jsonify({"error": "thread_ids must be an array"}), 400
        
        if len(thread_ids) == 0:
            return jsonify({"message": "No threads to delete", "deleted": 0, "failed": 0}), 200
        
        client = get_backboard_client()
        deleted_count = 0
        failed_count = 0
        errors = []
        
        for thread_id in thread_ids:
            try:
                success = client.delete_thread(thread_id)
                if success:
                    deleted_count += 1
                else:
                    failed_count += 1
                    errors.append(f"Thread {thread_id} not found")
            except RuntimeError as e:
                failed_count += 1
                errors.append(f"Thread {thread_id}: {str(e)}")
            except Exception as e:
                failed_count += 1
                errors.append(f"Thread {thread_id}: {str(e)}")
        
        # Invalidate thread cache after bulk delete
        invalidate_thread_cache()
        
        result = {
            "message": f"Deleted {deleted_count} thread(s), {failed_count} failed",
            "deleted": deleted_count,
            "failed": failed_count
        }
        
        if errors:
            result["errors"] = errors
        
        status_code = 200 if failed_count == 0 else 207  # 207 Multi-Status for partial success
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"error": f"Failed to delete threads: {str(e)}"}), 500


@api_bp.route("/threads/<thread_id>/messages", methods=["GET"])
def get_thread_messages(thread_id: str):
    """Get all messages from a thread"""
    try:
        client = get_backboard_client()
        messages = client.get_thread_messages(thread_id)
        return jsonify(messages), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
