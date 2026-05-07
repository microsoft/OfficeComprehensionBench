#!/usr/bin/env python3
"""
Evaluation module for comparing model responses with gold standards.

Supports:
- Single-model evaluation (GPT-4.1 default, or GPT-5.4)
- Multi-LLM evaluation with majority voting (GPT-5.4, Gemini 3.1, Claude 4.6 Opus)
"""

import asyncio
import json
import os
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

try:
    from dotenv import load_dotenv
    # override=True so values in .env take precedence over stale shell/user-level vars
    load_dotenv(override=True)
except ImportError:
    pass

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider


# Model used for single-model evaluation
EVALUATION_MODEL = "gpt-5.4"

# Default models for multi-LLM majority voting
MULTI_LLM_EVAL_MODELS = {
    "gpt": "gpt-5.4",
    "gemini": "gemini-3.1-pro-preview",
    "claude": "claude-opus-4-6"
}

# Initialize Azure OpenAI client with token provider
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)
AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT')
if not AZURE_OPENAI_ENDPOINT:
    raise RuntimeError('AZURE_OPENAI_ENDPOINT environment variable is required (see .env.example).')
azure_client = AzureOpenAI(
    api_version=os.environ.get('AZURE_OPENAI_API_VERSION', '2025-03-01-preview'),
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    azure_ad_token_provider=token_provider,
)


@dataclass
class EvaluationResult:
    """Result of evaluating a single response against gold standard.
    
    For list assertions, score is float (0.0 to 1.0) representing success rate.
    For single assertions, score is int (0 or 1).
    """
    id: str
    criteria: str
    rationale: str
    score: float  # Float to support fractional scores (e.g., 0.75 = 3/4 assertions passed)
    evaluation_success: bool
    evaluation_error: Optional[str] = None
    # Source context fields
    query: Optional[str] = None
    filepath: Optional[str] = None
    answer: Optional[str] = None
    # Additional fields for list assertions
    assertion_results: Optional[List[Dict[str, Any]]] = None  # Individual assertion results
    total_assertions: Optional[int] = None
    passed_assertions: Optional[int] = None
    # Multi-LLM evaluation fields
    evaluation_mode: Optional[str] = None  # "single" or "majority_vote"
    vote_breakdown: Optional[Dict[str, int]] = None  # {model: score} for majority voting
    votes_for_pass: Optional[int] = None
    votes_for_fail: Optional[int] = None
    # Individual model rationales (full text, not truncated)
    individual_rationales: Optional[Dict[str, str]] = None  # {"gpt": "full rationale...", "gemini": "...", "claude": "..."}


@dataclass
class AssertionEvaluationResult:
    """Result of evaluating a single assertion."""
    assertion: str
    rationale: str
    score: int  # 0 or 1
    evaluation_success: bool
    evaluation_error: Optional[str] = None
    # Multi-LLM evaluation fields
    vote_breakdown: Optional[Dict[str, int]] = None  # {model: score} for majority voting
    votes_for_pass: Optional[int] = None
    votes_for_fail: Optional[int] = None
    # Individual model rationales (full text per model)
    individual_rationales: Optional[Dict[str, str]] = None  # {"gpt": "full rationale...", "gemini": "...", "claude": "..."}


def load_accuracy_prompt() -> str:
    """Load the accuracy prompt template (domain Q&A judge prompt)."""
    accuracy_path = Path(__file__).parent / "eval_prompt.md"
    
    if not accuracy_path.exists():
        raise FileNotFoundError(f"Accuracy prompt not found at {accuracy_path}")
    
    with open(accuracy_path, 'r', encoding='utf-8') as f:
        return f.read()


def format_accuracy_evaluation_prompt(query: str, model_response: str, gold_criteria: str) -> str:
    """Format the accuracy evaluation prompt for GPT-4.1 using accuracy_prompt.md.
    
    Args:
        query: The question asked (will be placed in conversation)
        model_response: The generated answer from the model (will be placed in conversation)
        gold_criteria: The reference answer/criteria to evaluate against
    """
    
    # Load the accuracy prompt template
    accuracy_template = load_accuracy_prompt()
    
    # Replace placeholders in the template
    prompt = accuracy_template.replace("{examples}", "")  # No examples for now
    prompt = prompt.replace("{question}", query)
    prompt = prompt.replace("{reference_answer}", gold_criteria)
    prompt = prompt.replace("{generated_answer}", model_response)

    return prompt




async def evaluate_response_with_accuracy_prompt(
    query: str,
    model_response: str,
    gold_criteria: str,
    query_id: str,
    filepath: Optional[str] = None
) -> EvaluationResult:
    """Evaluate a single response against gold standard using GPT-4.1 with accuracy_prompt.md."""
    
    try:
        # Format the evaluation prompt using accuracy prompt template
        evaluation_prompt = format_accuracy_evaluation_prompt(query, model_response, gold_criteria)
        print(f"Evaluating Query ID {query_id}...")
        # print("evaluation_prompt", evaluation_prompt)
        
        # Call GPT for evaluation using Responses API
        response = azure_client.responses.create(
            model=EVALUATION_MODEL,
            input=evaluation_prompt,
            max_output_tokens=2048,
            store=False,
            reasoning={"effort": "low"},
        )
        
        evaluation_text = (response.output_text or "").strip()

        print("Raw evaluation output:", evaluation_text)
        
        # Parse the JSON output from accuracy prompt
        parsed_result = parse_accuracy_evaluation_output(evaluation_text)
        
        return EvaluationResult(
            id=query_id,
            criteria=gold_criteria,
            rationale=parsed_result.get("reasoning", ""),
            score=parsed_result.get("score", 0),
            evaluation_success=True,
            query=query,
            filepath=filepath,
            answer=model_response
        )
        
    except Exception as e:
        return EvaluationResult(
            id=query_id,
            criteria=gold_criteria,
            rationale="",
            score=0,
            evaluation_success=False,
            evaluation_error=str(e),
            query=query,
            filepath=filepath,
            answer=model_response
        )


async def evaluate_single_assertion(
    query: str,
    model_response: str,
    assertion: str,
    assertion_index: int
) -> AssertionEvaluationResult:
    """Evaluate a single assertion against the model response.
    
    Args:
        query: The original question
        model_response: The model's answer
        assertion: Single assertion to check
        assertion_index: Index of this assertion (for logging)
    
    Returns:
        AssertionEvaluationResult with pass/fail for this assertion
    """
    try:
        # Format the evaluation prompt for single assertion
        evaluation_prompt = format_accuracy_evaluation_prompt(query, model_response, assertion)
        
        # Call GPT for evaluation using Responses API
        response = azure_client.responses.create(
            model=EVALUATION_MODEL,
            input=evaluation_prompt,
            max_output_tokens=2048,
            store=False,
            reasoning={"effort": "low"},
        )
        
        evaluation_text = (response.output_text or "").strip()
        
        # Parse the JSON output
        parsed_result = parse_accuracy_evaluation_output(evaluation_text)
        
        return AssertionEvaluationResult(
            assertion=assertion,
            rationale=parsed_result.get("reasoning", ""),
            score=parsed_result.get("score", 0),
            evaluation_success=True
        )
        
    except Exception as e:
        return AssertionEvaluationResult(
            assertion=assertion,
            rationale="",
            score=0,
            evaluation_success=False,
            evaluation_error=str(e)
        )


async def evaluate_response_with_list_assertions(
    query: str,
    model_response: str,
    gold_assertions: List[str],
    query_id: str,
    semaphore: asyncio.Semaphore,
    filepath: Optional[str] = None
) -> EvaluationResult:
    """Evaluate response against multiple assertions, checking each separately.
    
    Args:
        query: The original question
        model_response: The model's answer
        gold_assertions: List of assertions to check
        query_id: Unique identifier for this query
        semaphore: Concurrency control
        filepath: Optional path to the source file
    
    Returns:
        EvaluationResult with aggregated score (passed/total)
    """
    print(f"  Evaluating Query {query_id} with {len(gold_assertions)} assertions...")
    
    # Evaluate each assertion separately (semaphore limits concurrency during execution)
    async def _eval_with_semaphore(idx, assertion):
        async with semaphore:
            return await evaluate_single_assertion(query, model_response, assertion, idx)
    
    assertion_tasks = [
        _eval_with_semaphore(idx, assertion)
        for idx, assertion in enumerate(gold_assertions)
    ]
    
    # Wait for all assertion evaluations
    assertion_results = await asyncio.gather(*assertion_tasks)
    
    # Calculate overall score
    passed = sum(1 for r in assertion_results if r.evaluation_success and r.score == 1)
    total = len(gold_assertions)
    score = passed / total if total > 0 else 0.0
    
    # Check if all evaluations succeeded
    all_success = all(r.evaluation_success for r in assertion_results)
    
    # Combine rationales
    combined_rationale = "\n".join([
        f"Assertion {i+1}/{total}: {'✓' if r.score == 1 else '✗'} - {r.rationale}"
        for i, r in enumerate(assertion_results)
    ])
    
    # Convert assertion results to dicts for serialization
    assertion_dicts = [
        {
            "assertion": r.assertion,
            "rationale": r.rationale,
            "score": r.score,
            "evaluation_success": r.evaluation_success,
            "evaluation_error": r.evaluation_error
        }
        for r in assertion_results
    ]
    
    return EvaluationResult(
        id=query_id,
        criteria=json.dumps(gold_assertions),  # Store as JSON string
        rationale=combined_rationale,
        score=score,
        evaluation_success=all_success,
        evaluation_error=None if all_success else "Some assertions failed to evaluate",
        query=query,
        filepath=filepath,
        answer=model_response,
        assertion_results=assertion_dicts,
        total_assertions=total,
        passed_assertions=passed,
        evaluation_mode="single"
    )


# ============================================================================
# Multi-LLM Evaluation with Majority Voting
# ============================================================================

# Lazy-loaded multi-LLM evaluator instance
_multi_llm_evaluator = None


def get_multi_llm_evaluator(
    use_majority_voting: bool = True,
    eval_models: Optional[Dict[str, str]] = None
):
    """Get or create the multi-LLM evaluator instance."""
    global _multi_llm_evaluator
    
    # Lazy import to avoid circular dependencies
    from multi_llm_evaluator import MultiLLMEvaluator
    
    if _multi_llm_evaluator is None:
        _multi_llm_evaluator = MultiLLMEvaluator(
            eval_models=eval_models or MULTI_LLM_EVAL_MODELS,
            use_majority_voting=use_majority_voting
        )
    return _multi_llm_evaluator


async def evaluate_single_assertion_multi_llm(
    query: str,
    model_response: str,
    assertion: str,
    assertion_index: int,
    evaluator = None,
    response_model: str = ""
) -> AssertionEvaluationResult:
    """Evaluate a single assertion using multiple LLMs with majority voting.
    
    Args:
        query: The original question
        model_response: The model's answer
        assertion: Single assertion to check
        assertion_index: Index of this assertion (for logging)
        evaluator: MultiLLMEvaluator instance (created if None)
    
    Returns:
        AssertionEvaluationResult with pass/fail determined by majority vote
    """
    try:
        if evaluator is None:
            evaluator = get_multi_llm_evaluator()
        
        # Use multi-LLM evaluation
        result = await evaluator.evaluate_assertion(
            query, model_response, assertion,
            f"assertion_{assertion_index}",
            response_model=response_model
        )
        
        # Build combined rationale from all models and capture full per-model rationales
        individual_rationales = {}
        rationale_parts = []
        for ir in result.individual_results:
            if not ir.success:
                status = "error"
            elif ir.score == 1:
                status = "pass"
            else:
                status = "fail"
            rationale_parts.append(f"{ir.provider}({ir.model}): {status}")
            # Store full rationale per model (same pattern as single-assertion path)
            if ir.success:
                full_rationale = ir.reasoning if ir.reasoning else "(no reasoning provided)"
            else:
                full_rationale = f"EVALUATION FAILED: {ir.error}" if ir.error else "EVALUATION FAILED: unknown error"
            individual_rationales[ir.provider] = full_rationale
        
        combined_rationale = f"Majority vote: {result.majority_vote}. " + "; ".join(rationale_parts)
        
        return AssertionEvaluationResult(
            assertion=assertion,
            rationale=combined_rationale,
            score=result.final_score,
            evaluation_success=result.evaluation_success,
            evaluation_error=result.evaluation_error,
            vote_breakdown=result.vote_breakdown,
            votes_for_pass=result.votes_for_pass,
            votes_for_fail=result.votes_for_fail,
            individual_rationales=individual_rationales
        )
        
    except Exception as e:
        return AssertionEvaluationResult(
            assertion=assertion,
            rationale="",
            score=0,
            evaluation_success=False,
            evaluation_error=str(e)
        )


async def evaluate_response_with_list_assertions_multi_llm(
    query: str,
    model_response: str,
    gold_assertions: List[str],
    query_id: str,
    semaphore: asyncio.Semaphore,
    evaluator = None,
    filepath: Optional[str] = None,
    response_model: str = ""
) -> EvaluationResult:
    """Evaluate response against multiple assertions using multi-LLM majority voting.
    
    Args:
        query: The original question
        model_response: The model's answer
        gold_assertions: List of assertions to check
        query_id: Unique identifier for this query
        semaphore: Concurrency control
        evaluator: MultiLLMEvaluator instance
        filepath: Optional path to the source file
    
    Returns:
        EvaluationResult with aggregated score (passed/total) based on majority votes
    """
    print(f"  Evaluating Query {query_id} with {len(gold_assertions)} assertions (multi-LLM)...")
    
    if evaluator is None:
        evaluator = get_multi_llm_evaluator()
    
    # Evaluate each assertion separately with multi-LLM (semaphore limits concurrency during execution)
    async def _eval_with_semaphore(idx, assertion):
        async with semaphore:
            return await evaluate_single_assertion_multi_llm(
                query, model_response, assertion, idx, evaluator,
                response_model=response_model
            )
    
    assertion_tasks = [
        _eval_with_semaphore(idx, assertion)
        for idx, assertion in enumerate(gold_assertions)
    ]
    
    # Wait for all assertion evaluations
    assertion_results = await asyncio.gather(*assertion_tasks)
    
    # Calculate overall score
    passed = sum(1 for r in assertion_results if r.evaluation_success and r.score == 1)
    total = len(gold_assertions)
    score = passed / total if total > 0 else 0.0
    
    # Check if all evaluations succeeded
    all_success = all(r.evaluation_success for r in assertion_results)
    
    # Combine rationales with vote info
    combined_rationale = "\n".join([
        f"Assertion {i+1}/{total}: {'✓' if r.score == 1 else '✗'} (votes: {r.votes_for_pass}/{r.votes_for_pass + r.votes_for_fail if r.votes_for_fail else 0}) - {r.rationale}"
        for i, r in enumerate(assertion_results)
    ])
    
    # Aggregate vote breakdowns (skip failed evaluations marked as -1)
    aggregated_votes = {}
    for r in assertion_results:
        if r.vote_breakdown:
            for model, vote in r.vote_breakdown.items():
                if vote == -1:  # Skip failed evaluations
                    continue
                if model not in aggregated_votes:
                    aggregated_votes[model] = {"pass": 0, "fail": 0}
                if vote == 1:
                    aggregated_votes[model]["pass"] += 1
                else:
                    aggregated_votes[model]["fail"] += 1
    
    # Convert assertion results to dicts for serialization
    assertion_dicts = [
        {
            "assertion": r.assertion,
            "rationale": r.rationale,
            "score": r.score,
            "evaluation_success": r.evaluation_success,
            "evaluation_error": r.evaluation_error,
            "vote_breakdown": r.vote_breakdown,
            "votes_for_pass": r.votes_for_pass,
            "votes_for_fail": r.votes_for_fail,
            "individual_rationales": r.individual_rationales
        }
        for r in assertion_results
    ]
    
    total_votes_pass = sum(r.votes_for_pass or 0 for r in assertion_results)
    total_votes_fail = sum(r.votes_for_fail or 0 for r in assertion_results)
    
    # Aggregate per-model rationales across all assertions into top-level individual_rationales
    # Format: {"gpt": "Assertion 1: <rationale>\n\nAssertion 2: <rationale>\n...", "gemini": "...", "claude": "..."}
    individual_rationales = {}
    for i, r in enumerate(assertion_results):
        if r.individual_rationales:
            for provider, rationale in r.individual_rationales.items():
                if provider not in individual_rationales:
                    individual_rationales[provider] = []
                individual_rationales[provider].append(
                    f"Assertion {i+1}/{total}: {gold_assertions[i]}\n{rationale}"
                )
    # Join each provider's rationales into a single string
    individual_rationales = {
        provider: "\n\n".join(parts)
        for provider, parts in individual_rationales.items()
    } if individual_rationales else None
    
    return EvaluationResult(
        id=query_id,
        criteria=json.dumps(gold_assertions),
        rationale=combined_rationale,
        score=score,
        evaluation_success=all_success,
        evaluation_error=None if all_success else "Some assertions failed to evaluate",
        query=query,
        filepath=filepath,
        answer=model_response,
        assertion_results=assertion_dicts,
        total_assertions=total,
        passed_assertions=passed,
        evaluation_mode="majority_vote",
        vote_breakdown=aggregated_votes,
        votes_for_pass=total_votes_pass,
        votes_for_fail=total_votes_fail,
        individual_rationales=individual_rationales
    )


async def evaluate_response_with_accuracy_prompt_multi_llm(
    query: str,
    model_response: str,
    gold_criteria: str,
    query_id: str,
    evaluator = None,
    filepath: Optional[str] = None,
    response_model: str = ""
) -> EvaluationResult:
    """Evaluate a single response using multi-LLM majority voting with accuracy_prompt.md."""
    
    try:
        if evaluator is None:
            evaluator = get_multi_llm_evaluator()
        
        print(f"Evaluating Query ID {query_id} (multi-LLM)...")
        
        # Use multi-LLM evaluation
        result = await evaluator.evaluate_assertion(
            query, model_response, gold_criteria, query_id,
            response_model=response_model
        )
        
        # Build individual rationales dict (full text, not truncated)
        individual_rationales = {}
        rationale_parts = []
        for ir in result.individual_results:
            status = "pass" if ir.score == 1 else "fail"
            # Store full rationale per model
            # Include error info if the evaluation failed
            if ir.success:
                full_rationale = ir.reasoning if ir.reasoning else "(no reasoning provided)"
            else:
                full_rationale = f"EVALUATION FAILED: {ir.error}" if ir.error else "EVALUATION FAILED: unknown error"
            individual_rationales[ir.provider] = full_rationale
            # Short summary for combined rationale field (for backward compatibility)
            short_reasoning = ir.reasoning[:100] + "..." if len(ir.reasoning) > 100 else ir.reasoning
            rationale_parts.append(f"{ir.provider}({ir.model}): {status} - {short_reasoning}")
        
        combined_rationale = f"Majority vote: {result.majority_vote}. " + "\n".join(rationale_parts)
        
        return EvaluationResult(
            id=query_id,
            criteria=gold_criteria,
            rationale=combined_rationale,
            score=result.final_score,
            evaluation_success=result.evaluation_success,
            evaluation_error=result.evaluation_error,
            query=query,
            filepath=filepath,
            answer=model_response,
            evaluation_mode="majority_vote",
            vote_breakdown=result.vote_breakdown,
            votes_for_pass=result.votes_for_pass,
            votes_for_fail=result.votes_for_fail,
            individual_rationales=individual_rationales
        )
        
    except Exception as e:
        return EvaluationResult(
            id=query_id,
            criteria=gold_criteria,
            rationale="",
            score=0,
            evaluation_success=False,
            evaluation_error=str(e),
            query=query,
            filepath=filepath,
            answer=model_response
        )


def parse_evaluation_output(evaluation_text: str) -> Dict[str, Any]:
    """Parse the YAML-like evaluation output from GPT-4.1."""
    
    result = {}
    current_field = None
    current_value = []
    
    lines = evaluation_text.split('\n')
    
    for line in lines:
        line = line.strip()
        
        if line.startswith('criteria:'):
            if current_field:
                result[current_field] = '\n'.join(current_value).strip()
            current_field = 'criteria'
            current_value = [line[9:].strip()]  # Remove 'criteria:' prefix
            
        elif line.startswith('rationale:'):
            if current_field:
                result[current_field] = '\n'.join(current_value).strip()
            current_field = 'rationale'
            current_value = [line[10:].strip()]  # Remove 'rationale:' prefix
            
        elif line.startswith('score:'):
            if current_field:
                result[current_field] = '\n'.join(current_value).strip()
            current_field = 'score'
            score_text = line[6:].strip()  # Remove 'score:' prefix
            try:
                result['score'] = int(score_text)
            except ValueError:
                result['score'] = 0
            current_field = None
            current_value = []
            
        elif current_field and line:
            current_value.append(line)
    
    # Handle the last field
    if current_field and current_field != 'score':
        result[current_field] = '\n'.join(current_value).strip()
    
    return result


def parse_accuracy_evaluation_output(evaluation_text: str) -> Dict[str, Any]:
    """Parse the JSON evaluation output from accuracy_prompt.md."""
    
    try:
        # Remove markdown code blocks if present
        # evaluation_text = evaluation_text.strip()
        # if evaluation_text.startswith('```json'):
        #     evaluation_text = evaluation_text[7:]  # Remove ```json
        # if evaluation_text.startswith('```'):
        #     evaluation_text = evaluation_text[3:]  # Remove ```
        # if evaluation_text.endswith('```'):
        #     evaluation_text = evaluation_text[:-3]  # Remove trailing ```
        
        evaluation_text = evaluation_text.strip()
        
        # Parse JSON
        result = json.loads(evaluation_text)
        
        # Ensure we have the expected fields
        if 'reasoning' not in result:
            result['reasoning'] = ''
        if 'score' not in result:
            result['score'] = 0
        
        # Convert score to int if it's a string
        if isinstance(result['score'], str):
            try:
                result['score'] = int(result['score'])
            except ValueError:
                result['score'] = 0
        
        return result
        
    except json.JSONDecodeError as e:
        # If JSON parsing fails, return default values
        print(f"Warning: Failed to parse JSON evaluation output: {e}")
        print(f"Raw text: {evaluation_text}")
        return {
            'reasoning': 'Failed to parse evaluation output',
            'score': 0
        }


async def evaluate_batch_results_with_accuracy_prompt(
    processing_outputs: List[Dict[str, Any]],
    max_concurrent: int = 3
) -> List[EvaluationResult]:
    """Evaluate a batch of processing outputs against their gold standards using accuracy_prompt.md.
    
    Supports both single assertions and lists of assertions:
    - Single assertion (string): Evaluated once, score is 0 or 1
    - Multiple assertions (list): Each evaluated separately, score is passed/total (0.0 to 1.0)
    """
    
    # Filter outputs that have gold standards and were successful
    evaluatable_outputs = [
        output for output in processing_outputs
        if output.get('gold') and output.get('success', False)
    ]
    
    if not evaluatable_outputs:
        print("No outputs with gold standards found for evaluation")
        return []
    
    print(f"Evaluating {len(evaluatable_outputs)} outputs with gold standards using eval_prompt.md...")
    
    # Create semaphore for rate limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Create evaluation tasks - handle both single and list assertions
    tasks = []
    for output in evaluatable_outputs:
        gold = output['gold']
        filepath = output.get('filepath')
        
        # Check if gold is a list of assertions
        if isinstance(gold, list):
            # Multiple assertions - evaluate each separately
            task = evaluate_response_with_list_assertions(
                query=output['query'],
                model_response=output['answer'],
                gold_assertions=gold,
                query_id=output['id'],
                semaphore=semaphore,
                filepath=filepath
            )
        else:
            # Single assertion - evaluate as before
            task = evaluate_single_with_accuracy_prompt_and_semaphore(
                query=output['query'],
                model_response=output['answer'],
                gold_criteria=gold,
                query_id=output['id'],
                semaphore=semaphore,
                filepath=filepath
            )
        tasks.append(task)
    
    # Execute evaluations concurrently
    evaluation_results = []
    for task in asyncio.as_completed(tasks):
        result = await task
        evaluation_results.append(result)
        
        if result.evaluation_success:
            # Display score with appropriate formatting
            if result.total_assertions:
                # List assertions - show fractional score
                status = "✓" if result.score == 1.0 else "◐" if result.score > 0 else "✗"
                print(f"  {status} Query {result.id}: Score {result.score:.2f} ({result.passed_assertions}/{result.total_assertions})")
            else:
                # Single assertion - show binary
                status = "✓" if result.score >= 1.0 else "✗"
                print(f"  {status} Query {result.id}: Score {result.score}")
        else:
            print(f"  ! Query {result.id}: Evaluation failed - {result.evaluation_error}")
    
    return evaluation_results


async def evaluate_batch_results_with_multi_llm(
    processing_outputs: List[Dict[str, Any]],
    max_concurrent: int = 3,
    use_majority_voting: bool = True,
    eval_models: Optional[Dict[str, str]] = None
) -> List[EvaluationResult]:
    """Evaluate a batch of processing outputs using multi-LLM majority voting.
    
    Args:
        processing_outputs: List of processing outputs to evaluate
        max_concurrent: Maximum concurrent evaluations
        use_majority_voting: If True, use 3 LLMs with majority vote. If False, use single model.
        eval_models: Dict of models to use, e.g. {"gpt": "gpt-5.2", "gemini": "gemini-3.1-pro-preview", "claude": "claude-opus-4-6"}
    
    Supports both single assertions and lists of assertions:
    - Single assertion (string): Evaluated by each LLM, majority vote determines score
    - Multiple assertions (list): Each assertion evaluated by all LLMs, majority vote per assertion
    """
    
    # Filter outputs that have gold standards and were successful
    evaluatable_outputs = [
        output for output in processing_outputs
        if output.get('gold') and output.get('success', False)
    ]
    
    if not evaluatable_outputs:
        print("No outputs with gold standards found for evaluation")
        return []
    
    # Initialize evaluator
    evaluator = get_multi_llm_evaluator(use_majority_voting=use_majority_voting, eval_models=eval_models)
    
    eval_mode = "multi-LLM majority voting" if use_majority_voting else "single-model"
    if use_majority_voting:
        models_str = ", ".join([f"{k}={v}" for k, v in (eval_models or MULTI_LLM_EVAL_MODELS).items()])
        print(f"Evaluating {len(evaluatable_outputs)} outputs with {eval_mode}")
        print(f"  Models: {models_str}")
    else:
        print(f"Evaluating {len(evaluatable_outputs)} outputs with single-model evaluation")
    
    # Create semaphore for rate limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Create evaluation tasks - handle both single and list assertions
    tasks = []
    for output in evaluatable_outputs:
        gold = output['gold']
        filepath = output.get('filepath')
        
        # Check if gold is a list of assertions
        if isinstance(gold, list):
            # Multiple assertions - evaluate each separately with multi-LLM
            task = evaluate_response_with_list_assertions_multi_llm(
                query=output['query'],
                model_response=output['answer'],
                gold_assertions=gold,
                query_id=output['id'],
                semaphore=semaphore,
                evaluator=evaluator,
                filepath=filepath,
                response_model=output.get('model', '')
            )
        else:
            # Single assertion - use multi-LLM evaluation
            async def _eval_single(output=output, gold=gold, semaphore=semaphore, evaluator=evaluator, filepath=filepath):
                async with semaphore:
                    result = await evaluate_response_with_accuracy_prompt_multi_llm(
                        query=output['query'],
                        model_response=output['answer'],
                        gold_criteria=gold,
                        query_id=output['id'],
                        evaluator=evaluator,
                        filepath=filepath,
                        response_model=output.get('model', '')
                    )
                    await asyncio.sleep(0.3)  # Rate limiting
                    return result
            
            task = _eval_single()
        tasks.append(task)
    
    # Execute evaluations concurrently
    evaluation_results = []
    for task in asyncio.as_completed(tasks):
        result = await task
        evaluation_results.append(result)
        
        if result.evaluation_success:
            # Display score with appropriate formatting
            if result.total_assertions:
                # List assertions - show fractional score
                status = "✓" if result.score == 1.0 else "◐" if result.score > 0 else "✗"
                vote_info = f" [votes: {result.votes_for_pass}/{result.votes_for_pass + result.votes_for_fail}]" if result.votes_for_pass is not None else ""
                print(f"  {status} Query {result.id}: Score {result.score:.2f} ({result.passed_assertions}/{result.total_assertions}){vote_info}")
            else:
                # Single assertion - show binary with vote info
                status = "✓" if result.score >= 1.0 else "✗"
                vote_info = f" [votes: {result.votes_for_pass}/{result.votes_for_pass + result.votes_for_fail}]" if result.votes_for_pass is not None else ""
                print(f"  {status} Query {result.id}: Score {result.score}{vote_info}")
        else:
            print(f"  ! Query {result.id}: Evaluation failed - {result.evaluation_error}")
    
    return evaluation_results


async def evaluate_single_with_accuracy_prompt_and_semaphore(
    query: str,
    model_response: str,
    gold_criteria: str,
    query_id: str,
    semaphore: asyncio.Semaphore,
    filepath: Optional[str] = None
) -> EvaluationResult:
    """Evaluate a single response with semaphore for rate limiting using accuracy_prompt.md."""
    
    async with semaphore:
        result = await evaluate_response_with_accuracy_prompt(query, model_response, gold_criteria, query_id, filepath)
        # Add small delay to avoid overwhelming the API
        await asyncio.sleep(0.5)
        return result


def calculate_accuracy_metrics(evaluation_results: List[EvaluationResult]) -> Dict[str, Any]:
    """Calculate accuracy metrics from evaluation results."""
    
    if not evaluation_results:
        return {
            "overall": {
                "total_evaluated": 0,
                "successful_evaluations": 0,
                "passed_evaluations": 0,
                "accuracy": 0.0,
                "evaluation_success_rate": 0.0
            },
            "by_category": {}
        }
    
    successful_evaluations = [r for r in evaluation_results if r.evaluation_success]
    passed_evaluations = [r for r in successful_evaluations if r.score >= 1.0]
    
    total_evaluated = len(evaluation_results)
    num_successful = len(successful_evaluations)
    num_passed = len(passed_evaluations)
    
    accuracy = num_passed / num_successful if num_successful > 0 else 0.0
    evaluation_success_rate = num_successful / total_evaluated if total_evaluated > 0 else 0.0
    
    overall_metrics = {
        "total_evaluated": total_evaluated,
        "successful_evaluations": num_successful,
        "passed_evaluations": num_passed,
        "accuracy": accuracy,
        "evaluation_success_rate": evaluation_success_rate
    }
    
    return {
        "overall": overall_metrics,
        "by_category": {}
    }


def calculate_categorized_accuracy_metrics(
    evaluation_results: List[EvaluationResult], 
    processing_outputs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Calculate accuracy metrics categorized by various dimensions.
    
    Handles both binary scores (0 or 1) and fractional scores (0.0 to 1.0) from list assertions.
    Accuracy is calculated as the average score across all evaluations.
    """
    
    if not evaluation_results:
        return {
            "overall": {
                "total_evaluated": 0,
                "successful_evaluations": 0,
                "passed_evaluations": 0,
                "accuracy": 0.0,
                "evaluation_success_rate": 0.0,
                "total_score": 0.0,
                "total_assertions": 0,
                "passed_assertions": 0,
                "assertion_accuracy": 0.0
            },
            "by_category": {}
        }
    
    # Create a mapping from id to processing output for category lookup
    output_by_id = {output['id']: output for output in processing_outputs}
    
    # Calculate overall metrics
    successful_evaluations = [r for r in evaluation_results if r.evaluation_success]
    
    # Sum up scores (handles both 0/1 and fractional scores)
    total_score = sum(r.score for r in successful_evaluations)
    
    # Count as "passed" if score >= threshold (0.5 for partial, 1.0 for perfect)
    # For reporting, we'll use the total score / num evaluations as accuracy
    passed_evaluations = [r for r in successful_evaluations if r.score >= 1.0]
    
    total_evaluated = len(evaluation_results)
    num_successful = len(successful_evaluations)
    num_passed = len(passed_evaluations)
    
    # Accuracy is average score (works for both binary and fractional)
    accuracy = total_score / num_successful if num_successful > 0 else 0.0
    evaluation_success_rate = num_successful / total_evaluated if total_evaluated > 0 else 0.0
    
    # Aggregate assertion-level stats
    total_assertions = sum(r.total_assertions or 1 for r in successful_evaluations)
    passed_assertions = sum(r.passed_assertions or (1 if r.score >= 1.0 else 0) for r in successful_evaluations)
    
    assertion_accuracy = passed_assertions / total_assertions if total_assertions > 0 else 0.0
    
    overall_metrics = {
        "total_evaluated": total_evaluated,
        "successful_evaluations": num_successful,
        "passed_evaluations": num_passed,  # Perfect scores only
        "accuracy": accuracy,  # Average score (0.0 to 1.0)
        "evaluation_success_rate": evaluation_success_rate,
        "total_score": total_score,
        "total_assertions": total_assertions,
        "passed_assertions": passed_assertions,
        "assertion_accuracy": assertion_accuracy  # passed_assertions / total_assertions
    }
    
    # Identify all category columns (excluding standard fields)
    excluded_fields = {'filepath', 'query', 'gold', 'id', 'model', 'answer', 'processing_time', 'success', 'error', 'image_urls'}
    category_columns = set()
    
    for output in processing_outputs:
        category_columns.update(k for k in output.keys() if k not in excluded_fields)
    
    # Calculate metrics by category
    by_category = {}
    
    for category_col in sorted(category_columns):
        category_metrics = {}
        
        # Group evaluation results by category values
        category_groups = {}
        for eval_result in evaluation_results:
            output = output_by_id.get(eval_result.id, {})
            category_value = output.get(category_col, 'Unknown')
            
            if category_value not in category_groups:
                category_groups[category_value] = []
            category_groups[category_value].append(eval_result)
        
        # Calculate metrics for each category value
        for category_value, results in category_groups.items():
            successful_in_category = [r for r in results if r.evaluation_success]
            
            # Sum scores for accuracy calculation
            total_score_in_category = sum(r.score for r in successful_in_category)
            passed_in_category = [r for r in successful_in_category if r.score >= 1.0]
            
            total_in_category = len(results)
            num_successful_in_category = len(successful_in_category)
            num_passed_in_category = len(passed_in_category)
            
            accuracy_in_category = total_score_in_category / num_successful_in_category if num_successful_in_category > 0 else 0.0
            success_rate_in_category = num_successful_in_category / total_in_category if total_in_category > 0 else 0.0
            
            # Aggregate assertion-level stats for this category
            total_assertions_in_category = sum(r.total_assertions or 1 for r in successful_in_category)
            passed_assertions_in_category = sum(r.passed_assertions or (1 if r.score >= 1.0 else 0) for r in successful_in_category)
            
            assertion_accuracy_in_category = passed_assertions_in_category / total_assertions_in_category if total_assertions_in_category > 0 else 0.0
            
            category_metrics[str(category_value)] = {
                "total_evaluated": total_in_category,
                "successful_evaluations": num_successful_in_category,
                "passed_evaluations": num_passed_in_category,
                "accuracy": accuracy_in_category,
                "evaluation_success_rate": success_rate_in_category,
                "total_score": total_score_in_category,
                "total_assertions": total_assertions_in_category,
                "passed_assertions": passed_assertions_in_category,
                "assertion_accuracy": assertion_accuracy_in_category
            }
        
        by_category[category_col] = category_metrics
    
    return {
        "overall": overall_metrics,
        "by_category": by_category
    }


def save_categorized_metrics(
    metrics: Dict[str, Any],
    output_path: str
):
    """Save categorized metrics to JSON file."""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def save_evaluation_results(
    evaluation_results: List[EvaluationResult],
    output_path: str
):
    """Save evaluation results to NDJSON file."""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for result in evaluation_results:
            json.dump(asdict(result), f, ensure_ascii=False)
            f.write('\n')


def print_accuracy_report(metrics: Dict[str, Any]):
    """Print a formatted accuracy report with categorized metrics."""
    
    overall = metrics.get("overall", {})
    by_category = metrics.get("by_category", {})
    
    print("\n" + "="*60)
    print("EVALUATION RESULTS")
    print("="*60)
    
    # Overall metrics
    print(f"OVERALL METRICS:")
    print(f"  Total Queries Evaluated: {overall.get('total_evaluated', 0)}")
    print(f"  Successful Evaluations: {overall.get('successful_evaluations', 0)}")
    print(f"  Perfect Scores (100%): {overall.get('passed_evaluations', 0)}")
    print(f"  Average Accuracy: {overall.get('accuracy', 0):.2%}")
    print(f"  Evaluation Success Rate: {overall.get('evaluation_success_rate', 0):.2%}")
    
    # Assertion-level stats if available
    if overall.get('total_assertions', 0) > 0:
        print(f"\n  ASSERTION-LEVEL STATISTICS:")
        print(f"    Total Assertions: {overall.get('total_assertions', 0)}")
        print(f"    Passed Assertions: {overall.get('passed_assertions', 0)}")
        assertion_accuracy = overall.get('assertion_accuracy', overall.get('passed_assertions', 0) / overall.get('total_assertions', 1))
        print(f"    Assertion Accuracy: {assertion_accuracy:.2%}")
    
    # Category-wise metrics
    if by_category:
        print(f"\nCATEGORIZED ACCURACY:")
        print("-" * 60)
        
        for category_name, category_data in by_category.items():
            print(f"\n📊 {category_name.upper()}:")
            
            # Sort by accuracy (descending) for better readability
            sorted_categories = sorted(
                category_data.items(), 
                key=lambda x: x[1]['accuracy'], 
                reverse=True
            )
            
            for category_value, metrics in sorted_categories:
                accuracy = metrics['accuracy']
                total = metrics['total_evaluated']
                passed = metrics['passed_evaluations']
                
                # Color coding for terminal output
                if accuracy >= 0.8:
                    status = "🟢"
                elif accuracy >= 0.6:
                    status = "🟡"
                else:
                    status = "🔴"
                
                print(f"  {status} {category_value}: {accuracy:.1%} ({passed}/{total})")
    
    print("="*60)


async def main():
    """Test the evaluation functionality."""
    
    # Example usage
    test_outputs = [
        {
            "id": "1",
            "filepath": "test.docx",
            "query": "What is the main topic?",
            "gold": "The response should identify the document's primary subject matter",
            "model": "claude-sonnet-4-5-20250929",
            "answer": "The main topic of this document is artificial intelligence applications in healthcare.",
            "processing_time": 2.5,
            "success": True
        }
    ]
    
    # Run evaluation
    #results = await evaluate_batch_results(test_outputs)
    results = await evaluate_batch_results_with_accuracy_prompt(test_outputs)

    # Calculate and print metrics with categorization
    metrics = calculate_categorized_accuracy_metrics(results, test_outputs)
    print_accuracy_report(metrics)


if __name__ == "__main__":
    asyncio.run(main())