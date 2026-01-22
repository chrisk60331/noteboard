import json
from flask import request, jsonify
from app.api import api_bp
from app.models.settings import Settings, SettingsUpdate
from app.config import SETTINGS_FILE
from app.services.backboard import BackboardClient

# Cache for assistant list with memory counts
_assistant_cache = None

def invalidate_assistant_cache():
    """Invalidate the assistant list cache"""
    global _assistant_cache
    _assistant_cache = None


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


@api_bp.route("/settings", methods=["GET"])
def get_settings():
    """Get current settings"""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r") as f:
                settings_data = json.load(f)
                settings = Settings(**settings_data)
                return jsonify(settings.model_dump()), 200
        else:
            # Return defaults
            from app.config import Config
            settings = Settings(
                api_key=Config.BACKBOARD_API_KEY,
                model=Config.DEFAULT_MODEL,
                base_url=Config.BACKBOARD_BASE_URL,
                sync_enabled=True
            )
            return jsonify(settings.model_dump()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/settings", methods=["PUT"])
def update_settings():
    """Update settings"""
    try:
        data = request.get_json()
        settings_update = SettingsUpdate(**data)
        
        # Load existing settings
        current_settings = {}
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE, "r") as f:
                current_settings = json.load(f)
        
        # Update with new values
        update_dict = settings_update.model_dump(exclude_unset=True)
        current_settings.update(update_dict)
        
        # Save to file
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(current_settings, f, indent=2)
        
        settings = Settings(**current_settings)
        return jsonify(settings.model_dump()), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/assistants", methods=["GET"])
def list_assistants():
    """List all assistants with memory counts (cached)"""
    global _assistant_cache
    
    # Return cached result if available
    if _assistant_cache is not None:
        return jsonify(_assistant_cache), 200
    
    try:
        client = get_backboard_client()
        
        # Use SDK's list_assistants method
        if hasattr(client.sdk_client, 'list_assistants'):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            assistants = loop.run_until_complete(client.sdk_client.list_assistants())
            
            # Convert to list of dicts with assistant_id, name, and memory_count
            result = []
            if isinstance(assistants, list):
                for assistant in assistants:
                    if isinstance(assistant, dict):
                        assistant_dict = assistant
                    elif hasattr(assistant, '__dict__'):
                        assistant_dict = assistant.__dict__
                    else:
                        continue
                    
                    assistant_id = assistant_dict.get('assistant_id') or assistant_dict.get('id', '')
                    name = assistant_dict.get('name', 'Untitled')
                    
                    # Get memory count for this assistant
                    memory_count = 0
                    if assistant_id:
                        memory_count = client.get_memory_count(str(assistant_id))
                    
                    result.append({
                        'assistant_id': str(assistant_id),
                        'name': name,
                        'memory_count': memory_count
                    })
            
            # Cache the result
            _assistant_cache = result
            
            return jsonify(result), 200
        else:
            return jsonify({"error": "SDK client doesn't support list_assistants"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/assistants", methods=["POST"])
def create_assistant():
    """Create a new assistant"""
    global _assistant_cache
    
    try:
        data = request.get_json() or {}
        name = data.get("name", "Notes")
        
        if not name:
            return jsonify({"error": "Assistant name is required"}), 400
        
        client = get_backboard_client()
        
        # Use SDK's create_assistant method
        if hasattr(client.sdk_client, 'create_assistant'):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            assistant = loop.run_until_complete(client.sdk_client.create_assistant(name=name))
            
            # Convert to dict
            if isinstance(assistant, dict):
                assistant_dict = assistant
            elif hasattr(assistant, '__dict__'):
                assistant_dict = assistant.__dict__
            else:
                return jsonify({"error": "Invalid assistant response format"}), 500
            
            assistant_id = assistant_dict.get('assistant_id') or assistant_dict.get('id', '')
            assistant_name = assistant_dict.get('name', name)
            
            # Invalidate cache when a new assistant is created
            _assistant_cache = None
            
            return jsonify({
                'assistant_id': str(assistant_id),
                'name': assistant_name
            }), 201
        else:
            return jsonify({"error": "SDK client doesn't support create_assistant"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/assistants/refresh", methods=["POST"])
def refresh_assistants():
    """Manually refresh the assistant list cache"""
    invalidate_assistant_cache()
    return jsonify({"message": "Cache invalidated, next request will refresh"}), 200
