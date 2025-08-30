

from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
from core.legal_document_processor import LegalDocumentProcessor
from typing import List, Dict, Any, Optional, Tuple
import hashlib
import os
from models.schema import FolderMetadata
from dataclasses import dataclass, asdict
from pathlib import Path



class HierarchicalRAGSystem:
  """Main RAG system with hierarchical structure support"""

  def __init__(
    self,
    data_path: str,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    persist_directory: str = "./db/chroma_db"
  ):
    
    self.data_path = data_path
    self.persist_directory = persist_directory
    
    # Initialize embeeding model
    self.embedding_model = SentenceTransformer(embedding_model)
    
    # Initialize ChromaDB
    self.chroma_client = chromadb.PersistentClient(path=persist_directory)
    
    # Collection cho different levels
    self.folder_collection = self._get_or_create_collection("folder_metadata")
    self.document_collection = self._get_or_create_collection("document_chunks")
    
    # Document processor
    self.processor = LegalDocumentProcessor()
    
    # Cache cho folder metadata
    self.folder_cache = {}
    
    # Check if DB already exists and load cache
    self._load_existing_folder_cache()
    


  def _get_or_create_collection(self, name: str):
    """Tạo hoặc lấy collection từ ChromaDB"""
    
    try:
      return self.chroma_client.get_collection(name)
    except:
      return self.chroma_client.create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"}
      )


  def _generate_folder_id(self, folder_path: str) -> str:
    """Tạo unique ID cho folder"""
    return hashlib.md5(folder_path.encode()).hexdigest()


  def index_folders(self) -> Dict[str, FolderMetadata]:
    """Index tất cả folders và metadata"""

    folder_metadata = {}
    
    for root, dirs, files in os.walk(self.data_path):
      # Skip root directory
      if root == self.data_path:
        continue
      
      folder_path = root
      folder_name = os.path.basename(folder_path)
      folder_id = self._generate_folder_id(folder_path)
      
      # Load folder metadata
      meta_data = self.processor.load_folder_metadata(folder_path)
      
      if meta_data:
        # Tạo FolderMetadata object
        folder_meta = FolderMetadata(
          folder_id=folder_id,
          folder_name=folder_name,
          folder_path=folder_path,
          description=meta_data.get('description', ''),
          legal_domain=meta_data.get('legal_domain', ''),
          total_documents=len([f for f in files if f != 'meta.json']),
          last_updated=meta_data.get('last_updated', ''),
          keywords=meta_data.get('keywords', []),
          hierarchy_level=len(Path(folder_path).parts) - len(Path(self.data_path).parts),
          parent_folder=meta_data.get('parent_folder')
        )

        folder_metadata[folder_id] = folder_meta
        self.folder_cache[folder_id] = folder_meta
        
        # Embed folder metadata cho semantic search
        folder_text = f"{folder_meta.description} {' '.join(folder_meta.keywords)}"
        folder_embedding = self.embedding_model.encode([folder_text])

        
        # Store trong ChromaDB
        metadata_dict = asdict(folder_meta)
        if isinstance(metadata_dict.get("keywords"), list):
          metadata_dict["keywords"] = ", ".join(metadata_dict["keywords"])
        for key, value in metadata_dict.items():
          if value is None:
              metadata_dict[key] = ""

        self.folder_collection.add(
          embeddings=[folder_embedding[0].tolist()],
          documents=[folder_text],
          metadatas=[metadata_dict],
          ids=[folder_id]
        )
        
    return folder_metadata



  def index_documents(self) -> int:
    """Index tất cả documents trong folders"""
    
    total_chunks = 0
    
    for folder_id, folder_meta in self.folder_cache.items():
      folder_path = folder_meta.folder_path
      
      # Lấy tất cả files trong folder (trừ meta.json)
      files = [f for f in os.listdir(folder_path) if f != 'meta.json' and os.path.isfile(os.path.join(folder_path, f))]
      
      for file_name in files:
        file_path = os.path.join(folder_path, file_name)
        
        # Extract text từ file
        text_content = self.processor.extract_text_from_file(file_path)
        
        if not text_content.strip():
          continue
        
        # Tạo document metadata
        document_id = hashlib.md5(file_path.encode()).hexdigest()
        
        base_metadata = {
          'document_id': document_id,
          'folder_path': folder_path,
          'folder_name': folder_meta.folder_name,
          'folder_id': folder_id,
          'file_name': file_name,
          'file_type': Path(file_name).suffix,
          'folder_meta_summary': folder_meta.description,
          'legal_category': folder_meta.legal_domain,
          'folder_keywords': folder_meta.keywords
        }
        
        # Chunk document
        chunks = self.processor.chunk_document(text_content, base_metadata)

        for chunk_data in chunks:
          # Sanitize metadata giống index_folders
          metadata_dict = chunk_data['metadata']
          for key, value in metadata_dict.items():
            if isinstance(value, list):
              metadata_dict[key] = ", ".join(value)
            elif value is None:
              metadata_dict[key] = ""

          # Tạo enhanced text cho embedding
          enhanced_text = self._create_enhanced_chunk_text(
            chunk_data['text'],
            metadata_dict
          )

          # Generate embedding
          embedding = self.embedding_model.encode([enhanced_text])

          # Store trong ChromaDB
          self.document_collection.add(
            embeddings=[embedding[0].tolist()],
            documents=[chunk_data['text']],
            metadatas=[metadata_dict],
            ids=[chunk_data['id']]
          )

          total_chunks += 1

    return total_chunks



  def _create_enhanced_chunk_text(self, chunk_text: str, metadata: Dict) -> str:
    """Tạo enhanced text cho embedding với context từ folder metadata"""
    
    folder_context = f"Lĩnh vực pháp lý: {metadata.get('legal_category', '')}"
    folder_summary = f"Bối cảnh thư mục: {metadata.get('folder_meta_summary', '')}"
    keywords = f"Từ khóa: {' '.join(metadata.get('folder_keywords', []))}"
    
    enhanced_text = f"{folder_context}\n{folder_summary}\n{keywords}\n\nNội dung: {chunk_text}"
    return enhanced_text



  def hybrid_search(
    self,
    query: str,
    top_k: int = 10,
    folder_filter: Optional[List[str]] = None,
    legal_category_filter: Optional[str] = None
  ) -> List[Dict]:
    """
    Hybrid search kết hợp:
      1. Folder-level semantic search
      2. Document-level semantic search  
      3. Filtering và ranking
    """
    
    results = []
    
    # Step 1: Tìm relevant folders trước
    relevant_folders = self._search_relevant_folders(query, top_k)
    
    # Step 2: Search trong documents, ưu tiên relevant folders
    folder_ids = [f['folder_id'] for f in relevant_folders]
    if folder_filter:
      folder_ids = list(set(folder_ids) & set(folder_filter))
      
    # Build where clause cho filtering
    where_clause = {}
    if folder_ids:
      where_clause["folder_id"] = {"$in": folder_ids}
    if legal_category_filter:
      where_clause["legal_category"] = legal_category_filter
      
    # Enhanced query với folder context
    enhanced_query = self._enhance_query_with_folder_context(query, relevant_folders)
    query_embedding = self.embedding_model.encode([enhanced_query])
    
    # Search documents
    doc_results = self.document_collection.query(
      query_embeddings=[query_embedding[0].tolist()],
      n_results=top_k * 2, # Lấy nhiều hơn để có thể re-rank
      where=where_clause if where_clause else None
    )
    
    # Step 3: Re-rank và combine results
    final_results = self._rerank_results(
      query, doc_results, relevant_folders
    )
    
    return final_results[:top_k]
    
    
  


  def _search_relevant_folders(self, query: str, top_k: int = 5) -> List[Dict]:
    """Tìm folders liên quan đến query"""
    
    query_embedding = self.embedding_model.encode([query])
    
    folder_results = self.folder_collection.query(
      query_embeddings=[query_embedding[0].tolist()],
      n_results=top_k
    )
    
    results = []
    
    for i in range(len(folder_results['ids'][0])):
      results.append({
        'folder_id': folder_results['ids'][0][i],
        'folder_metadata': folder_results['metadatas'][0][i],
        'similarity_score': 1 - folder_results['distances'][0][i],
        'description': folder_results['documents'][0][i]
      })

    return results
  
  
  
  def _enhance_query_with_folder_context(self, query: str, relevant_folders: List[Dict]) -> str:
    """Enhance query với context từ relevant folders"""
    
    if not relevant_folders:
      return query
    
    folder_contexts = []
    
    for folder in relevant_folders[:3]: # Top 3 folders
      meta = folder['folder_metadata']
      context = f"Lĩnh vực: {meta.get('legal_domain', '')} - {meta.get('description', '')}"
      folder_contexts.append(context)
      
      
    enhanced_query = f"Bối cảnh: {' | '.join(folder_contexts)}\n\nTruy vấn: {query}"
    return enhanced_query
  
  
  def _rerank_results(
    self,
    query: str,
    doc_results: Dict,
    folder_results: List[Dict]
  ) -> List[Dict]:
    """Re-rank kết quả dựa trên multiple factors"""
    
    results = []
    
    # Tạo folder score mapping
    folder_scores = {f['folder_id']: f['similarity_score'] for f in folder_results}
    
    for i in range(len(doc_results['ids'][0])):
      metadata = doc_results['metadatas'][0][i]
      doc_similarity = 1 - doc_results['distances'][0][i]
      folder_similarity = folder_scores.get(metadata.get('folder_id'), 0)
      
      
      # Combined score với weights
      combined_score = (
        0.7 * doc_similarity +  # Document relevance
        0.2 * folder_similarity +  # Folder relevance  
        0.1 * self._calculate_document_authority_score(metadata)  # Document authority
      )
      
      results.append({
        'chunk_id': doc_results['ids'][0][i],
        'content': doc_results['documents'][0][i],
        'metadata': metadata,
        'doc_similarity': doc_similarity,
        'folder_similarity': folder_similarity,
        'combined_score': combined_score,
        'authority_score': self._calculate_document_authority_score(metadata)
      })
      
    # Sort theo combined score
    results.sort(key=lambda x: x['combined_score'], reverse=True)
    
    # Diversity filtering - tránh quá nhiều chunks từ cùng document
    diverse_results = self._apply_diversity_filter(results)
    
    return diverse_results
    
  
  
  
  def _calculate_document_authority_score(self, metadata: Dict) -> float:
    """Tính authority score dựa trên metadata"""
    score = 0.5  # Base score
    
    # Boost cho documents có status active
    if metadata.get('status') == 'active':
      score += 0.2
    
    # Boost cho documents có effective_date gần đây
    if metadata.get('effective_date'):
      # Logic để tính điểm dựa trên ngày hiệu lực
      score += 0.1
    
    # Boost cho documents ở folder có nhiều keywords match
    if metadata.get('folder_keywords'):
      score += min(0.2, len(metadata['folder_keywords']) * 0.05)
    
    return min(1.0, score)



  def _apply_diversity_filter(self, results: List[Dict], max_per_doc: int = 3) -> List[Dict]:
    """Áp dụng diversity filtering"""
    doc_counts = {}
    filtered_results = []
    
    for result in results:
      doc_id = result['metadata']['document_id']
      count = doc_counts.get(doc_id, 0)
      
      if count < max_per_doc:
        filtered_results.append(result)
        doc_counts[doc_id] = count + 1
  
    return filtered_results
  


  def get_folder_overview(self, folder_id: str) -> Dict:
    """Lấy tổng quan về một folder"""
    
    if folder_id in self.folder_cache:
      folder_meta = self.folder_cache[folder_id]
      
      # Lấy sample documents từ folder
      sample_docs = self.document_collection.query(
        query_embeddings=None,
        n_results=5,
        where={
          "folder_id": folder_id
        }
      )
      
      return {
        'folder_metadata': asdict(folder_meta),
        'sample_documents': sample_docs,
        'total_chunks': len(sample_docs['ids'][0]) if sample_docs['ids'] else 0
      }

    return {}

  
  
  def build_index(self, force_rebuild: bool = False):
    """Main method để build toàn bộ index"""
    
    # Check if data already exists
    if not force_rebuild and self.folder_cache:
      print("Database already exists. Use force_rebuild=True to rebuild.")
      return {
        'folders_indexed': len(self.folder_cache),
        'chunks_indexed': self.document_collection.count(),
        'status': 'loaded_existing'
      }
    
    print("---> Indexing folders...")
    folder_count = len(self.index_folders())
    print(f"#####===> Indexed {folder_count} folders")
    
    print("---> Indexing documents...")
    chunk_count = self.index_documents()
    print(f"#####===> Indexed {chunk_count} document chunks")
    
    return {
      'folders_indexed': folder_count,
      'chunks_indexed': chunk_count,
      'status': 'newly_built'
    }
    
    
  def has_existing_data(self) -> bool:
    """Check if database already has data"""
    try:
      folder_count = len(self.folder_collection.get()['ids'])
      doc_count = len(self.document_collection.get()['ids'])
      return folder_count > 0 and doc_count > 0
    except:
      return False
    
  
  def search(
    self,
    query: str,
    top_k: int = 5,
    include_folder_context: bool = True,
    **filters
  ) -> Dict:
    """Main search interface"""
    
    # Perform hybrid search
    results = self.hybrid_search(
      query=query,
      top_k=top_k,
      folder_filter=filters.get('folder_filter'),
      legal_category_filter=filters.get('legal_category_filter')
    )
    
    # Format results
    formatted_results = []
    for result in results:
      formatted_result = {
        'content': result['content'],
        'metadata': result['metadata'],
        'relevance_score': result['combined_score'],
        'source_info': {
          'folder': result['metadata']['folder_name'],
          'file': result['metadata']['file_name'],
          'chunk_position': f"{result['metadata']['chunk_index'] + 1}/{result['metadata']['total_chunks']}"
        }
      }

      if include_folder_context:
        formatted_result['folder_context'] = {
          'domain': result['metadata']['legal_category'],
          'description': result['metadata']['folder_meta_summary']
        }
        
      formatted_results.append(formatted_result)
    
    return {
      'query': query,
      'results': formatted_results,
      'total_results': len(formatted_results)
    }
    
    
    
  def _load_existing_folder_cache(self):
    """Load folder cache từ existing DB"""
    try:
      # Check if folder collection has data
      existing_folders = self.folder_collection.get()
      
      if existing_folders['ids']:
        print(f"Found existing folder data: {len(existing_folders['ids'])} folders")
        
        # Rebuild folder cache from existing data
        for i, folder_id in enumerate(existing_folders['ids']):
          metadata = existing_folders['metadatas'][i]
          
          # Convert keywords back to list if it's a string
          keywords = metadata.get('keywords', '')
          if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',') if k.strip()]
          
          folder_meta = FolderMetadata(
            folder_id=metadata['folder_id'],
            folder_name=metadata['folder_name'],
            folder_path=metadata['folder_path'],
            description=metadata['description'],
            legal_domain=metadata['legal_domain'],
            total_documents=int(metadata['total_documents']),
            last_updated=metadata['last_updated'],
            keywords=keywords,
            hierarchy_level=int(metadata['hierarchy_level']),
            parent_folder=metadata.get('parent_folder')
          )
          
          self.folder_cache[folder_id] = folder_meta
          
    except Exception as e:
      print(f"No existing data found or error loading: {e}")
      
  
  def debug_document_content(self, document_id: str = None, limit: int = 3):
    """Debug để xem nội dung chunks"""
    
    if document_id:
      # Get specific document chunks
      results = self.document_collection.get(
        where={"document_id": document_id},
        include=['documents', 'metadatas']
      )
    else:
      # Get random sample
      results = self.document_collection.get(
        limit=limit,
        include=['documents', 'metadatas']
      )
    
    print(f"\n=== DEBUG: Document chunks ===")
    if not results['ids']:
      print("No chunks found!")
      return
      
    for i, (chunk_id, content, metadata) in enumerate(zip(
      results['ids'], 
      results['documents'], 
      results['metadatas']
    )):
      print(f"\nChunk {i+1}: {chunk_id}")
      print(f"Length: {len(content)} chars")
      print(f"File: {metadata['file_name']}")
      print(f"Content preview: {content[:500]}...")
      print("-" * 50)
      
      if i >= limit - 1:  # Limit số chunks hiển thị
        break
