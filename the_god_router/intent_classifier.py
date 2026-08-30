"""
the_god_router/intent_classifier.py
================================================================================
ENTERPRISE EDITION: The Master Router & Dynamic Resource Allocator (Rio 2040)
================================================================================
Capabilities:
- Dynamic Prompt Complexity Classification: O(1), O(N), O(N^2), AAA
- Intelligent Engine Bypass: Disables C++/WebRTC for lightweight WebGL to save RAM
- Direct Priority Assignment to SimulationScheduler (CRITICAL, HIGH, NORMAL, LOW)
- Pydantic Schema Validation with Deterministic Heuristic Fallback
- 100% Zero-Hardcoding Universal AI Gateway Integration
================================================================================
"""

import json
import logging
import asyncio
import time
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("GodNode.MasterRouter")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - [MASTER ROUTER] - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

# Safe Universal Gateway Resolution
try:
    from god_brain.api_nexus import UniversalAIGateway
    GATEWAY_AVAILABLE = True
except Exception as e:
    logger.warning(f"UniversalAIGateway import notice in MasterRouter: {e}")
    GATEWAY_AVAILABLE = False
    UniversalAIGateway = None

# Safe Priority Enum Resolution
try:
    from simulation_scheduler.priorities import SimulationPriority
except Exception as e:
    logger.warning(f"SimulationPriority import notice in MasterRouter: {e}")
    class SimulationPriority:
        CRITICAL = 0
        HIGH = 1
        NORMAL = 2
        LOW = 3

class GameEngineConfig(BaseModel):
    """Configuration flags determining which backend engines are activated."""
    use_cpp_bridge: bool = Field(default=False, description="True if heavy simulation requires C++ execution.")
    use_webrtc_stream: bool = Field(default=False, description="True if game requires WebRTC pixel streaming.")
    use_multiplayer_nexus: bool = Field(default=False, description="True if WebSockets multiplayer is required.")
    use_local_storage_only: bool = Field(default=True, description="True if game saves state in browser localStorage.")

class ResourceAllocation(BaseModel):
    """Dynamic RAM, Thread, and Priority budget calculated for this instance."""
    estimated_ram_mb: int = Field(default=512, description="Estimated RAM footprint in MB.")
    max_concurrent_threads: int = Field(default=4, description="Threads allocated to SimulationScheduler.")
    priority_level: int = Field(default=2, description="0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW")

class GameArchitectureSchema(BaseModel):
    """Master blueprint schema produced by the Intent Router for downstream execution."""
    target_platform: str = Field(default="web_html5", pattern="^(web_html5|mobile_apk|pc_exe|cloud_stream)$")
    complexity_class: str = Field(default="O(N)", pattern="^(O\\(1\\)|O\\(N\\)|O\\(N\\^2\\)|AAA)$")
    engine_config: GameEngineConfig
    resource_limits: ResourceAllocation
    required_agents: List[str] = Field(default_factory=lambda: ["DirectorAgent", "MapBuilderAgent", "PhysicsAgent", "QATesterAgent"])
    build_steps_dependency_graph: List[str] = Field(default_factory=lambda: ["director_plan", "map_physics_dag", "compile_threejs", "qa_verification"])

class MasterIntentRouter:
    """
    Enterprise Intent Classifier & Resource Budgeting Engine.
    Estimates algorithmic complexity, allocates server RAM/CPU threads,
    and maps work directly into the SimulationScheduler.
    """

    def __init__(self):
        self.role_name = "Master Intent Router"
        self.version = "2040.2-Enterprise"
        self.active_routings: int = 0
        logger.info(f"âš¡ [{self.role_name} v{self.version}] Online and calibrated.")

    def _sanitize_llm_output(self, text: str) -> str:
        """Strips markdown code fences and isolates valid JSON dictionary blocks."""
        if not text:
            return "{}"
        clean = text.strip()
        clean = re.sub(r"^```(?:json|javascript|js)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)
        match = re.search(r'(\{.*\})', clean, re.DOTALL)
        if match:
            return match.group(1).strip()
        return clean

    def _apply_server_allocations(self, arch: GameArchitectureSchema, req_id: str) -> Dict[str, Any]:
        """Maps architectural resource limits to live engine priorities and subsystem flags."""
        priority_map = {
            0: getattr(SimulationPriority, "CRITICAL", 0),
            1: getattr(SimulationPriority, "HIGH", 1),
            2: getattr(SimulationPriority, "NORMAL", 2),
            3: getattr(SimulationPriority, "LOW", 3)
        }
        engine_priority = priority_map.get(arch.resource_limits.priority_level, 2)
        priority_name = "NORMAL"
        if hasattr(engine_priority, "name"):
            priority_name = engine_priority.name
        elif engine_priority == 0:
            priority_name = "CRITICAL"
        elif engine_priority == 1:
            priority_name = "HIGH"
        elif engine_priority == 3:
            priority_name = "LOW"

        return {
            "cpp_engine_status": "ONLINE" if arch.engine_config.use_cpp_bridge else "BYPASSED (Optimized)",
            "webrtc_status": "ONLINE" if arch.engine_config.use_webrtc_stream else "BYPASSED (Bandwidth Saved)",
            "nexus_status": "ONLINE" if arch.engine_config.use_multiplayer_nexus else "OFFLINE (Singleplayer)",
            "scheduler_priority_assigned": priority_name,
            "allocated_ram_mb": arch.resource_limits.estimated_ram_mb,
            "thread_pool_limit": arch.resource_limits.max_concurrent_threads,
            "complexity_rating": arch.complexity_class
        }

    def _emergency_fallback_routing(self, prompt: str) -> Dict[str, Any]:
        """
        Deterministic, zero-latency fallback routing configuration.
        Ensures the swarm orchestrator always receives valid architectural parameters.
        """
        prompt_lower = prompt.lower()
        is_multiplayer = any(k in prompt_lower for k in ["multiplayer", "pvp", "coop", "mmo", "online"])
        is_heavy_sim = any(k in prompt_lower for k in ["physics sim", "fluid", "heavy", "10000", "voxel"])

        complexity = "AAA" if (is_heavy_sim and is_multiplayer) else ("O(N^2)" if is_heavy_sim else "O(N)")
        ram_mb = 1024 if is_heavy_sim else 512
        threads = 8 if is_heavy_sim else 4

        fallback_arch = GameArchitectureSchema(
            target_platform="web_html5",
            complexity_class=complexity,
            engine_config=GameEngineConfig(
                use_cpp_bridge=is_heavy_sim,
                use_webrtc_stream=False,
                use_multiplayer_nexus=is_multiplayer,
                use_local_storage_only=not is_multiplayer
            ),
            resource_limits=ResourceAllocation(
                estimated_ram_mb=ram_mb,
                max_concurrent_threads=threads,
                priority_level=1 if is_multiplayer else 2
            ),
            required_agents=["DirectorAgent", "MapBuilderAgent", "PhysicsAgent", "QATesterAgent"],
            build_steps_dependency_graph=["director_blueprint", "map_physics_dag", "compile_threejs", "qa_verification"]
        )

        try:
            arch_dict = fallback_arch.model_dump()
        except AttributeError:
            arch_dict = fallback_arch.dict()

        return {
            "status": "FALLBACK_ROUTING",
            "request_id": f"REQ-FALLBACK-{int(time.time())}",
            "architecture": arch_dict,
            "server_allocation": self._apply_server_allocations(fallback_arch, "FALLBACK")
        }

    async def analyze_and_allocate(self, prompt: str) -> Dict[str, Any]:
        """
        Reads user prompt -> Evaluates Complexity -> Allocates Server Resources -> Returns Architecture Plan.
        """
        self.active_routings += 1
        request_id = f"REQ-{int(time.time())}-{self.active_routings}"
        logger.info(f"[{request_id}] Analyzing Directive: '{prompt[:50]}...'")

        system_prompt = (
            "You are the Master Architect API for the God Node V2 (Rio) Game Engine.\n"
            "Analyze the game request and return ONLY a valid JSON object strictly matching this schema:\n"
            "{\n"
            '  "target_platform": "web_html5" | "mobile_apk" | "pc_exe" | "cloud_stream",\n'
            '  "complexity_class": "O(1)" | "O(N)" | "O(N^2)" | "AAA",\n'
            '  "engine_config": {\n'
            '    "use_cpp_bridge": bool,\n'
            '    "use_webrtc_stream": bool,\n'
            '    "use_multiplayer_nexus": bool,\n'
            '    "use_local_storage_only": bool\n'
            '  },\n'
            '  "resource_limits": {\n'
            '    "estimated_ram_mb": int,\n'
            '    "max_concurrent_threads": int,\n'
            '    "priority_level": int (0=CRITICAL, 1=HIGH, 2=NORMAL, 3=LOW)\n'
            '  },\n'
            '  "required_agents": ["DirectorAgent", "MapBuilderAgent", "PhysicsAgent", "QATesterAgent"],\n'
            '  "build_steps_dependency_graph": ["director_blueprint", "map_physics_dag", "compile_threejs", "qa_verification"]\n'
            "}\n"
            "CRITICAL: Return valid JSON ONLY. Do NOT include markdown blocks or prose."
        )

        try:
            if GATEWAY_AVAILABLE and UniversalAIGateway is not None:
                raw_response = await UniversalAIGateway.generate_response(
                    prompt=f"Analyze and architect resources for: '{prompt}'",
                    system_prompt=system_prompt
                )
            else:
                raise RuntimeError("UniversalAIGateway is not accessible.")

            if not raw_response or len(raw_response.strip()) == 0:
                raise ValueError("Empty response from Universal AI Gateway")

            clean_json = self._sanitize_llm_output(raw_response)
            parsed_data = json.loads(clean_json)

            validated_architecture = GameArchitectureSchema(**parsed_data)
            allocation_report = self._apply_server_allocations(validated_architecture, request_id)

            try:
                arch_dict = validated_architecture.model_dump()
            except AttributeError:
                arch_dict = validated_architecture.dict()

            logger.info(f"[{request_id}] Complexity Class: {validated_architecture.complexity_class} | Priority: {allocation_report['scheduler_priority_assigned']}")
            return {
                "status": "ROUTING_COMPLETE",
                "request_id": request_id,
                "architecture": arch_dict,
                "server_allocation": allocation_report
            }

        except Exception as e:
            logger.warning(f"[{request_id}] Routing safely utilizing heuristic fallback due to: {e}")
            return self._emergency_fallback_routing(prompt)
        finally:
            self.active_routings -= 1

# Singleton Global Router Instance
master_router_instance = MasterIntentRouter()
