import sys, os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(BASE_DIR)

from core.hierarchical_rag_system import HierarchicalRAGSystem
from core.law_rag_query_engine import LegalRAGQueryEngine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH = os.path.join(BASE_DIR, "src/law_documents")


def rag_tool(prompt_standardization: str) -> dict:
  """Tool using RAG techniques to answer legal questions"""
  
  rag_system = HierarchicalRAGSystem(
    data_path=DATA_PATH,
    embedding_model="sentence-transformers/all-MiniLM-L6-v2"
  )
  
  if not rag_system.has_existing_data():
    rag_system.build_index()
  
  query_engine = LegalRAGQueryEngine(rag_system)
  
  results = rag_system.search(prompt_standardization, top_k=3)
  # answer = query_engine.answer_question(prompt_standardization)
  
  return {
    "query": prompt_standardization,
    "search_results": results["results"],
    # "answer": answer["answer"],
    # "sources": answer["sources"]
  }
