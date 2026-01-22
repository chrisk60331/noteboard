import json
import os
from flask import request, jsonify, Response, stream_with_context
from app.api import api_bp
from app.services.apple_notes import AppleNotesReader
from app.services.backboard import BackboardClient
from app.config import SETTINGS_FILE
from app.api.settings import invalidate_assistant_cache

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
    except Exception as e:
        pass
    
    # Fallback to defaults
    from app.config import Config
    return BackboardClient(Config.BACKBOARD_API_KEY, Config.BACKBOARD_BASE_URL)

@api_bp.route("/sync/import", methods=["POST"])
def import_notes():
    """Import notes from Apple Notes to Backboard.io (legacy endpoint)"""
    try:
        data = request.get_json() or {}
        first_n = data.get('first_n')
        last_n = data.get('last_n')
        
        reader = AppleNotesReader()
        # Use cached version for faster processing
        force_refresh = data.get('force_refresh', False)
        apple_notes = reader.get_all_notes_cached(force_refresh=force_refresh)
        
        # Apply limits if specified
        if first_n is not None and first_n > 0:
            apple_notes = apple_notes[:first_n]
        elif last_n is not None and last_n > 0:
            apple_notes = apple_notes[-last_n:]
        
        client = get_backboard_client()
        synced_notes = []
        errors = []
        
        for note in apple_notes:
            try:
                synced_note = client.sync_note(note)
                if synced_note:
                    synced_notes.append(synced_note.model_dump())
            except Exception as e:
                errors.append({
                    "note_id": note.id,
                    "title": note.title,
                    "error": str(e)
                })
        
        # Invalidate assistant cache since memory counts may have changed
        invalidate_assistant_cache()
        
        return jsonify({
            "parsed": len(apple_notes),
            "imported": len(synced_notes),
            "notes": synced_notes,
            "errors": errors
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route("/sync/import/stream", methods=["GET"])
def import_notes_stream():
    """Stream import notes from Apple Notes to Backboard.io via Server-Sent Events"""
    source = request.args.get('source', 'apple')
    first_n = request.args.get('first_n', type=int)
    last_n = request.args.get('last_n', type=int)
    
    def generate():
        try:
            # Send initial status
            yield f"data: {json.dumps({'type': 'start', 'message': 'Starting import...'})}\n\n"
            
            # Read Apple Notes
            reader = AppleNotesReader()
            force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
            if force_refresh:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Reading notes from Apple Notes (cache refresh)...'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'status', 'message': 'Reading notes from Apple Notes (using cache if available)...'})}\n\n"
            apple_notes = reader.get_all_notes_cached(force_refresh=force_refresh)
            
            # Apply limits if specified
            original_count = len(apple_notes)
            if first_n is not None and first_n > 0:
                apple_notes = apple_notes[:first_n]
                yield f"data: {json.dumps({'type': 'status', 'message': f'Limiting to first {first_n} notes (out of {original_count} total)'})}\n\n"
            elif last_n is not None and last_n > 0:
                apple_notes = apple_notes[-last_n:]
                yield f"data: {json.dumps({'type': 'status', 'message': f'Limiting to last {last_n} notes (out of {original_count} total)'})}\n\n"
            
            total = len(apple_notes)
            
            yield f"data: {json.dumps({'type': 'progress', 'total': total, 'current': 0, 'message': f'Found {total} notes to import'})}\n\n"
            
            # Sync to Backboard.io
            client = get_backboard_client()
            synced_count = 0
            error_count = 0
            
            for idx, note in enumerate(apple_notes, 1):
                try:
                    synced_note = client.sync_note(note)
                    if synced_note:
                        synced_count += 1
                        # Use model_dump with mode='json' to properly serialize datetime objects
                        note_dict = synced_note.model_dump(mode='json')
                        yield f"data: {json.dumps({'type': 'note', 'note': note_dict, 'current': idx, 'total': total, 'imported': synced_count, 'errors': error_count})}\n\n"
                    else:
                        error_count += 1
                        yield f"data: {json.dumps({'type': 'error', 'note': {'id': note.id, 'title': note.title}, 'error': 'Failed to sync', 'current': idx, 'total': total, 'imported': synced_count, 'errors': error_count})}\n\n"
                except Exception as e:
                    error_count += 1
                    yield f"data: {json.dumps({'type': 'error', 'note': {'id': note.id, 'title': note.title}, 'error': str(e), 'current': idx, 'total': total, 'imported': synced_count, 'errors': error_count})}\n\n"
                
                # Send progress update
                yield f"data: {json.dumps({'type': 'progress', 'current': idx, 'total': total, 'imported': synced_count, 'errors': error_count})}\n\n"
            
            # Invalidate assistant cache since memory counts may have changed
            invalidate_assistant_cache()
            
            # Send completion
            yield f"data: {json.dumps({'type': 'complete', 'total': total, 'imported': synced_count, 'errors': error_count, 'message': f'Import complete: {synced_count} imported, {error_count} errors'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'message': f'Import failed: {str(e)}'})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@api_bp.route("/sync/cache/invalidate", methods=["POST"])
def invalidate_cache():
    """Invalidate the notes cache"""
    try:
        from app.services.cache import NotesCache
        cache = NotesCache()
        cache.invalidate_cache()
        return jsonify({"message": "Cache invalidated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
