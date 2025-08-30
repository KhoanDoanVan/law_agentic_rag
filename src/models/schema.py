
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class DocumentMetadata:
  """Metadata structure cho mỗi document"""
  document_id: str
  folder_path: str
  folder_name: str
  file_name: str
  file_type: str
  chunk_index: int
  total_chunks: int
  folder_meta_summary: str
  document_summary: str
  legal_category: str
  effective_date: Optional[str] = None
  status: str = "active"
  parent_documents: List[str] = None
  
  def __post_init__(self):
      if self.parent_documents is None:
          self.parent_documents = []
          
          
@dataclass
class FolderMetadata:
    """Metadata structure cho mỗi folder"""
    folder_id: str
    folder_name: str
    folder_path: str
    description: str
    legal_domain: str
    total_documents: int
    last_updated: str
    keywords: List[str]
    hierarchy_level: int
    parent_folder: Optional[str] = None
    
    

