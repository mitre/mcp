import dspy
import json
from typing import List, Dict, Optional
from aiohttp import web

import logging
import os
import glob
from app.utility.base_world import BaseWorld
from plugins.mcp.app.utilities.paths import get_mcp_data_dir


class RAGService:
    """RAG service for CTI (Cyber Threat Intelligence) data retrieval using STIX bundles."""
    
    def __init__(self, stix_bundle_path: Optional[str] = None, embed_model: Optional[str] = None, api_key: Optional[str] = None, log: Optional[logging.Logger] = None, provider: Optional[str] = None, cti_dir: Optional[str] = None):
        self.max_characters = 6000
        self.topk_objects_to_retrieve = 5
        self.corpus = []
        self.adv_step = {}
        self.search = None
        self.api_key = api_key
        if not api_key:
            raise ValueError("RAGService requires api_key (provided by MCPService)")
        self.provider = provider
        self.embed_model = embed_model
        self.log = log or logging.getLogger("plugins.mcp")
        self.base_dir = get_mcp_data_dir()
        self.log.info(f"Loading STIX bundle from: {stix_bundle_path}")
        
        # Initialize with STIX bundle if provided (single file)
        if stix_bundle_path:
            self.load_stix_bundle(stix_bundle_path, embed_model=self.embed_model, provider=self.provider)
    
    def load_stix_bundle(self, stix_bundle_path: str, *, embed_model: str, provider: str):
        """Load base STIX bundle + any CTI STIX bundles from dir, then build embeddings."""
        if not provider:
            raise ValueError("provider is required when loading STIX bundle for RAG")
        bundles = []

        try:
            with open(stix_bundle_path, 'r') as f:
                base_bundle = json.load(f)
            bundles.append(base_bundle)
        except FileNotFoundError:
            raise FileNotFoundError(f"STIX bundle not found at: {stix_bundle_path}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in STIX bundle: {stix_bundle_path}")

        # Extra CTI-derived bundles from CTI MCP (if directory exists)
        # I think this is dead Code
        cti_dir = os.path.abspath(cti_dir) if cti_dir else None
        if os.path.isdir(cti_dir):
            for path in glob.glob(os.path.join(cti_dir, '*.json')):
                try:
                    with open(path, 'r') as f:
                        bundles.append(json.load(f))
                    self.log.info(f"[RAG] Loaded CTI STIX bundle: {path}")
                except Exception as ex:
                    self.log.warning(f"[RAG] Failed to load CTI STIX bundle {path}: {ex}")

        # One call, reusing your existing multi-bundle initializer
        self.initialize_from_bundles(bundles, embed_model=embed_model, provider=provider)

    
    def initialize_from_bundles(self, stix_bundles: List[dict], *, embed_model: str, provider: str):
        if not embed_model:
            raise ValueError("embed_model is required for RAG initialization")
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
        if not provider:
            raise ValueError("provider is required for RAG embeddings")

        qualified_embed_model = f"{provider}/{embed_model}"

        embedder = dspy.Embedder(
            qualified_embed_model,
            api_key=self.api_key,
        )
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
        if len(topK.passages) > 5:
            names = [f"{x.split(' | ')[0]}" for x in topK.passages[5:30]]
            topK = topK.passages[:5]
            self.log.info(f"names: {names}")
        else:
            names = [f"{x.split(' | ')[0]}" for x in topK.passages]
            topK = topK
            self.log.info(f"names: {names}")
        return topK
    
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

    async def upload_stix_cti(self, request):
        try:
            reader = await request.multipart()
            part = await reader.next()
            if not part or part.name != "file":
                return web.json_response({"error": 'Missing "file" field in form-data'}, status=400)

            raw_filename = part.filename or "cti.stix.json"
            filename = os.path.basename(raw_filename)

            if not filename.lower().endswith(".json"):
                return web.json_response({"error": "Only .json files are allowed"}, status=400)

            # IMPORTANT: this is the directory rag.py already loads from
            stix_dir = self.base_dir / "stix_cti"
            stix_dir.mkdir(parents=True, exist_ok=True)

            target_path = stix_dir / filename
            if target_path.exists():
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                filename = f"{stem}_{ts}{suffix}"
                target_path = stix_dir / filename

            file_bytes = await part.read()
            try:
                _ = json.loads(file_bytes.decode("utf-8"))
            except Exception as e:
                return web.json_response({"error": f"Invalid JSON: {e}"}, status=400)

            with open(target_path, "wb") as f:
                f.write(file_bytes)

            stat = target_path.stat()
            self.log.info(f"[MCP] Uploaded CTI STIX bundle to {target_path} ({stat.st_size} bytes)")
            return web.json_response({
                "message": "CTI STIX bundle uploaded",
                "filename": filename,
                "size": stat.st_size,
                "path": str(target_path)
            })
        except Exception as e:
            self.log.error(f"[MCP] Error uploading CTI STIX bundle: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def list_stix_cti(self, request):
        try:
            stix_dir = self.base_dir / "stix_cti"
            files = []
            if stix_dir.exists():
                for p in stix_dir.glob("*.json"):
                    try:
                        stat = p.stat()
                        files.append({
                            "filename": p.name,
                            "size": stat.st_size,
                            "modified": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z"
                        })
                    except Exception:
                        continue
            return web.json_response({"files": sorted(files, key=lambda x: x["filename"].lower())})
        except Exception as e:
            self.log.error(f"[MCP] Error listing CTI STIX bundles: {e}")
            return web.json_response({"error": str(e)}, status=500)

    
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