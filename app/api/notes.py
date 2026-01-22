import json
from flask import request, jsonify
from app.api import api_bp
from app.models.note import Note, NoteCreate, NoteUpdate
from app.services.backboard import BackboardClient
from app.config import SETTINGS_FILE


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


@api_bp.route("/notes", methods=["GET"])
def list_notes():
    """List all notes"""
    try:
        client = get_backboard_client()
        notes = client.list_notes()
        return jsonify([note.model_dump() for note in notes]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/notes", methods=["POST"])
def create_note():
    """Create a new note"""
    try:
        data = request.get_json()
        note_create = NoteCreate(**data)
        
        client = get_backboard_client()
        note = client.create_note(note_create)
        
        return jsonify(note.model_dump()), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/notes/<note_id>", methods=["GET"])
def get_note(note_id: str):
    """Get a note by ID"""
    try:
        client = get_backboard_client()
        note = client.get_note(note_id)
        
        if note:
            return jsonify(note.model_dump()), 200
        else:
            return jsonify({"error": "Note not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/notes/<note_id>", methods=["PUT"])
def update_note(note_id: str):
    """Update a note"""
    try:
        data = request.get_json()
        note_update = NoteUpdate(**data)
        
        client = get_backboard_client()
        note = client.update_note(note_id, note_update)
        
        if note:
            return jsonify(note.model_dump()), 200
        else:
            return jsonify({"error": "Note not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/notes/<note_id>", methods=["DELETE"])
def delete_note(note_id: str):
    """Delete a note"""
    try:
        client = get_backboard_client()
        success = client.delete_note(note_id)
        
        if success:
            return jsonify({"message": "Note deleted"}), 200
        else:
            return jsonify({"error": "Note not found"}), 404
    except RuntimeError as e:
        # RuntimeError from BackboardClient contains the actual error message
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to delete note: {str(e)}"}), 500


@api_bp.route("/notes/bulk", methods=["DELETE"])
def delete_notes_bulk():
    """Delete multiple notes"""
    try:
        data = request.get_json()
        if not data or "note_ids" not in data:
            return jsonify({"error": "note_ids array is required"}), 400
        
        note_ids = data.get("note_ids", [])
        if not isinstance(note_ids, list):
            return jsonify({"error": "note_ids must be an array"}), 400
        
        if len(note_ids) == 0:
            return jsonify({"message": "No notes to delete", "deleted": 0, "failed": 0}), 200
        
        client = get_backboard_client()
        deleted_count = 0
        failed_count = 0
        errors = []
        
        for note_id in note_ids:
            try:
                success = client.delete_note(note_id)
                if success:
                    deleted_count += 1
                else:
                    failed_count += 1
                    errors.append(f"Note {note_id} not found")
            except RuntimeError as e:
                failed_count += 1
                errors.append(f"Note {note_id}: {str(e)}")
            except Exception as e:
                failed_count += 1
                errors.append(f"Note {note_id}: {str(e)}")
        
        result = {
            "message": f"Deleted {deleted_count} note(s), {failed_count} failed",
            "deleted": deleted_count,
            "failed": failed_count
        }
        
        if errors:
            result["errors"] = errors
        
        status_code = 200 if failed_count == 0 else 207  # 207 Multi-Status for partial success
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"error": f"Failed to delete notes: {str(e)}"}), 500