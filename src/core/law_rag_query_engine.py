


from core.hierarchical_rag_system import HierarchicalRAGSystem
from typing import List, Dict, Any, Optional, Tuple


class LegalRAGQueryEngine:
  """Query engine với advanced features"""
  
  def __init__(self, rag_system: HierarchicalRAGSystem):
    self.rag_system = rag_system


  def answer_question(
    self,
    question: str,
    context_limit: int = 5000
  ) -> Dict:
    """Trả lời câu hỏi dựa trên RAG results"""
    
    # Search relevant documents
    search_results = self.rag_system.search(question, top_k=10)

    # Build context từ top results
    context_chunks = []
    current_length = 0

    for result in search_results['results']:
      chunk_text = result['content']
      chunk_length = len(chunk_text)
      
      if current_length + chunk_length <= context_limit:
        context_chunks.append({
          'text': chunk_text,
          'source': f"{result['source_info']['folder']}/{result['source_info']['file']}",
          'relevance': result['relevance_score']
        })
        current_length += chunk_length
      else:
        break
    
    # Prepare response
    response = {
      'question': question,
      'context_used': context_chunks,
      'sources': list(set([chunk['source'] for chunk in context_chunks])),
      'total_context_length': current_length,
      'search_metadata': {
        'total_results_found': search_results['total_results'],
        'chunks_used_for_context': len(context_chunks)
      }
    }
    
    return response
    
  
  def get_related_documents(self, document_id: str, top_k: int = 5) -> List[Dict]:
    """Tìm documents liên quan đến một document cụ thể"""
    
    # Lấy document hiện tại
    current_doc = self.rag_system.document_collection.get(
      ids=[document_id],
      include=['documents', 'metadatas']
    )
    
    if not current_doc['documents']:
      return []
    
    # Search bằng content của document
    current_text = current_doc['documents'][0]
    folder_id = current_doc['metadatas'][0]['folder_id']
    
    # Search trong cùng folder và folders liên quan
    related_results = self.rag_system.search(
      query=current_text[:500],  # Use first 500 chars as query
      top_k=top_k + 5
    )
    
    # Filter out chính document đó
    filtered_results = [
      result for result in related_results['results']
      if result['metadata']['document_id'] != current_doc['metadatas'][0]['document_id']
    ]
    
    return filtered_results[:top_k]