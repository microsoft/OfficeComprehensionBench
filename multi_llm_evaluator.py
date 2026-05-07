#!/usr/bin/env python3
"""
Multi-LLM Evaluator with Majority Voting - FAST VERSION

Performance-optimized copy of multi_llm_evaluator.py with:
- Native async Gemini client via client.aio.models (no thread pool)
- Native async Claude client via AsyncAnthropic (no thread pool)
- Explicit large thread pool (100 threads) as fallback for GPT only
- Reduced sleep delays between assertions
- CACHED Azure token to avoid concurrent 'az' subprocess spawning

Original: multi_llm_evaluator.py
"""

import asyncio
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential
from google import genai
import anthropic
import dotenv

dotenv.load_dotenv()

# Explicit large thread pool so run_in_executor doesn't bottleneck
_THREAD_POOL = ThreadPoolExecutor(max_workers=100)

# ============================================================================
# CACHED TOKEN MANAGEMENT
# Prevents 100 threads from spawning 'az' subprocesses simultaneously
# ============================================================================
_token_lock = threading.Lock()
_cached_token: Optional[str] = None
_token_expiry: float = 0  # Unix timestamp when token expires


def _get_cached_azure_token() -> str:
    """Get cached Azure token, refreshing only when expired (thread-safe)."""
    global _cached_token, _token_expiry
    
    # Check if we have a valid cached token (with 5 min buffer)
    current_time = time.time()
    if _cached_token and current_time < (_token_expiry - 300):
        return _cached_token
    
    # Need to refresh - acquire lock to prevent concurrent 'az' spawning
    with _token_lock:
        # Double-check after acquiring lock (another thread may have refreshed)
        current_time = time.time()
        if _cached_token and current_time < (_token_expiry - 300):
            return _cached_token
        
        # Actually refresh the token
        credential = DefaultAzureCredential()
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        _cached_token = token.token
        _token_expiry = token.expires_on
        
        print(f"✓ Azure token refreshed (expires in {int((_token_expiry - current_time) / 60)} minutes)")
        return _cached_token

# Default evaluation models for majority voting
EVAL_MODELS = {
    "gpt": "gpt-5.4",  # GPT-5.4 thinking model
    "gemini": "gemini-3.1-pro-preview",  # Gemini 3.1
    "claude": "claude-opus-4-6"  # Claude 4.6 Opus
}

# Alternative model names for flexibility
MODEL_ALIASES = {
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-thinking": "gpt-5.4",
    "gpt-5.2": "gpt-5.2",
    "gpt-5.2-thinking": "gpt-5.2",
    "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
    "claude-4.5-opus": "claude-opus-4-5-20250908",
    "claude-opus-4-5": "claude-opus-4-5-20250908",
    "claude-opus-4-5-20250908": "claude-opus-4-5-20250908",
    "claude-opus-4-6": "claude-opus-4-6"
}


@dataclass
class SingleModelEvalResult:
    """Result from a single evaluator model."""
    model: str
    provider: str  # "gpt", "gemini", or "claude"
    score: int  # 0 or 1
    reasoning: str
    success: bool
    error: Optional[str] = None


@dataclass
class MultiLLMEvalResult:
    """Result of multi-LLM evaluation with majority voting."""
    query_id: str
    assertion: str
    final_score: int  # 0 or 1 (majority vote)
    vote_breakdown: Dict[str, int]  # {model: score}
    votes_for_pass: int
    votes_for_fail: int
    majority_vote: str  # "pass", "fail", or "tie"
    individual_results: List[SingleModelEvalResult]
    evaluation_success: bool
    evaluation_error: Optional[str] = None


class MultiLLMEvaluator:
    """Evaluates assertions using multiple LLMs with majority voting. (FAST version)"""
    
    # Mapping of prompt type shorthand to filename
    PROMPT_TEMPLATES = {
        "domain": "eval_prompt.md",
    }

    def __init__(
        self,
        eval_models: Optional[Dict[str, str]] = None,
        use_majority_voting: bool = True,
        prompt_template: str = "domain"
    ):
        # Apply model aliases to normalize model names
        raw_models = eval_models or EVAL_MODELS.copy()
        self.eval_models = {}
        for provider, model in raw_models.items():
            self.eval_models[provider] = MODEL_ALIASES.get(model, model)
        
        self.use_majority_voting = use_majority_voting
        self.prompt_template = prompt_template
        
        # Initialize clients
        self.azure_client = None
        self.gemini_client = None
        self.claude_client = None
        self.claude_async_client = None  # Native async client
        
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize API clients for each provider."""
        
        # Initialize Azure OpenAI (GPT) client with cached token
        if "gpt" in self.eval_models:
            try:
                # Pre-cache the token (thread-safe, serialized)
                initial_token = _get_cached_azure_token()
                
                # Create client with the cached token
                # We'll refresh the token in the API call wrapper if needed
                self.azure_client = AzureOpenAI(
                    api_version=os.environ.get('AZURE_OPENAI_API_VERSION', '2025-03-01-preview'),
                    azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT'],
                    azure_ad_token=initial_token,
                )
                print("✓ GPT evaluation client initialized (token cached)")
            except Exception as e:
                print(f"⚠ Failed to initialize GPT client: {e}")
        
        # Initialize Gemini client (uses native async via client.aio)
        if "gemini" in self.eval_models:
            try:
                gemini_api_key = os.environ.get("GEMINI_API_KEY")
                if gemini_api_key:
                    self.gemini_client = genai.Client(api_key=gemini_api_key)
                    print("✓ Gemini evaluation client initialized (async via client.aio)")
                else:
                    print("⚠ GEMINI_API_KEY not set, Gemini evaluation disabled")
            except Exception as e:
                print(f"⚠ Failed to initialize Gemini client: {e}")
        
        # Initialize Claude client - prefer async client
        if "claude" in self.eval_models:
            try:
                claude_api_key = os.environ.get("ANTHROPIC_API_KEY")
                if claude_api_key:
                    # Native async client - no thread pool needed
                    self.claude_async_client = anthropic.AsyncAnthropic(api_key=claude_api_key)
                    # Keep sync client as fallback
                    self.claude_client = anthropic.Anthropic(api_key=claude_api_key)
                    print("✓ Claude evaluation client initialized (async)")
                else:
                    print("⚠ ANTHROPIC_API_KEY not set, Claude evaluation disabled")
            except Exception as e:
                print(f"⚠ Failed to initialize Claude client: {e}")
    
        # Set up file logger for eval prompts and responses
        self.eval_logger = logging.getLogger("eval_prompts")
        if not self.eval_logger.handlers:
            self.eval_logger.setLevel(logging.DEBUG)
            fh = logging.FileHandler(
                "eval_prompts.log", mode="a", encoding="utf-8"
            )
            fh.setFormatter(logging.Formatter(
                "%(asctime)s | %(message)s"
            ))
            self.eval_logger.addHandler(fh)
            self.eval_logger.propagate = False

    def load_accuracy_prompt(self) -> str:
        """Load the accuracy prompt template."""
        filename = self.PROMPT_TEMPLATES.get(self.prompt_template)
        if not filename:
            raise ValueError(f"Unknown prompt template '{self.prompt_template}'. Choose from: {list(self.PROMPT_TEMPLATES.keys())}")
        accuracy_path = Path(__file__).parent / filename
        
        if not accuracy_path.exists():
            raise FileNotFoundError(f"Accuracy prompt not found at {accuracy_path}")
        
        with open(accuracy_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def format_evaluation_prompt(self, query: str, model_response: str, assertion: str) -> str:
        """Format the evaluation prompt for all LLMs."""
        template = self.load_accuracy_prompt()
        
        prompt = template.replace("{examples}", "")
        prompt = prompt.replace("{question}", query)
        prompt = prompt.replace("{assertion}", assertion)
        prompt = prompt.replace("{ai_response}", model_response)
        
        return prompt
    
    async def evaluate_with_gpt(
        self,
        prompt: str,
        model: str = "gpt-5.4"
    ) -> SingleModelEvalResult:
        """Evaluate using GPT model."""
        if not self.azure_client:
            return SingleModelEvalResult(
                model=model,
                provider="gpt",
                score=0,
                reasoning="",
                success=False,
                error="GPT client not initialized"
            )
        
        try:
            loop = asyncio.get_event_loop()
            
            def _call_gpt():
                # Get cached token (refreshes automatically if expired, thread-safe)
                current_token = _get_cached_azure_token()
                
                # Create a fresh client with the current token
                # This avoids token expiry issues during long runs
                client = AzureOpenAI(
                    api_version=os.environ.get('AZURE_OPENAI_API_VERSION', '2025-03-01-preview'),
                    azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT'],
                    azure_ad_token=current_token,
                )
                
                response = client.responses.create(
                    model=model,
                    input=prompt,
                    max_output_tokens=2048,
                    store=False,
                    reasoning={"effort": "low"},
                )
                return (response.output_text or "").strip()
            
            # CRITICAL: Must use thread pool! The sync SDK blocks the event loop,
            # which was preventing Gemini and Claude from running concurrently.
            eval_text = await loop.run_in_executor(_THREAD_POOL, _call_gpt)
            self.eval_logger.debug(
                "RESPONSE | query_id=%s provider=gpt model=%s\n%s\n%s",
                getattr(self, '_current_query_id', '?'), model, eval_text, "-" * 80
            )
            
            if not eval_text:
                return SingleModelEvalResult(
                    model=model,
                    provider="gpt",
                    score=0,
                    reasoning="",
                    success=False,
                    error="GPT returned empty response"
                )
            
            parsed = self._parse_evaluation_output(eval_text)
            
            reasoning = parsed.get("reasoning", "")
            if not reasoning and eval_text:
                reasoning = f"[Raw response - parse incomplete]: {eval_text}"
            
            return SingleModelEvalResult(
                model=model,
                provider="gpt",
                score=parsed.get("score", 0),
                reasoning=reasoning,
                success=True
            )
            
        except Exception as e:
            return SingleModelEvalResult(
                model=model,
                provider="gpt",
                score=0,
                reasoning="",
                success=False,
                error=str(e)
            )
    
    async def evaluate_with_gemini(
        self,
        prompt: str,
        model: str = "gemini-3.1-pro-preview"
    ) -> SingleModelEvalResult:
        """Evaluate using Gemini model. Uses native async via client.aio."""
        if not self.gemini_client:
            return SingleModelEvalResult(
                model=model,
                provider="gemini",
                score=0,
                reasoning="",
                success=False,
                error="Gemini client not initialized"
            )
        
        try:
            # Native async - no thread pool bottleneck
            response = await self.gemini_client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "temperature": 0,
                    "max_output_tokens": 2048,
                }
            )
            eval_text = response.text
            self.eval_logger.debug(
                "RESPONSE | query_id=%s provider=gemini model=%s\n%s\n%s",
                getattr(self, '_current_query_id', '?'), model, eval_text, "-" * 80
            )
            
            if not eval_text or not eval_text.strip():
                return SingleModelEvalResult(
                    model=model,
                    provider="gemini",
                    score=0,
                    reasoning="",
                    success=False,
                    error="Gemini returned empty response"
                )
            
            parsed = self._parse_evaluation_output(eval_text)
            
            reasoning = parsed.get("reasoning", "")
            if not reasoning and eval_text:
                reasoning = f"[Raw response - parse incomplete]: {eval_text}"
            
            return SingleModelEvalResult(
                model=model,
                provider="gemini",
                score=parsed.get("score", 0),
                reasoning=reasoning,
                success=True
            )
            
        except Exception as e:
            return SingleModelEvalResult(
                model=model,
                provider="gemini",
                score=0,
                reasoning="",
                success=False,
                error=str(e)
            )
    
    async def evaluate_with_claude(
        self,
        prompt: str,
        model: str = "claude-opus-4-6"
    ) -> SingleModelEvalResult:
        """Evaluate using Claude model. Uses native async client (no thread pool)."""
        if not self.claude_async_client and not self.claude_client:
            return SingleModelEvalResult(
                model=model,
                provider="claude",
                score=0,
                reasoning="",
                success=False,
                error="Claude client not initialized"
            )
        
        try:
            if self.claude_async_client:
                # Native async - no thread pool bottleneck
                response = await self.claude_async_client.messages.create(
                    model=model,
                    max_tokens=2048,
                    temperature=0,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                eval_text = response.content[0].text
            else:
                # Fallback to sync client with explicit large thread pool
                loop = asyncio.get_event_loop()
                
                def _call_claude():
                    response = self.claude_client.messages.create(
                        model=model,
                        max_tokens=2048,
                        temperature=0,
                        messages=[
                            {"role": "user", "content": prompt}
                        ]
                    )
                    return response.content[0].text
                
                eval_text = await loop.run_in_executor(_THREAD_POOL, _call_claude)
            
            self.eval_logger.debug(
                "RESPONSE | query_id=%s provider=claude model=%s\n%s\n%s",
                getattr(self, '_current_query_id', '?'), model, eval_text, "-" * 80
            )
            
            if not eval_text or not eval_text.strip():
                return SingleModelEvalResult(
                    model=model,
                    provider="claude",
                    score=0,
                    reasoning="",
                    success=False,
                    error="Claude returned empty response"
                )
            
            parsed = self._parse_evaluation_output(eval_text)
            
            reasoning = parsed.get("reasoning", "")
            if not reasoning and eval_text:
                reasoning = f"[Raw response - parse incomplete]: {eval_text}"
            
            return SingleModelEvalResult(
                model=model,
                provider="claude",
                score=parsed.get("score", 0),
                reasoning=reasoning,
                success=True
            )
            
        except Exception as e:
            return SingleModelEvalResult(
                model=model,
                provider="claude",
                score=0,
                reasoning="",
                success=False,
                error=str(e)
            )
    
    def _parse_evaluation_output(self, eval_text: str) -> Dict[str, Any]:
        """Parse the JSON evaluation output."""
        try:
            eval_text = eval_text.strip()
            
            # Remove markdown code blocks if present
            if eval_text.startswith('```json'):
                eval_text = eval_text[7:]
            if eval_text.startswith('```'):
                eval_text = eval_text[3:]
            if eval_text.endswith('```'):
                eval_text = eval_text[:-3]
            eval_text = eval_text.strip()
            
            result = json.loads(eval_text)
            
            if 'reasoning' not in result:
                result['reasoning'] = ''
            if 'score' not in result:
                result['score'] = 0
            
            # Convert score to int if string
            if isinstance(result['score'], str):
                try:
                    result['score'] = int(result['score'])
                except ValueError:
                    result['score'] = 0
            
            return result
            
        except json.JSONDecodeError:
            # Try to extract score manually
            eval_lower = eval_text.lower()
            if '"score": 1' in eval_lower or '"score":1' in eval_lower or 'score: 1' in eval_lower:
                return {'reasoning': eval_text, 'score': 1}
            return {'reasoning': eval_text, 'score': 0}
    
    def _calculate_majority_vote(
        self,
        results: List[SingleModelEvalResult]
    ) -> Tuple[int, int, int, str]:
        """
        Calculate majority vote from individual results.
        
        Returns: (final_score, votes_for_pass, votes_for_fail, majority_vote_str)
        """
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            return 0, 0, 0, "no_votes"
        
        votes_for_pass = sum(1 for r in successful_results if r.score == 1)
        votes_for_fail = sum(1 for r in successful_results if r.score == 0)
        
        if votes_for_pass > votes_for_fail:
            return 1, votes_for_pass, votes_for_fail, "pass"
        elif votes_for_fail > votes_for_pass:
            return 0, votes_for_pass, votes_for_fail, "fail"
        else:
            # Tie - default to fail (conservative)
            return 0, votes_for_pass, votes_for_fail, "tie"
    
    async def evaluate_assertion(
        self,
        query: str,
        model_response: str,
        assertion: str,
        query_id: str,
        response_model: str = ""
    ) -> MultiLLMEvalResult:
        """
        Evaluate a single assertion using multiple LLMs with majority voting.
        """
        prompt = self.format_evaluation_prompt(query, model_response, assertion)
        model_label = f" response_model={response_model}" if response_model else ""
        self.eval_logger.debug(
            "PROMPT | query_id=%s%s assertion=%s\n%s\n%s",
            query_id, model_label,
            assertion[:120], prompt, "=" * 80
        )
        print()
        
        # Store query_id for response logging
        self._current_query_id = query_id
        
        # Prepare evaluation tasks
        tasks = []
        task_providers = []
        
        if self.use_majority_voting:
            # Use all 3 models
            if "gpt" in self.eval_models and self.azure_client:
                tasks.append(self.evaluate_with_gpt(prompt, self.eval_models["gpt"]))
                task_providers.append("gpt")
            
            if "gemini" in self.eval_models and self.gemini_client:
                tasks.append(self.evaluate_with_gemini(prompt, self.eval_models["gemini"]))
                task_providers.append("gemini")
            
            if "claude" in self.eval_models and (self.claude_async_client or self.claude_client):
                tasks.append(self.evaluate_with_claude(prompt, self.eval_models["claude"]))
                task_providers.append("claude")
        else:
            # Single model mode - use GPT only
            if self.azure_client:
                tasks.append(self.evaluate_with_gpt(prompt, self.eval_models.get("gpt", "gpt-5.4")))
                task_providers.append("gpt")
        
        if not tasks:
            return MultiLLMEvalResult(
                query_id=query_id,
                assertion=assertion,
                final_score=0,
                vote_breakdown={},
                votes_for_pass=0,
                votes_for_fail=0,
                majority_vote="no_evaluators",
                individual_results=[],
                evaluation_success=False,
                evaluation_error="No evaluator models available"
            )
        
        # Run evaluations in parallel
        results = await asyncio.gather(*tasks)
        
        # Calculate majority vote
        final_score, votes_pass, votes_fail, vote_str = self._calculate_majority_vote(results)
        
        # Build vote breakdown
        vote_breakdown = {}
        for result in results:
            if result.success:
                vote_breakdown[result.model] = result.score
            else:
                vote_breakdown[result.model] = -1
        
        # Check if any evaluation succeeded
        any_success = any(r.success for r in results)
        all_errors = [r.error for r in results if r.error]
        
        return MultiLLMEvalResult(
            query_id=query_id,
            assertion=assertion,
            final_score=final_score,
            vote_breakdown=vote_breakdown,
            votes_for_pass=votes_pass,
            votes_for_fail=votes_fail,
            majority_vote=vote_str,
            individual_results=results,
            evaluation_success=any_success,
            evaluation_error="; ".join(all_errors) if all_errors and not any_success else None
        )
    
    async def evaluate_multiple_assertions(
        self,
        query: str,
        model_response: str,
        assertions: List[str],
        query_id: str,
        semaphore: asyncio.Semaphore
    ) -> List[MultiLLMEvalResult]:
        """
        Evaluate multiple assertions for a single query.
        """
        # Semaphore limits concurrency during execution, not task creation
        async def _eval_with_semaphore(i, assertion):
            async with semaphore:
                result = await self.evaluate_assertion(
                    query, model_response, assertion, f"{query_id}_assertion_{i+1}"
                )
                # FAST: reduced sleep from 0.2s to 0.05s
                await asyncio.sleep(0.05)
                return result
        
        tasks = [
            _eval_with_semaphore(i, assertion)
            for i, assertion in enumerate(assertions)
        ]
        
        return list(await asyncio.gather(*tasks))


def get_evaluator_info(use_majority_voting: bool, eval_models: Optional[Dict[str, str]] = None) -> str:
    """Get a description of the evaluation configuration."""
    models = eval_models or EVAL_MODELS
    
    if use_majority_voting:
        model_list = ", ".join([f"{v} ({k})" for k, v in models.items()])
        return f"Multi-LLM majority voting with: {model_list}"
    else:
        return f"Single-model evaluation with: {models.get('gpt', 'gpt-5.4')}"


async def test_multi_llm_evaluator():
    """Test the multi-LLM evaluator."""
    
    evaluator = MultiLLMEvaluator(use_majority_voting=True)
    
    # Test assertion
    query = "What is the capital of France?"
    response = "The capital of France is Paris."
    assertion = "The answer correctly identifies Paris as the capital of France."
    
    print(f"\nTesting Multi-LLM Evaluator (FAST):")
    print(f"  Query: {query}")
    print(f"  Response: {response}")
    print(f"  Assertion: {assertion}")
    print()
    
    result = await evaluator.evaluate_assertion(query, response, assertion, "test_1")
    
    print(f"Results:")
    print(f"  Final Score (majority): {result.final_score}")
    print(f"  Votes: Pass={result.votes_for_pass}, Fail={result.votes_for_fail}")
    print(f"  Majority Vote: {result.majority_vote}")
    print(f"  Vote Breakdown: {result.vote_breakdown}")
    print()
    
    for ir in result.individual_results:
        status = "✓" if ir.success else "✗"
        print(f"  {status} {ir.provider} ({ir.model}): score={ir.score}")
        if ir.error:
            print(f"      Error: {ir.error}")


if __name__ == "__main__":
    asyncio.run(test_multi_llm_evaluator())
