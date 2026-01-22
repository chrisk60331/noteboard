import re
from typing import List
from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """Represents a single chunk of text"""
    content: str = Field(..., description="The chunk content")
    part_number: int = Field(..., description="Part number (1-indexed)")
    total_parts: int = Field(..., description="Total number of parts")


class SemanticChunker:
    """Semantic chunking service that splits text at meaningful boundaries"""
    
    def __init__(self, max_chunk_size: int = 3800):
        """
        Initialize the semantic chunker
        
        Args:
            max_chunk_size: Maximum size in bytes for each chunk (default 3800, leaving room for headers)
        """
        self.max_chunk_size = max_chunk_size
    
    def chunk_text(self, text: str, title: str = "") -> List[Chunk]:
        """
        Split text into semantic chunks
        
        Args:
            text: The text to chunk
            title: Optional title to include in chunk headers
            
        Returns:
            List of Chunk objects
        """
        if not text:
            return []
        
        # Calculate header overhead (title + part indicator)
        # Format: "{title}\n\n{content}\n\n[Part {n}/{total}]"
        header_overhead = len(title.encode('utf-8')) + 50  # Approximate overhead for part indicator
        
        # First, try splitting by paragraphs (double newlines)
        paragraphs = self._split_by_paragraphs(text)
        
        chunks = []
        current_chunk_parts = []
        current_size = 0
        
        for paragraph in paragraphs:
            para_size = len(paragraph.encode('utf-8'))
            
            # If single paragraph exceeds limit, split by sentences
            if para_size > (self.max_chunk_size - header_overhead):
                # Split this paragraph by sentences
                sentences = self._split_by_sentences(paragraph)
                
                for sentence in sentences:
                    sent_size = len(sentence.encode('utf-8'))
                    
                    # If even a sentence is too large, split by characters (fallback)
                    if sent_size > (self.max_chunk_size - header_overhead):
                        char_chunks = self._split_by_characters(
                            sentence, 
                            self.max_chunk_size - header_overhead
                        )
                        for char_chunk in char_chunks:
                            if current_size + len(char_chunk.encode('utf-8')) > (self.max_chunk_size - header_overhead):
                                # Save current chunk (total_parts will be updated later)
                                if current_chunk_parts:
                                    chunks.append(self._create_chunk(current_chunk_parts, title, len(chunks) + 1, 0))
                                    current_chunk_parts = []
                                    current_size = 0
                            
                            current_chunk_parts.append(char_chunk)
                            current_size += len(char_chunk.encode('utf-8'))
                    else:
                        # Check if adding this sentence would exceed limit
                        if current_size + sent_size > (self.max_chunk_size - header_overhead):
                            # Save current chunk (total_parts will be updated later)
                            if current_chunk_parts:
                                chunks.append(self._create_chunk(current_chunk_parts, title, len(chunks) + 1, 0))
                                current_chunk_parts = []
                                current_size = 0
                        
                        current_chunk_parts.append(sentence)
                        current_size += sent_size
            else:
                # Check if adding this paragraph would exceed limit
                if current_size + para_size > (self.max_chunk_size - header_overhead):
                    # Save current chunk (total_parts will be updated later)
                    if current_chunk_parts:
                        chunks.append(self._create_chunk(current_chunk_parts, title, len(chunks) + 1, 0))
                        current_chunk_parts = []
                        current_size = 0
                
                current_chunk_parts.append(paragraph)
                current_size += para_size
        
        # Add remaining chunk
        if current_chunk_parts:
            chunks.append(self._create_chunk(current_chunk_parts, title, len(chunks) + 1, 0))
        
        # Update total_parts for all chunks
        total_parts = len(chunks) if chunks else 1
        
        # If only one chunk, return it without part indicator
        if total_parts == 1:
            return chunks if chunks else [Chunk(content=text, part_number=1, total_parts=1)]
        
        # Recreate chunks with correct total_parts
        final_chunks = []
        for i, chunk in enumerate(chunks):
            # Rebuild content with correct total_parts
            content = chunk.content
            # Remove old part indicator if present
            content = re.sub(r'\n\n\[Part \d+/\d+\]$', '', content)
            # Add correct part indicator
            content += f"\n\n[Part {i + 1}/{total_parts}]"
            final_chunks.append(Chunk(
                content=content,
                part_number=i + 1,
                total_parts=total_parts
            ))
        
        return final_chunks
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text by paragraphs (double newlines)"""
        paragraphs = re.split(r'\n\s*\n', text)
        # Filter out empty paragraphs and preserve single newlines within paragraphs
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """Split text by sentences (periods, exclamation marks, question marks)"""
        # Pattern to match sentence endings followed by whitespace or end of string
        pattern = r'([.!?]+)\s+'
        sentences = re.split(pattern, text)
        
        # Recombine sentences with their punctuation
        result = []
        i = 0
        while i < len(sentences):
            if i + 1 < len(sentences):
                # Combine sentence with its punctuation
                combined = sentences[i] + sentences[i + 1]
                result.append(combined.strip())
                i += 2
            else:
                if sentences[i].strip():
                    result.append(sentences[i].strip())
                i += 1
        
        return [s for s in result if s]
    
    def _split_by_characters(self, text: str, max_size: int) -> List[str]:
        """Fallback: split text by character count (preserves word boundaries when possible)"""
        chunks = []
        words = text.split()
        current_chunk = []
        current_size = 0
        
        for word in words:
            word_size = len(word.encode('utf-8')) + 1  # +1 for space
            if current_size + word_size > max_size:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                
                # If single word exceeds limit, split it
                if len(word.encode('utf-8')) > max_size:
                    # Split word character by character
                    word_bytes = word.encode('utf-8')
                    for i in range(0, len(word_bytes), max_size):
                        chunk_bytes = word_bytes[i:i + max_size]
                        chunks.append(chunk_bytes.decode('utf-8', errors='ignore'))
                else:
                    current_chunk.append(word)
                    current_size = word_size
            else:
                current_chunk.append(word)
                current_size += word_size
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks if chunks else [text]
    
    def _create_chunk(self, parts: List[str], title: str, part_number: int, total_parts: int = 0) -> Chunk:
        """Create a Chunk object from text parts"""
        content = '\n\n'.join(parts)
        
        # Add title and part indicator (total_parts will be updated after all chunks are created)
        if title:
            chunk_content = f"{title}\n\n{content}"
        else:
            chunk_content = content
        
        # Add part indicator only if we have total_parts
        if total_parts > 1:
            chunk_content += f"\n\n[Part {part_number}/{total_parts}]"
        
        return Chunk(
            content=chunk_content,
            part_number=part_number,
            total_parts=total_parts
        )
