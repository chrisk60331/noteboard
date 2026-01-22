import json
import re
from collections import Counter
from flask import request, jsonify, Response, stream_with_context
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


@api_bp.route("/categories", methods=["GET"])
def list_categories():
    """List all categories with note counts"""
    try:
        client = get_backboard_client()
        notes = client.list_notes()
        
        # Count categories across all notes
        category_counter = Counter()
        for note in notes:
            if note.categories:
                category_counter.update(note.categories)
        
        # Convert to list of dicts with counts
        categories = [{"name": name, "count": count} for name, count in category_counter.most_common()]
        
        return jsonify(categories), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/categories/<category_name>", methods=["DELETE"])
def delete_category(category_name: str):
    """Delete a category from all notes"""
    try:
        client = get_backboard_client()
        notes = client.list_notes()
        
        updated_count = 0
        for note in notes:
            if note.categories and category_name in note.categories:
                # Remove category from note
                updated_categories = [c for c in note.categories if c != category_name]
                note_update = NoteUpdate(categories=updated_categories)
                updated_note = client.update_note(note.id, note_update)
                if updated_note:
                    updated_count += 1
        
        return jsonify({
            "message": f"Category '{category_name}' removed from {updated_count} note(s)",
            "updated_count": updated_count
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/notes/<note_id>/extract-categories", methods=["POST"])
def extract_categories(note_id: str):
    """Automatically extract categories for a note using Backboard LLM"""
    try:
        client = get_backboard_client()
        # Get note from list since get_note doesn't work with memory IDs
        all_notes = client.list_notes()
        note = next((n for n in all_notes if n.id == note_id), None)
        
        if not note:
            return jsonify({"error": "Note not found"}), 404
        
        # Prepare prompt for LLM
        prompt = f"""Analyze this note and suggest 3-5 relevant category tags. Return only a JSON array of tag names, nothing else.

Note Title: {note.title}
Note Content: {note.content[:1000]}

Return format: ["tag1", "tag2", "tag3"]"""

        # Use Backboard LLM to extract categories
        assistant_id = client._get_or_create_default_assistant()
        result = client.chat(prompt, assistant_id=assistant_id)
        
        # Parse LLM response to extract categories
        response_text = result.get("response", "") if isinstance(result, dict) else str(result)
        
        # Try to extract JSON array from response
        categories = []
        # Look for JSON array pattern
        json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
        if json_match:
            try:
                categories = json.loads(json_match.group(0))
                if not isinstance(categories, list):
                    categories = []
            except json.JSONDecodeError:
                # Try to extract quoted strings
                quoted_matches = re.findall(r'"([^"]+)"', response_text)
                categories = quoted_matches[:5]  # Limit to 5 categories
        
        # Merge with existing categories (avoid duplicates)
        existing_categories = note.categories or []
        all_categories = list(set(existing_categories + categories))
        
        # Since update_note creates a new note (can't match IDs), we need to:
        # 1. Delete the old note
        # 2. Create a new note with updated categories
        try:
            # Try to delete the old note (may fail if ID doesn't match, but that's ok)
            client.delete_note(note_id)
        except:
            pass  # Ignore delete errors
        
        # Create new note with updated categories
        note_create = NoteCreate(
            title=note.title,
            content=note.content,
            categories=all_categories
        )
        updated_note = client.create_note(note_create)
        
        if updated_note:
            return jsonify({
                "message": f"Extracted {len(categories)} categories",
                "extracted_categories": categories,
                "note": updated_note.model_dump(mode='json')
            }), 200
        else:
            return jsonify({"error": "Failed to update note"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/notes/bulk/extract-categories", methods=["POST"])
def extract_categories_bulk():
    """Extract categories for multiple notes - streams progress updates"""
    try:
        data = request.get_json()
        note_ids = data.get("note_ids", []) if data else []
        
        if not isinstance(note_ids, list):
            return jsonify({"error": "note_ids must be an array"}), 400
        
        if len(note_ids) == 0:
            return jsonify({"message": "No notes to process", "processed": 0, "failed": 0}), 200
        
        client = get_backboard_client()
        
        def generate():
            processed_count = 0
            failed_count = 0
            errors = []
            
            yield f"data: {json.dumps({'type': 'start', 'message': f'Starting extraction for {len(note_ids)} notes...', 'total': len(note_ids)})}\n\n"
            
            # Get all notes once to find notes by ID (since get_note doesn't work with memory IDs)
            yield f"data: {json.dumps({'type': 'status', 'message': 'Loading notes...'})}\n\n"
            all_notes = client.list_notes()
            notes_by_id = {note.id: note for note in all_notes}
            
            for i, note_id in enumerate(note_ids):
                try:
                    # Get note from the list (get_note doesn't work with memory IDs)
                    note = notes_by_id.get(note_id)
                    if not note:
                        failed_count += 1
                        errors.append(f"Note {note_id} not found")
                        yield f"data: {json.dumps({'type': 'error', 'note_id': note_id, 'note_title': 'Unknown', 'error': 'Note not found'})}\n\n"
                        yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': len(note_ids), 'processed': processed_count, 'failed': failed_count})}\n\n"
                        continue
                    
                    yield f"data: {json.dumps({'type': 'status', 'message': f'Processing: {note.title[:50]}...', 'note_id': note_id, 'note_title': note.title})}\n\n"
                    
                    # Extract categories
                    prompt = f"""Analyze this note and suggest 3-5 relevant category tags. Return only a JSON array of tag names, nothing else.

Note Title: {note.title}
Note Content: {note.content[:1000]}

Return format: ["tag1", "tag2", "tag3"]"""
                    
                    assistant_id = client._get_or_create_default_assistant()
                    result = client.chat(prompt, assistant_id=assistant_id)
                    
                    response_text = result.get("response", "") if isinstance(result, dict) else str(result)
                    json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
                    categories = []
                    if json_match:
                        try:
                            categories = json.loads(json_match.group(0))
                            if not isinstance(categories, list):
                                categories = []
                        except json.JSONDecodeError:
                            quoted_matches = re.findall(r'"([^"]+)"', response_text)
                            categories = quoted_matches[:5]
                    
                    # Merge with existing
                    existing_categories = note.categories or []
                    all_categories = list(set(existing_categories + categories))
                    
                    # Since update_note creates a new note (can't match IDs), we need to:
                    # 1. Delete the old note
                    # 2. Create a new note with updated categories
                    try:
                        # Try to delete the old note (may fail if ID doesn't match, but that's ok)
                        client.delete_note(note_id)
                    except:
                        pass  # Ignore delete errors
                    
                    # Create new note with updated categories
                    note_create = NoteCreate(
                        title=note.title,
                        content=note.content,
                        categories=all_categories
                    )
                    updated_note = client.create_note(note_create)
                    
                    if updated_note:
                        processed_count += 1
                        # Use model_dump with mode='json' to properly serialize datetime objects
                        note_dict = updated_note.model_dump(mode='json')
                        yield f"data: {json.dumps({'type': 'note', 'note_id': note_id, 'note_title': note.title, 'extracted_categories': categories, 'all_categories': all_categories, 'note': note_dict})}\n\n"
                    else:
                        failed_count += 1
                        errors.append(f"Note {note_id}: Failed to update")
                        yield f"data: {json.dumps({'type': 'error', 'note_id': note_id, 'note_title': note.title, 'error': 'Failed to update'})}\n\n"
                    
                    # Progress update
                    yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': len(note_ids), 'processed': processed_count, 'failed': failed_count})}\n\n"
                    
                except Exception as e:
                    failed_count += 1
                    error_msg = str(e)
                    errors.append(f"Note {note_id}: {error_msg}")
                    note_title = 'Unknown'
                    try:
                        note = client.get_note(note_id)
                        if note:
                            note_title = note.title
                    except:
                        pass
                    yield f"data: {json.dumps({'type': 'error', 'note_id': note_id, 'note_title': note_title, 'error': error_msg})}\n\n"
                    yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': len(note_ids), 'processed': processed_count, 'failed': failed_count})}\n\n"
            
            # Final summary
            yield f"data: {json.dumps({'type': 'complete', 'message': f'Extraction complete: {processed_count} processed, {failed_count} failed', 'processed': processed_count, 'failed': failed_count, 'errors': errors})}\n\n"
        
        return Response(stream_with_context(generate()), mimetype='text/event-stream')
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500