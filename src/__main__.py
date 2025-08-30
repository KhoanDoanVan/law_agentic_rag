

from core.hierarchical_rag_system import HierarchicalRAGSystem
from core.law_rag_query_engine import LegalRAGQueryEngine



import sys

def main():
    """Example usage của RAG system"""
    
    # Initialize system
    rag_system = HierarchicalRAGSystem(
        data_path="./law_documents",  # Path tới folder chứa data
        embedding_model="sentence-transformers/all-MiniLM-L6-v2"
    )
    
    # Build index
    if not rag_system.has_existing_data():
        print("No existing database found. Building index...")
        index_stats = rag_system.build_index()
        print(f"Index built: {index_stats}")
    else:
        print("Existing database found. Skipping index building.")
        
    # Debug: Check một vài chunks để xem content
    print("\n=== Checking sample chunks ===")
    rag_system.debug_document_content(limit=2)
    
    # Initialize query engine
    query_engine = LegalRAGQueryEngine(rag_system)
    
    # Check if query was passed as command-line argument
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("🔍 Enter your query: ")
    
    print(f"\n🔍 Query: {query}")
    
    # Search
    results = rag_system.search(query, top_k=3)
    
    for i, result in enumerate(results['results'], 1):
        print(f"\n{i}. Score: {result['relevance_score']:.3f}")
        print(f"   Source: {result['source_info']['folder']}/{result['source_info']['file']}")
        print(f"   Content preview: {result['content']}")
        
    # Get answer
    answer = query_engine.answer_question(query)
    print(f"\n📋 Context sources: {answer['sources']}")

if __name__ == "__main__":
    main()
