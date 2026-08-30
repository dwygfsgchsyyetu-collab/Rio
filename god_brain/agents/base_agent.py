"""
god_brain/agents/base_agent.py
================================================================================
ENTERPRISE ARCHITECTURE: God Node Swarm Base Agent (Rio 2040)
================================================================================
Capabilities:
- Universal Abstract Base Class for All 5 Swarm Agents
- Direct Non-Blocking Connection to UniversalAIGateway
- Multi-Layer JSON Sanitization & Markdown Code Fence Extractor
- Exponential Backoff Auto-Retry with Resilient Fallback Handling
- Dual Parameter Resolution (supports both `retries` and `max_retries`)
- Structured Logging & Invocation Telemetry
================================================================================
"""

import json
import logging
import asyncio
import re
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union, List

# Direct Universal Gateway Connection (Zero-Hardcoding)
from god_brain.api_nexus import UniversalAIGateway

logger = logging.getLogger("GodNode.BaseAgent")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - [SWARM BASE] - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

class GodBaseAgent(ABC):
    """
    Abstract Master Base Agent for the 5-Agent Swarm.
    Coordinates non-blocking AI cognitive generation, JSON error-proofing,
    and automatic fallback recovery.
    """

    def __init__(self, role_name: str, service_type: str = "brain"):
        self.role_name = role_name
        self.service_type = service_type
        self.total_invocations: int = 0
        self.failed_invocations: int = 0
        self.version = "2040.2-Enterprise"
        logger.info(f"âš¡ [{self.role_name}] Online and calibrated.")

    def _sanitize_json(self, raw_text: str) -> str:
        """
        Multi-Layer High-Speed JSON Extractor.
        Strips markdown code blocks, backticks, trailing explanatory prose,
        and isolates valid JSON dictionaries or lists.
        """
        if not raw_text:
            return "{}"

        # 1. Strip Markdown Code Fences
        clean = raw_text.strip()
        clean = re.sub(r"^```(?:json|javascript|js)?\s*", "", clean, flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean)

        # 2. Extract outermost JSON object { ... } or array [ ... ]
        match_obj = re.search(r'(\{.*\})', clean, re.DOTALL)
        if match_obj:
            return match_obj.group(1).strip()

        match_arr = re.search(r'(\[.*\])', clean, re.DOTALL)
        if match_arr:
            return match_arr.group(1).strip()

        return clean.strip()

    async def think_and_execute(
        self, 
        task_directive: str, 
        context: Optional[Dict[str, Any]] = None,
        retries: Optional[int] = None,
        max_retries: int = 2,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Cognitive execution loop communicating with UniversalAIGateway.
        Supports both `retries` and `max_retries` keywords for 100% agent compatibility.
        """
        self.total_invocations += 1
        effective_retries = retries if retries is not None else max_retries

        system_prompt = (
            f"You are the {self.role_name} of God Node V2 (Rio 2040).\n"
            f"Directive: {task_directive}\n"
        )
        if context:
            system_prompt += f"\nCONTEXT:\n{json.dumps(context, default=str, indent=2)}\n"
        system_prompt += "\nCRITICAL REQUIREMENT: Return ONLY valid, parseable JSON. Zero explanations, zero markdown code fences."

        last_error = None

        for attempt in range(effective_retries + 1):
            try:
                raw_response = await UniversalAIGateway.generate_response(
                    prompt=task_directive,
                    system_prompt=system_prompt
                )

                if raw_response and len(raw_response.strip()) > 0:
                    clean_json_str = self._sanitize_json(raw_response)
                    parsed_dict = json.loads(clean_json_str)

                    if isinstance(parsed_dict, dict):
                        return parsed_dict
                    elif isinstance(parsed_dict, list):
                        return {"items": parsed_dict, "status": "SUCCESS"}

                raise ValueError("Empty or unparseable response from UniversalAIGateway.")

            except Exception as e:
                last_error = e
                if attempt < effective_retries:
                    backoff_delay = 0.4 * (2 ** attempt)
                    logger.warning(
                        f"[{self.role_name}] Retry {attempt + 1}/{effective_retries} "
                        f"in {backoff_delay:.2f}s due to: {e}"
                    )
                    await asyncio.sleep(backoff_delay)
                else:
                    self.failed_invocations += 1
                    logger.warning(f"[{self.role_name}] Retries exhausted ({e}). Applying safe fallback.")

        # Resilient Safe Fallback Structure
        return {
            "status": "FALLBACK_PARSED",
            "agent": self.role_name,
            "task_directive": task_directive[:100],
            "error_note": str(last_error)[:120],
            "timestamp": time.time()
        }

    @abstractmethod
    async def perform_role(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Abstract method implemented by Director, MapBuilder, Physics, and QA agents."""
        pass
