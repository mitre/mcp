import dspy
import json
from typing import List, Dict, Optional
import logging

class RAGService:
    """RAG service for CTI (Cyber Threat Intelligence) data retrieval using STIX bundles."""
    
    def __init__(self, stix_bundle_path: Optional[str] = None, api_key: Optional[str] = None, log: Optional[logging.Logger] = None):
        self.max_characters = 6000
        self.topk_objects_to_retrieve = 5
        self.corpus = []
        self.adv_step = {}
        self.search = None
        self.api_key = api_key
        self.log = log or logging.getLogger("plugins.mcp")
        
        self.log.info(f"Loading STIX bundle from: {stix_bundle_path}")
        
        # Initialize with STIX bundle if provided (single file)
        if stix_bundle_path:
            self.load_stix_bundle(stix_bundle_path)
    
    def load_stix_bundle(self, stix_bundle_path: str, embed_model: str = 'openai/text-embedding-3-small'):
        """Load STIX bundle from file path and build embeddings."""
        try:
            with open(stix_bundle_path, 'r') as f:
                stix_bundle = json.load(f)
            self.initialize_from_bundles([stix_bundle], embed_model=embed_model)
        except FileNotFoundError:
            raise FileNotFoundError(f"STIX bundle not found at: {stix_bundle_path}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in STIX bundle: {stix_bundle_path}")
    
    def initialize_from_bundles(self, stix_bundles: List[dict], embed_model: str = 'openai/text-embedding-3-small'):
        """Initialize the RAG service with multiple STIX bundles and create retriever."""
        all_corpus = []
        all_adv_step = {}
        for bundle in stix_bundles:
            corpus, adv_step = self.extract_text_chunks(bundle)
            all_corpus.extend(corpus)
            all_adv_step.update(adv_step)

        self.corpus = all_corpus
        self.adv_step = all_adv_step
        
        self.log.info("Initializing embeddings and retriever for STIX corpus")
        embedder = dspy.Embedder(embed_model, api_key=self.api_key)
        self.search = dspy.retrievers.Embeddings(
            corpus=self.corpus,
            embedder=embedder, 
            k=self.topk_objects_to_retrieve,
        )
        self.log.info(f"[RAG] Initialized search retriever: {self.search} with model {embed_model} and k={self.topk_objects_to_retrieve}")
    
    def extract_text_chunks(self, stix_bundle: dict) -> tuple[List[str], Dict[str, str]]:
        """Extract text chunks from STIX bundle objects."""
        text_chunks = []
        adv_step = {}
        
        for obj in stix_bundle.get("objects", []):
            if obj.get("type") in [
                "attack-pattern", "malware", "tool", "threat-actor", 
                "intrusion-set", "identity", "indicator", "report"
            ]:
                name = obj.get("name", "")
                description = obj.get("description", "")
                
                if name or description:
                    adv_step[name] = description
                    text_chunks.append(f"{name} | {description}")
        
        return text_chunks, adv_step
    
    def search_cti_title(self, query: str) -> List[str]:
        """Returns top-5 results and then the names of the top-5 to top-30 results."""
        self.log.info(f"Searching CTI title with query: {query}")
        
        if not self.search:
            self.log.warning("Search attempted but RAG service not initialized with STIX data")
            return ["RAG service not initialized with STIX data"]
            
        self.log.debug(f"Using search retriever: {self.search}")
        
        topK = self.search(query)
        self.log.debug(f" Retrieved top {len(topK)} results")
        self.log.info(f"topK: {topK}")
        names = []
        if len(topK) > 5:
            names = [f"{x.split(' | ')[0]}" for x in topK.passages[5:30]]
            topK = topK[:5]
            self.log.info(f"names: {names}")
        else:
            names = [f"{x.split(' | ')[0]}" for x in topK.passages]
            topK = topK
            self.log.info(f"names: {names}")
        return topK.passages
    
    def search_cti_data_by_title(self, name: str) -> str:
        """Returns the full CTI data for a given name."""
        self.log.info(f"Searching CTI data for title: {name}")
        
        if name in self.adv_step:
            self.log.debug("Found title in adv_step cache")
            return self.adv_step[name]
        
        if not self.search:
            self.log.warning("Search attempted but RAG service not initialized with STIX data")
            return "RAG service not initialized with STIX data"
        
        results = [x for x in self.search(name, 10) if x.startswith(name + " | ")]
        if not results:
            self.log.warning(f"No CTI data found for name: {name}")
            return f"No CTI data found for name: {name}"
            
        self.log.debug(f"Found {len(results)} matching results")
        return results[0]
    
    def get_context_for_task(self, task: str) -> Dict[str, any]:
        thoughts = []

        thoughts.append(f"Getting context for task: {task}")
        cti_results = self.search_cti_title(task)
        thoughts.append(f"Retrieved {len(cti_results)} CTI results")

        detailed_context = []
        for result in cti_results[:3]:
            if " | " in result:
                name = result.split(" | ")[0]
                detail = self.search_cti_data_by_title(name)
                detailed_context.append({
                    "name": name,
                    "description": detail
                })
                thoughts.append(f"Retrieved detail for: {name}")

        return {
            "search_results": cti_results,
            "detailed_context": detailed_context,
            "query": task,
            "thoughts": thoughts  # <-- used for Stage/Thoughts display
        }


# Legacy functions for backward compatibility
def search_cti_title(query: str) -> list[str]:
    """Legacy function - use RAGService instead."""
    if 'global_rag_service' in globals():
        return global_rag_service.search_cti_title(query)
    return ["RAG service not initialized"]

def search_cti_data_by_title(name: str) -> str:
    """Legacy function - use RAGService instead."""
    if 'global_rag_service' in globals():
        return global_rag_service.search_cti_data_by_title(name)
    return "RAG service not initialized"