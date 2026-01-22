from typing import List, Optional
from datetime import datetime
from app.models.note import Note, NoteCreate, NoteUpdate
from app.services.chunking import SemanticChunker

try:
    from backboard_sdk import BackboardClient as SDKClient
    SDK_AVAILABLE = True
except ImportError:
    try:
        from backboard import BackboardClient as SDKClient
        SDK_AVAILABLE = True
    except ImportError:
        SDK_AVAILABLE = False

class BackboardClient:
    """Client for interacting with Backboard.io API using backboard-sdk"""
    
    def __init__(self, api_key: str, base_url: str = "https://app.backboard.io/api", assistant_id: Optional[str] = None):
        if not SDK_AVAILABLE:
            raise RuntimeError("backboard-sdk is not installed. Please install it with: pip install backboard-sdk")
        
        # Initialize SDK client
        # Try common initialization patterns
        try:
            # Pattern 1: BackboardClient(api_key=..., base_url=...)
            self.sdk_client = SDKClient(api_key=api_key, base_url=base_url)
            
        except TypeError:
            try:
                # Pattern 2: BackboardClient(api_key, base_url)
                self.sdk_client = SDKClient(api_key, base_url)
                
            except TypeError:
                try:
                    # Pattern 3: Just api_key
                    self.sdk_client = SDKClient(api_key)
                    if hasattr(self.sdk_client, 'set_base_url'):
                        self.sdk_client.set_base_url(base_url)
                    
                except Exception as e:
                    
                    raise RuntimeError(f"Failed to initialize backboard-sdk: {str(e)}")
        
        # Check SDK client methods
        has_create_note = hasattr(self.sdk_client, 'create_note')
        has_notes_create = hasattr(self.sdk_client, 'notes') and hasattr(self.sdk_client.notes, 'create') if hasattr(self.sdk_client, 'notes') else False
        has_memory_create = hasattr(self.sdk_client, 'memory') and hasattr(self.sdk_client.memory, 'create') if hasattr(self.sdk_client, 'memory') else False
        
        
        self.api_key = api_key
        self.base_url = base_url
        self._default_assistant_id = assistant_id  # Use provided assistant_id or None
        self._default_thread_id = None  # Cache thread_id for chat sessions
        self._current_assistant_id = None  # Track current assistant for thread management
        self.chunker = SemanticChunker(max_chunk_size=3800)
    
    def _get_or_create_default_assistant(self) -> str:
        """Get or create a default assistant for storing notes"""
        # If assistant_id was provided during initialization, use it
        if self._default_assistant_id:
            return self._default_assistant_id
        
        # Try to list existing assistants and find one named "Notes" or create one
        # SDK methods are async, so we need to use asyncio to run them
        # Use a new event loop each time to avoid "Event loop is closed" errors
        import asyncio
        
        try:
            if hasattr(self.sdk_client, 'list_assistants'):
                
                # Run async coroutine synchronously - create new event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                assistants = loop.run_until_complete(self.sdk_client.list_assistants())
                
                
                # Look for an assistant named "Notes"
                if isinstance(assistants, list):
                    for assistant in assistants:
                        assistant_dict = assistant if isinstance(assistant, dict) else assistant.__dict__ if hasattr(assistant, '__dict__') else {}
                        name = assistant_dict.get('name', '') if isinstance(assistant_dict, dict) else getattr(assistant, 'name', '')
                        
                        if name == 'Notes':
                            
                            # The key is "assistant_id" not "id"!
                            assistant_id = assistant_dict.get('assistant_id', '') if isinstance(assistant_dict, dict) else getattr(assistant, 'assistant_id', '')
                            if assistant_id:
                                self._default_assistant_id = str(assistant_id)
                                return self._default_assistant_id
        except Exception as e:
            pass
        
        # Create a new assistant named "Notes"
        try:
            if hasattr(self.sdk_client, 'create_assistant'):
                # Run async coroutine synchronously - reuse or create event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                assistant = loop.run_until_complete(self.sdk_client.create_assistant(name="Notes"))
                assistant_dict = assistant if isinstance(assistant, dict) else assistant.__dict__ if hasattr(assistant, '__dict__') else {}
                # The key is "assistant_id" not "id"!
                assistant_id = assistant_dict.get('assistant_id', '') if isinstance(assistant_dict, dict) else getattr(assistant, 'assistant_id', '')
                if assistant_id:
                    self._default_assistant_id = str(assistant_id)
                    return self._default_assistant_id
        except Exception as e:
            raise RuntimeError(f"Failed to create default assistant: {str(e)}")
        
        raise RuntimeError("Could not get or create default assistant")
    
    def create_note(self, note: NoteCreate) -> Note:
        """Create a new note in Backboard.io"""
        
        
        try:
            # Check available methods
            has_create_note = hasattr(self.sdk_client, 'create_note')
            has_notes = hasattr(self.sdk_client, 'notes')
            has_notes_create = has_notes and hasattr(self.sdk_client.notes, 'create') if has_notes else False
            has_memory = hasattr(self.sdk_client, 'memory')
            has_memory_create = has_memory and hasattr(self.sdk_client.memory, 'create') if has_memory else False
            
            
            # Try common SDK method patterns - SDK uses add_memory for creating memories
            has_add_memory = hasattr(self.sdk_client, 'add_memory')
            
            
            if has_add_memory:
                # Get or create default assistant
                assistant_id = self._get_or_create_default_assistant()
                
                # Combine title and content
                combined_content = f"{note.title}\n\n{note.content}" if note.title else note.content
                
                # Use semantic chunking to split large content
                chunks = self.chunker.chunk_text(combined_content, title=note.title)
                
                # Call add_memory with assistant_id and content (signature: add_memory(assistant_id, content, metadata=None))
                # SDK methods are async, so we need to use asyncio to run them
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Create memories for all chunks
                results = []
                for chunk in chunks:
                    memory_result = loop.run_until_complete(
                        self.sdk_client.add_memory(assistant_id, chunk.content)
                    )
                    results.append(memory_result)
                
                # Return the first chunk as the primary note
                result = results[0] if results else None
                
            elif has_create_note:
                
                result = self.sdk_client.create_note(title=note.title, content=note.content)
            elif has_notes_create:
                
                result = self.sdk_client.notes.create(title=note.title, content=note.content)
            elif has_memory_create:
                
                result = self.sdk_client.memory.create(title=note.title, content=note.content)
            else:
                
                raise RuntimeError("SDK client doesn't have create_note or add_memory method")
            
            
            
            # Convert SDK result to our Note model
            return self._sdk_result_to_note(result)
        except Exception as e:
            
            raise RuntimeError(f"Failed to create note: {str(e)}")
    
    def get_note(self, note_id: str) -> Optional[Note]:
        """Get a note by ID"""
        try:
            
            
            # SDK uses get_memory for retrieving memories (requires assistant_id and memory_id)
            # Note: The note_id from Apple Notes won't match memory IDs, so we can't use this for sync
            # We'll need to search memories instead or store a mapping
            # For now, always return None since we can't match Apple Notes IDs to memory IDs
            result = None
            
            return self._sdk_result_to_note(result)
        except Exception as e:
            
            return None
    
    def list_notes(self) -> List[Note]:
        """List all notes"""
        try:
            
            
            # SDK uses get_memories for listing memories (requires assistant_id)
            assistant_id = self._get_or_create_default_assistant()
            if hasattr(self.sdk_client, 'get_memories'):
                # SDK methods are async
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                results = loop.run_until_complete(self.sdk_client.get_memories(assistant_id))
                
                # get_memories returns MemoriesListResponse object - need to extract the actual memories list
                # Check common attributes: memories, data, items, results
                if hasattr(results, 'memories'):
                    results = results.memories
                    
                elif hasattr(results, 'data'):
                    results = results.data
                    
                elif hasattr(results, 'items'):
                    results = results.items
                    
                elif isinstance(results, tuple) and len(results) > 0:
                    # Extract the actual list of memories from the tuple
                    results = results[0]
                    
            elif hasattr(self.sdk_client, 'list_notes'):
                results = self.sdk_client.list_notes()
            elif hasattr(self.sdk_client, 'notes') and hasattr(self.sdk_client.notes, 'list'):
                results = self.sdk_client.notes.list()
            elif hasattr(self.sdk_client, 'memory') and hasattr(self.sdk_client.memory, 'list'):
                results = self.sdk_client.memory.list()
            else:
                return []
            
            notes = []
            if results:
                for item in results:
                    
                    note = self._sdk_result_to_note(item)
                    notes.append(note)
            
            
            
            return notes
        except Exception as e:
            
            return []
    
    def update_note(self, note_id: str, note_update: NoteUpdate) -> Optional[Note]:
        """Update an existing note"""
        data = {}
        if note_update.title is not None:
            data["title"] = note_update.title
        if note_update.content is not None:
            data["content"] = note_update.content
        
        if not data:
            return self.get_note(note_id)
        
        try:
            
            
            # SDK uses update_memory for updating memories
            # Note: note_id from Apple Notes won't match memory_id in Backboard
            # Since we can't match IDs, treat update as create
            if hasattr(self.sdk_client, 'add_memory'):
                
                # Combine title and content into a single content string
                content = data.get('content', '')
                title = data.get('title', '')
                combined_content = f"{title}\n\n{content}" if title else content
                assistant_id = self._get_or_create_default_assistant()
                
                # Use semantic chunking to split large content
                chunks = self.chunker.chunk_text(combined_content, title=title)
                
                # SDK methods are async
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Create memories for all chunks
                results = []
                for chunk in chunks:
                    memory_result = loop.run_until_complete(
                        self.sdk_client.add_memory(assistant_id, chunk.content)
                    )
                    results.append(memory_result)
                
                # Return the first chunk as the primary note
                result = results[0] if results else None
                
            elif hasattr(self.sdk_client, 'update_note'):
                result = self.sdk_client.update_note(note_id, **data)
            elif hasattr(self.sdk_client, 'notes') and hasattr(self.sdk_client.notes, 'update'):
                result = self.sdk_client.notes.update(note_id, **data)
            elif hasattr(self.sdk_client, 'memory') and hasattr(self.sdk_client.memory, 'update'):
                result = self.sdk_client.memory.update(note_id, **data)
            else:
                return None
            
            return self._sdk_result_to_note(result)
        except Exception as e:
            
            return None
    
    def delete_note(self, note_id: str) -> bool:
        """Delete a note"""
        try:
            # SDK uses delete_memory for deleting memories (async method, requires memory_id parameter)
            if hasattr(self.sdk_client, 'delete_memory'):
                # SDK methods are async, so we need to use asyncio to run them
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Try different method signatures
                try:
                    # Try with memory_id as keyword argument: delete_memory(memory_id=...)
                    loop.run_until_complete(self.sdk_client.delete_memory(memory_id=note_id))
                except TypeError:
                    # If that fails, try with assistant_id and memory_id (matching get_memories pattern)
                    assistant_id = self._get_or_create_default_assistant()
                    try:
                        # Try positional: delete_memory(assistant_id, memory_id)
                        loop.run_until_complete(self.sdk_client.delete_memory(assistant_id, note_id))
                    except TypeError:
                        # Try keyword: delete_memory(assistant_id=..., memory_id=...)
                        loop.run_until_complete(self.sdk_client.delete_memory(assistant_id=assistant_id, memory_id=note_id))
            elif hasattr(self.sdk_client, 'delete_note'):
                self.sdk_client.delete_note(note_id)
            elif hasattr(self.sdk_client, 'notes') and hasattr(self.sdk_client.notes, 'delete'):
                self.sdk_client.notes.delete(note_id)
            elif hasattr(self.sdk_client, 'memory') and hasattr(self.sdk_client.memory, 'delete'):
                self.sdk_client.memory.delete(note_id)
            else:
                return False
            return True
        except Exception as e:
            # Re-raise the exception so the API can return the actual error message
            raise RuntimeError(f"Failed to delete note: {str(e)}")
    
    def delete_thread(self, thread_id: str) -> bool:
        """Delete a thread"""
        try:
            # SDK methods are async, so we need to use asyncio to run them
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Try different SDK method patterns for deleting threads
            if hasattr(self.sdk_client, 'delete_thread'):
                try:
                    # Try: delete_thread(thread_id=thread_id)
                    loop.run_until_complete(self.sdk_client.delete_thread(thread_id=thread_id))
                except TypeError:
                    try:
                        # Try: delete_thread(thread_id)
                        loop.run_until_complete(self.sdk_client.delete_thread(thread_id))
                    except Exception as e:
                        raise RuntimeError(f"Failed to delete thread: {str(e)}")
            elif hasattr(self.sdk_client, 'threads') and hasattr(self.sdk_client.threads, 'delete'):
                try:
                    # Try: threads.delete(thread_id=thread_id)
                    loop.run_until_complete(self.sdk_client.threads.delete(thread_id=thread_id))
                except TypeError:
                    try:
                        # Try: threads.delete(thread_id)
                        loop.run_until_complete(self.sdk_client.threads.delete(thread_id))
                    except Exception as e:
                        raise RuntimeError(f"Failed to delete thread: {str(e)}")
            else:
                return False
            return True
        except Exception as e:
            # Re-raise the exception so the API can return the actual error message
            raise RuntimeError(f"Failed to delete thread: {str(e)}")
    
    def _get_or_create_thread(self, assistant_id: str) -> str:
        """Get or create a thread for the assistant"""
        # Return cached thread_id if available
        if self._default_thread_id:
            return self._default_thread_id
        
        # SDK methods are async, so we need to use asyncio to run them
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Create a new thread for the assistant
        if hasattr(self.sdk_client, 'create_thread'):
            try:
                # Try: create_thread(assistant_id)
                thread = loop.run_until_complete(self.sdk_client.create_thread(assistant_id))
            except TypeError:
                # Try: create_thread(assistant_id=assistant_id)
                thread = loop.run_until_complete(self.sdk_client.create_thread(assistant_id=assistant_id))
            
            # Extract thread_id from the result
            if isinstance(thread, dict):
                thread_id = thread.get('thread_id') or thread.get('id', '')
            elif hasattr(thread, 'thread_id'):
                thread_id = thread.thread_id
            elif hasattr(thread, 'id'):
                thread_id = thread.id
            else:
                raise RuntimeError("Could not extract thread_id from create_thread response")
            
            if thread_id:
                self._default_thread_id = str(thread_id)
                return self._default_thread_id
        
        raise RuntimeError("Could not create thread for assistant")
    
    def get_memory_count(self, assistant_id: str) -> int:
        """Get the number of memories for a specific assistant"""
        try:
            if hasattr(self.sdk_client, 'get_memories'):
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                results = loop.run_until_complete(self.sdk_client.get_memories(assistant_id))
                
                # Extract the actual list of memories
                if hasattr(results, 'memories'):
                    results = results.memories
                elif hasattr(results, 'data'):
                    results = results.data
                elif hasattr(results, 'items'):
                    results = results.items
                elif isinstance(results, tuple) and len(results) > 0:
                    results = results[0]
                
                if isinstance(results, list):
                    return len(results)
                return 0
        except Exception as e:
            return 0
    
    def list_threads(self, assistant_id: Optional[str] = None, search: Optional[str] = None) -> List[dict]:
        """List all threads for an assistant
        
        Args:
            assistant_id: Optional assistant ID to filter threads
            search: Optional search query for filtering threads (future: will search thread content)
        """
        try:
            # Get assistant_id (use provided one or default)
            if not assistant_id:
                assistant_id = self._get_or_create_default_assistant()
            
            # SDK methods are async, so we need to use asyncio to run them
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            threads = []
            
            # Try different SDK method patterns for listing threads
            # Always use keyword arguments to avoid parameter confusion (e.g., skip vs assistant_id)
            if hasattr(self.sdk_client, 'list_threads'):
                try:
                    # Try: list_threads(assistant_id=assistant_id) - keyword argument only
                    if assistant_id:
                        results = loop.run_until_complete(self.sdk_client.list_threads(assistant_id=assistant_id))
                    else:
                        results = loop.run_until_complete(self.sdk_client.list_threads())
                except (TypeError, ValueError) as e:
                    # If keyword argument fails, try without assistant_id filter
                    try:
                        results = loop.run_until_complete(self.sdk_client.list_threads())
                    except Exception:
                        import logging
                        logging.error(f"Failed to call list_threads: {str(e)}")
                        raise
            elif hasattr(self.sdk_client, 'threads') and hasattr(self.sdk_client.threads, 'list'):
                try:
                    # Try: threads.list(assistant_id=assistant_id) - keyword argument only
                    if assistant_id:
                        results = loop.run_until_complete(self.sdk_client.threads.list(assistant_id=assistant_id))
                    else:
                        results = loop.run_until_complete(self.sdk_client.threads.list())
                except (TypeError, ValueError) as e:
                    # If keyword argument fails, try without assistant_id filter
                    try:
                        results = loop.run_until_complete(self.sdk_client.threads.list())
                    except Exception:
                        import logging
                        logging.error(f"Failed to call threads.list: {str(e)}")
                        raise
            else:
                import logging
                logging.warning("SDK client doesn't have list_threads or threads.list methods")
                return []
            
            # Extract the actual list of threads
            if hasattr(results, 'threads'):
                results = results.threads
            elif hasattr(results, 'data'):
                results = results.data
            elif hasattr(results, 'items'):
                results = results.items
            elif isinstance(results, tuple) and len(results) > 0:
                results = results[0]
            
            # Convert threads to list of dicts
            import logging
            if isinstance(results, list):
                for thread in results:
                    if isinstance(thread, dict):
                        thread_dict = thread
                    elif hasattr(thread, '__dict__'):
                        thread_dict = thread.__dict__.copy()
                        # Also check direct attributes
                        for attr in ['preview', 'preview_text', 'first_message', 'last_message', 'messages']:
                            if hasattr(thread, attr):
                                thread_dict[attr] = getattr(thread, attr)
                    else:
                        continue
                    
                    thread_id = thread_dict.get('thread_id') or thread_dict.get('id', '')
                    created_at = thread_dict.get('created_at') or thread_dict.get('created_at', '')
                    updated_at = thread_dict.get('updated_at') or thread_dict.get('updated_at', '')
                    
                    # Try to get preview text from thread object if available
                    preview_text = None
                    # Check various possible fields for preview/message content
                    if 'preview' in thread_dict and thread_dict.get('preview'):
                        preview_text = str(thread_dict.get('preview'))
                    elif 'preview_text' in thread_dict and thread_dict.get('preview_text'):
                        preview_text = str(thread_dict.get('preview_text'))
                    elif 'first_message' in thread_dict:
                        first_msg = thread_dict.get('first_message')
                        if isinstance(first_msg, dict):
                            preview_text = first_msg.get('content') or first_msg.get('text') or first_msg.get('message') or first_msg.get('body', '')
                        elif isinstance(first_msg, str):
                            preview_text = first_msg
                    elif 'last_message' in thread_dict:
                        last_msg = thread_dict.get('last_message')
                        if isinstance(last_msg, dict):
                            preview_text = last_msg.get('content') or last_msg.get('text') or last_msg.get('message') or last_msg.get('body', '')
                        elif isinstance(last_msg, str):
                            preview_text = last_msg
                    elif 'messages' in thread_dict and isinstance(thread_dict.get('messages'), list):
                        # Check if messages array is in thread object
                        messages = thread_dict.get('messages')
                        for msg in messages:
                            if isinstance(msg, dict):
                                role = msg.get('role', '').lower()
                                if role == 'user':
                                    preview_text = msg.get('content') or msg.get('text') or msg.get('message') or msg.get('body', '')
                                    break
                            elif hasattr(msg, 'role') and (hasattr(msg, 'content') or hasattr(msg, 'text')):
                                if getattr(msg, 'role', '').lower() == 'user':
                                    preview_text = getattr(msg, 'content', '') or getattr(msg, 'text', '') or getattr(msg, 'message', '')
                                    break
                    
                    # Truncate preview if found
                    if preview_text:
                        preview_text = str(preview_text).strip()
                        if len(preview_text) > 100:
                            preview_text = preview_text[:100] + '...'
                    
                    threads.append({
                        'thread_id': str(thread_id),
                        'created_at': created_at,
                        'updated_at': updated_at,
                        'preview_text': preview_text
                    })
            
            # Fetch first message for each thread if preview_text is not available
            # Only fetch for threads without preview_text to avoid unnecessary API calls
            import logging
            for thread in threads:
                if not thread.get('preview_text'):
                    try:
                        preview = self._get_thread_preview(thread['thread_id'], loop)
                        if preview:
                            thread['preview_text'] = preview
                        else:
                            logging.debug(f"No preview found for thread {thread['thread_id']}")
                    except Exception as e:
                        logging.debug(f"Could not fetch preview for thread {thread['thread_id']}: {str(e)}")
                        # Continue without preview if fetch fails
                        pass
            
            # Apply search filter if provided (currently filters by thread_id, can be extended for content search)
            if search:
                search_lower = search.lower()
                threads = [t for t in threads if search_lower in t.get('thread_id', '').lower() or search_lower in (t.get('preview_text') or '').lower()]
            
            return threads
        except Exception as e:
            import logging
            logging.error(f"Error listing threads: {str(e)}", exc_info=True)
            raise  # Re-raise to let API handle it properly
    
    def _get_thread_preview(self, thread_id: str, loop) -> Optional[str]:
        """Get the first user message from a thread as preview text"""
        import logging
        try:
            # Try to get messages from the thread using various SDK method patterns
            messages = None
            
            # Pattern 1: get_thread_messages
            if hasattr(self.sdk_client, 'get_thread_messages'):
                try:
                    messages = loop.run_until_complete(self.sdk_client.get_thread_messages(thread_id=thread_id))
                except (TypeError, AttributeError):
                    try:
                        messages = loop.run_until_complete(self.sdk_client.get_thread_messages(thread_id))
                    except Exception as e:
                        logging.debug(f"get_thread_messages failed: {e}")
            
            # Pattern 2: threads.get_messages
            if messages is None and hasattr(self.sdk_client, 'threads') and hasattr(self.sdk_client.threads, 'get_messages'):
                try:
                    messages = loop.run_until_complete(self.sdk_client.threads.get_messages(thread_id=thread_id))
                except (TypeError, AttributeError):
                    try:
                        messages = loop.run_until_complete(self.sdk_client.threads.get_messages(thread_id))
                    except Exception as e:
                        logging.debug(f"threads.get_messages failed: {e}")
            
            # Pattern 3: list_messages
            if messages is None and hasattr(self.sdk_client, 'list_messages'):
                try:
                    messages = loop.run_until_complete(self.sdk_client.list_messages(thread_id=thread_id))
                except (TypeError, AttributeError):
                    try:
                        messages = loop.run_until_complete(self.sdk_client.list_messages(thread_id))
                    except Exception as e:
                        logging.debug(f"list_messages failed: {e}")
            
            # Pattern 4: get_thread (might return thread with messages)
            if messages is None and hasattr(self.sdk_client, 'get_thread'):
                try:
                    thread_obj = loop.run_until_complete(self.sdk_client.get_thread(thread_id=thread_id))
                    if thread_obj:
                        if isinstance(thread_obj, dict):
                            messages = thread_obj.get('messages', [])
                        elif hasattr(thread_obj, 'messages'):
                            messages = thread_obj.messages
                except (TypeError, AttributeError):
                    try:
                        thread_obj = loop.run_until_complete(self.sdk_client.get_thread(thread_id))
                        if thread_obj:
                            if isinstance(thread_obj, dict):
                                messages = thread_obj.get('messages', [])
                            elif hasattr(thread_obj, 'messages'):
                                messages = thread_obj.messages
                    except Exception as e:
                        logging.debug(f"get_thread failed: {e}")
            
            if messages is None:
                return None
            
            # Extract messages list if wrapped
            if hasattr(messages, 'messages'):
                messages = messages.messages
            elif hasattr(messages, 'data'):
                messages = messages.data
            elif hasattr(messages, 'items'):
                messages = messages.items
            elif isinstance(messages, tuple) and len(messages) > 0:
                messages = messages[0]
            
            # Find first user message
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict):
                        msg_dict = msg
                    elif hasattr(msg, '__dict__'):
                        msg_dict = msg.__dict__
                    else:
                        continue
                    
                    role = msg_dict.get('role', '').lower()
                    content = msg_dict.get('content', '') or msg_dict.get('text', '') or msg_dict.get('message', '') or msg_dict.get('body', '')
                    
                    # Return first user message as preview
                    if role == 'user' and content:
                        # Truncate to reasonable length
                        preview = str(content).strip()
                        if len(preview) > 100:
                            preview = preview[:100] + '...'
                        return preview
            
            return None
        except Exception as e:
            import logging
            logging.debug(f"Could not get preview for thread {thread_id}: {str(e)}")
            return None
    
    def get_thread_messages(self, thread_id: str) -> List[dict]:
        """Get all messages from a thread
        
        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        import logging
        import asyncio
        try:
            # SDK methods are async, so we need to use asyncio to run them
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Try to get messages from the thread using various SDK method patterns
            messages = None
            
            # Pattern 1: get_thread_messages
            if hasattr(self.sdk_client, 'get_thread_messages'):
                try:
                    messages = loop.run_until_complete(self.sdk_client.get_thread_messages(thread_id=thread_id))
                except (TypeError, AttributeError):
                    try:
                        messages = loop.run_until_complete(self.sdk_client.get_thread_messages(thread_id))
                    except Exception as e:
                        logging.debug(f"get_thread_messages failed: {e}")
            
            # Pattern 2: threads.get_messages
            if messages is None and hasattr(self.sdk_client, 'threads') and hasattr(self.sdk_client.threads, 'get_messages'):
                try:
                    messages = loop.run_until_complete(self.sdk_client.threads.get_messages(thread_id=thread_id))
                except (TypeError, AttributeError):
                    try:
                        messages = loop.run_until_complete(self.sdk_client.threads.get_messages(thread_id))
                    except Exception as e:
                        logging.debug(f"threads.get_messages failed: {e}")
            
            # Pattern 3: list_messages
            if messages is None and hasattr(self.sdk_client, 'list_messages'):
                try:
                    messages = loop.run_until_complete(self.sdk_client.list_messages(thread_id=thread_id))
                except (TypeError, AttributeError):
                    try:
                        messages = loop.run_until_complete(self.sdk_client.list_messages(thread_id))
                    except Exception as e:
                        logging.debug(f"list_messages failed: {e}")
            
            # Pattern 4: get_thread (might return thread with messages)
            if messages is None and hasattr(self.sdk_client, 'get_thread'):
                try:
                    thread_obj = loop.run_until_complete(self.sdk_client.get_thread(thread_id=thread_id))
                    if thread_obj:
                        if isinstance(thread_obj, dict):
                            messages = thread_obj.get('messages', [])
                        elif hasattr(thread_obj, 'messages'):
                            messages = thread_obj.messages
                except (TypeError, AttributeError):
                    try:
                        thread_obj = loop.run_until_complete(self.sdk_client.get_thread(thread_id))
                        if thread_obj:
                            if isinstance(thread_obj, dict):
                                messages = thread_obj.get('messages', [])
                            elif hasattr(thread_obj, 'messages'):
                                messages = thread_obj.messages
                    except Exception as e:
                        logging.debug(f"get_thread failed: {e}")
            
            if messages is None:
                return []
            
            # Extract messages list if wrapped
            if hasattr(messages, 'messages'):
                messages = messages.messages
            elif hasattr(messages, 'data'):
                messages = messages.data
            elif hasattr(messages, 'items'):
                messages = messages.items
            elif isinstance(messages, tuple) and len(messages) > 0:
                messages = messages[0]
            
            # Convert messages to list of dicts
            result = []
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict):
                        msg_dict = msg
                    elif hasattr(msg, '__dict__'):
                        msg_dict = msg.__dict__
                    else:
                        continue
                    
                    role = msg_dict.get('role', '').lower()
                    content = msg_dict.get('content', '') or msg_dict.get('text', '') or msg_dict.get('message', '') or msg_dict.get('body', '')
                    
                    if content:  # Only include messages with content
                        result.append({
                            'role': role,
                            'content': str(content).strip()
                        })
            
            return result
        except Exception as e:
            import logging
            logging.error(f"Error getting thread messages: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to get thread messages: {str(e)}")
    
    def chat(self, message: str, context_notes: Optional[List[str]] = None, assistant_id: Optional[str] = None, thread_id: Optional[str] = None) -> dict:
        """Send a chat message to the LLM with optional note context
        
        Args:
            message: The message to send
            context_notes: Optional list of note IDs for context
            assistant_id: Optional assistant ID (uses default if not provided)
            thread_id: Optional thread ID to continue existing thread (creates new if not provided)
        
        Returns:
            dict with 'response' and 'thread_id' keys
        """
        try:
            # Get assistant_id (use provided one or default)
            if not assistant_id:
                assistant_id = self._get_or_create_default_assistant()
            
            # Use provided thread_id or get/create a thread for this assistant
            if thread_id:
                # Use the provided thread_id
                thread_id = str(thread_id)
            else:
                # Reset thread cache if assistant_id changed
                if hasattr(self, '_current_assistant_id') and self._current_assistant_id != assistant_id:
                    self._default_thread_id = None
                self._current_assistant_id = assistant_id
                thread_id = self._get_or_create_thread(assistant_id)
            
            # SDK methods are async, so we need to use asyncio to run them
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Prepare add_message parameters
            # According to the quickstart: add_message(thread_id=..., content=..., memory="Auto", stream=True)
            # memory="Auto" enables automatic memory retrieval and storage
            add_message_kwargs = {
                'thread_id': thread_id,
                'content': message,
                'memory': 'Auto',  # Enable memory - automatically searches and retrieves saved memories
                'stream': True
            }
            
            # Add optional parameters if they exist
            if context_notes:
                add_message_kwargs['context_notes'] = context_notes
            
            # Call add_message and collect streaming response
            if hasattr(self.sdk_client, 'add_message'):
                # add_message returns an async generator, need to await it first
                async def collect_response():
                    content_parts = []
                    # According to quickstart: async for chunk in await client.add_message(...)
                    stream = await self.sdk_client.add_message(**add_message_kwargs)
                    async for chunk in stream:
                        if isinstance(chunk, dict):
                            chunk_type = chunk.get('type')
                            if chunk_type == 'content_streaming':
                                content_parts.append(chunk.get('content', ''))
                            elif chunk_type == 'memory_retrieved':
                                # Memory is being retrieved - this is informational, we can ignore it
                                # or log it for debugging: memories = chunk.get('memories', [])
                                pass
                            elif chunk_type == 'message_complete':
                                break
                        elif hasattr(chunk, 'type'):
                            if chunk.type == 'content_streaming':
                                content_parts.append(getattr(chunk, 'content', ''))
                            elif chunk.type == 'memory_retrieved':
                                # Memory is being retrieved - informational
                                pass
                            elif chunk.type == 'message_complete':
                                break
                        else:
                            # If not a dict, try to extract content directly
                            if hasattr(chunk, 'content'):
                                content_parts.append(chunk.content)
                            elif isinstance(chunk, str):
                                content_parts.append(chunk)
                    return ''.join(content_parts)
                
                # Run the async collection
                response = loop.run_until_complete(collect_response())
                return {
                    'response': response if response else "No response received",
                    'thread_id': thread_id
                }
            else:
                raise RuntimeError("SDK client doesn't have add_message method")
            
        except Exception as e:
            
            raise RuntimeError(f"Chat request failed: {str(e)}")
    
    def sync_note(self, note: Note) -> Note:
        """Sync a note to Backboard.io (create or update)"""
        
        
        # Try to get existing note
        existing = self.get_note(note.id)
        
        
        if existing:
            # Update if exists
            
            result = self.update_note(
                note.id,
                NoteUpdate(title=note.title, content=note.content)
            )
            
            return result
        else:
            # Create if new
            
            result = self.create_note(
                NoteCreate(title=note.title, content=note.content)
            )
            
            return result
    
    def _sdk_result_to_note(self, result) -> Note:
        """Convert SDK result object to our Note model"""
        
        
        # Handle None case
        if result is None:
            return Note(
                id="",
                title="Untitled",
                content="",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        
        # Handle different SDK result formats
        if isinstance(result, dict):
            
            # SDK Memory objects might have memory_id instead of id, and content instead of title/content
            memory_id = result.get("memory_id") or result.get("id") or ""
            # Extract title from content if it's in the first line
            content = result.get("content", "") or result.get("data", "")
            title = result.get("title", "")
            if not title and content:
                # Try to extract title from first line of content
                lines = content.split("\n")
                first_line = lines[0].strip()
                title = first_line[:100] if first_line else "Untitled"
                # Remove the extracted title from content if it matches the first line
                # This prevents title duplication when title was combined with content during create/update
                # Compare the first 100 chars of first_line with title (since title is truncated to 100)
                if len(lines) > 1 and first_line[:100] == title:
                    # Remove first line and any following empty lines
                    remaining_lines = lines[1:]
                    while remaining_lines and not remaining_lines[0].strip():
                        remaining_lines = remaining_lines[1:]
                    content = "\n".join(remaining_lines)
                elif first_line[:100] == title:
                    # Only title, no content
                    content = ""
            
            return Note(
                id=str(memory_id),
                title=title or "Untitled",
                content=content,
                created_at=self._parse_datetime(result.get("created_at")),
                updated_at=self._parse_datetime(result.get("updated_at"))
            )
        elif hasattr(result, '__dict__'):
            # Object with attributes
            result_dict = result.__dict__
            
            memory_id = getattr(result, 'memory_id', None) or getattr(result, 'id', '')
            content = getattr(result, 'content', '') or getattr(result, 'data', '')
            title = getattr(result, 'title', '')
            if not title and content:
                # Try to extract title from first line of content
                lines = content.split("\n")
                first_line = lines[0].strip()
                title = first_line[:100] if first_line else "Untitled"
                # Remove the extracted title from content if it matches the first line
                # This prevents title duplication when title was combined with content during create/update
                # Compare the first 100 chars of first_line with title (since title is truncated to 100)
                if len(lines) > 1 and first_line[:100] == title:
                    # Remove first line and any following empty lines
                    remaining_lines = lines[1:]
                    while remaining_lines and not remaining_lines[0].strip():
                        remaining_lines = remaining_lines[1:]
                    content = "\n".join(remaining_lines)
                elif first_line[:100] == title:
                    # Only title, no content
                    content = ""
            
            return Note(
                id=str(memory_id),
                title=title or "Untitled",
                content=content,
                created_at=self._parse_datetime(getattr(result, 'created_at', None)),
                updated_at=self._parse_datetime(getattr(result, 'updated_at', None))
            )
        else:
            # Fallback - try to access as dict-like or convert to string
            
            memory_id = result.get("memory_id") if hasattr(result, 'get') else (getattr(result, 'memory_id', None) if hasattr(result, 'memory_id') else str(result))
            content = result.get("content", "") if hasattr(result, 'get') else (getattr(result, 'content', '') if hasattr(result, 'content') else "")
            title = result.get("title", "") if hasattr(result, 'get') else (getattr(result, 'title', '') if hasattr(result, 'title') else "")
            if not title and content:
                lines = content.split("\n")
                first_line = lines[0].strip()
                title = first_line[:100] if first_line else "Untitled"
                # Remove the extracted title from content if it matches the first line
                # This prevents title duplication when title was combined with content during create/update
                # Compare the first 100 chars of first_line with title (since title is truncated to 100)
                if len(lines) > 1 and first_line[:100] == title:
                    # Remove first line and any following empty lines
                    remaining_lines = lines[1:]
                    while remaining_lines and not remaining_lines[0].strip():
                        remaining_lines = remaining_lines[1:]
                    content = "\n".join(remaining_lines)
                elif first_line[:100] == title:
                    # Only title, no content
                    content = ""
            
            return Note(
                id=str(memory_id),
                title=title or "Untitled",
                content=content,
                created_at=self._parse_datetime(result.get("created_at") if hasattr(result, 'get') else (getattr(result, 'created_at', None) if hasattr(result, 'created_at') else None)),
                updated_at=self._parse_datetime(result.get("updated_at") if hasattr(result, 'get') else (getattr(result, 'updated_at', None) if hasattr(result, 'updated_at') else None))
            )
    
    def _parse_datetime(self, dt_str: Optional[str]) -> datetime:
        """Parse datetime string from API"""
        if not dt_str:
            return datetime.now()
        
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except:
            return datetime.now()
