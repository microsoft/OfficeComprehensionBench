#!/usr/bin/env python3
"""
Compete TSV Response Processor.

Parses TSV scrapes of AI assistant conversations, matches them against an
NDJSON of queries (with optional gold-standard assertions), and runs the
multi-LLM judge evaluation.
"""

import asyncio
import json
import os
import argparse
from dataclasses import dataclass, asdict, fields
from typing import List, Dict, Any, Optional, Set, Union
from pathlib import Path
import time
from tqdm.asyncio import tqdm
import re
import unicodedata
from difflib import SequenceMatcher
import csv

# Import evaluation modules
from evaluation import (
    evaluate_batch_results_with_accuracy_prompt,
    evaluate_batch_results_with_multi_llm,
    calculate_categorized_accuracy_metrics, 
    print_accuracy_report,
    save_evaluation_results,
    save_categorized_metrics
)


@dataclass
class QueryItem:
    """Input query item from NDJSON.
    
    filepath: Can be a single string or list of strings (for multiple documents)
    gold: Can be a single string, list of strings (assertions), or None
    """
    filepath: Union[str, List[str]]
    query: str
    gold: Optional[Union[str, List[str]]]
    id: str
    feature: Optional[str] = None
    number_of_pages: Optional[str] = None
    question_level: Optional[str] = None
    question_level2: Optional[str] = None
    size: Optional[str] = None
    sharepointurl: Optional[str] = None
    downloadurl: Optional[str] = None
    domain1: Optional[str] = None
    domain2: Optional[str] = None
    filetype: Optional[str] = None


@dataclass
class ProcessingOutput:
    """Output format matching main processors.
    
    filepath: Can be a single string or list of strings (for multiple documents)
    gold: Can be a single string, list of strings (assertions), or None
    """
    id: str
    filepath: Union[str, List[str]]
    query: str
    gold: Optional[Union[str, List[str]]]
    model: str
    answer: str
    processing_time: float
    success: bool
    error: Optional[str]
    feature: Optional[str] = None
    number_of_pages: Optional[str] = None
    question_level: Optional[str] = None
    question_level2: Optional[str] = None
    size: Optional[str] = None
    sharepointurl: Optional[str] = None
    downloadurl: Optional[str] = None
    domain1: Optional[str] = None
    domain2: Optional[str] = None
    filetype: Optional[str] = None


def load_queries_from_ndjson(file_path: str) -> List[QueryItem]:
    """Load queries from NDJSON file."""
    queries = []
    valid_fields = {f.name for f in fields(QueryItem)}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # Drop unknown keys (e.g. extra metadata columns) to stay forward-compatible
                filtered = {k: v for k, v in data.items() if k in valid_fields}
                query = QueryItem(**filtered)
                queries.append(query)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Error parsing line {line_num}: {e}")
                continue
    return queries


def extract_response_from_tsv_row(query_json: str, result_json: str) -> Optional[Dict[str, Any]]:
    """
    Extract query, response, and filenames from TSV row.
    
    Args:
        query_json: JSON string from column 0 (conversation array with user query)
        result_json: JSON string from column 6 (result array with SydneyReply)
    
    Returns:
        Dict with 'query', 'response', and 'filenames' keys, or None if extraction fails.
        'filenames' is a sorted list of document filenames extracted from hiddenText.
    """
    try:
        # Parse the query conversation (column 0)
        query_conversation = json.loads(query_json)
        if not isinstance(query_conversation, list) or len(query_conversation) == 0:
            return None
        
        # Extract user query and filenames from the conversation
        user_query = None
        filenames = []
        for msg in query_conversation:
            if not isinstance(msg, dict):
                continue
            # Extract user query text
            if msg.get('author') == 'user' and user_query is None:
                user_query = msg.get('text', '').strip()
                # Extract filenames from UpdateConversationMessages -> hiddenText
                for ucm in msg.get('UpdateConversationMessages', []):
                    if isinstance(ucm, dict):
                        hidden_text = ucm.get('hiddenText', [])
                        if isinstance(hidden_text, list):
                            for ht in hidden_text:
                                if isinstance(ht, dict) and 'fileName' in ht:
                                    filenames.append(ht['fileName'])
        
        if not user_query:
            return None
        
        # Parse the result data (column 6)
        result_data = json.loads(result_json)
        if not isinstance(result_data, list) or len(result_data) == 0:
            return None
        
        # Extract SydneyReply from the first result object
        result_obj = result_data[0]
        if not isinstance(result_obj, dict):
            return None
        
        sydney_reply = result_obj.get('SydneyReply')
        if not sydney_reply:
            return None
        
        # SydneyReply can be a list or string
        if isinstance(sydney_reply, list):
            assistant_response = ' '.join(str(item) for item in sydney_reply if item)
        else:
            assistant_response = str(sydney_reply)
        
        assistant_response = assistant_response.strip()
        
        if assistant_response:
            return {
                'query': user_query,
                'response': assistant_response,
                'filenames': sorted(filenames)
            }
        
        return None
    except Exception:
        # Silently handle parsing errors
        return None


def load_chatgpt_tsv_responses(tsv_file: str) -> List[Dict[str, Any]]:
    """Load scrape responses from an NDJSON or TSV file.

    Supported formats (auto-detected by extension):
    - .ndjson / .jsonl: one JSON object per line with keys
        {"filepath": str|list, "query": str, "response": str}
    - .tsv (slim):  header `filepath<TAB>query<TAB>response`. Multi-file
      filepath cells may use `;` or `|` separators.
    - .tsv (legacy raw scrape): 7+ columns where col 0 is the user-conversation
      JSON and col 6 is the result JSON containing SydneyReply.
    """
    responses: List[Dict[str, Any]] = []

    if not os.path.exists(tsv_file):
        raise FileNotFoundError(f"Scrape file not found: {tsv_file}")

    print(f"Loading scrape file: {tsv_file}")
    ext = os.path.splitext(tsv_file)[1].lower()

    def _normalize_filenames(fp) -> List[str]:
        if fp is None:
            return []
        if isinstance(fp, list):
            return [str(x).strip() for x in fp if x and str(x).strip()]
        s = str(fp).strip()
        if not s:
            return []
        for sep in (";", "|"):
            if sep in s:
                parts = [p.strip() for p in s.split(sep) if p.strip()]
                if len(parts) > 1:
                    return parts
        return [s]

    # NDJSON / JSONL
    if ext in (".ndjson", ".jsonl", ".json"):
        with open(tsv_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"Warning: row {line_num} JSON parse error: {e}")
                    continue
                if not isinstance(rec, dict):
                    continue
                query = (rec.get("query") or "").strip()
                response = (rec.get("response") or "").strip()
                if not query or not response:
                    print(f"Warning: row {line_num} empty query/response")
                    continue
                filenames = _normalize_filenames(rec.get("filepath"))
                responses.append({
                    "row_number": line_num,
                    "query": query,
                    "response": response,
                    "filenames": sorted(filenames),
                })
        print(f"Successfully loaded {len(responses)} scrape responses from NDJSON")
        return responses

    # TSV: detect slim vs legacy by header row
    with open(tsv_file, "r", encoding="utf-8") as f:
        first_line = f.readline().rstrip("\n").rstrip("\r")
        slim_header = ["filepath", "query", "response"]
        is_slim = first_line.split("\t")[:3] == slim_header

        if is_slim:
            for line_num, line in enumerate(f, 2):
                line = line.rstrip("\n").rstrip("\r")
                if not line.strip():
                    continue
                fields = line.split("\t")
                if len(fields) < 3:
                    print(f"Warning: Insufficient columns in row {line_num}")
                    continue
                filepath, query, response = fields[0], fields[1], "\t".join(fields[2:])
                query = query.strip()
                response = response.strip()
                if not query or not response:
                    print(f"Warning: Empty query or response in row {line_num}")
                    continue
                filenames = _normalize_filenames(filepath)
                responses.append({
                    "row_number": line_num,
                    "query": query,
                    "response": response,
                    "filenames": sorted(filenames),
                })
            print(f"Successfully loaded {len(responses)} scrape responses from slim TSV")
            return responses

        # Legacy format — first line is data, not a header. Re-process it too.
        all_lines = [first_line] + f.readlines()

    for line_num, line in enumerate(all_lines, 1):
        line = line.rstrip('\n').rstrip('\r').strip()
        if not line:
            continue

        # Split by tab to get columns
        fields = line.split('\t')
        if len(fields) < 7:  # Need at least 7 columns (0-6)
            print(f"Warning: Insufficient columns in row {line_num}")
            continue

        # Column 0 has the query conversation, column 6 has the result with SydneyReply
        # If there are extra columns (tabs embedded in JSON text), try to
        # reconstruct by finding the valid JSON boundaries
        if len(fields) == 7:
            query_json = fields[0]
            result_json = fields[6]
        else:
            query_json = None
            result_json = None
            for end_col in range(1, len(fields) - 5):
                candidate = '\t'.join(fields[:end_col])
                try:
                    json.loads(candidate)
                    query_json = candidate
                    result_json = fields[-1]
                    break
                except json.JSONDecodeError:
                    continue
            if query_json is None:
                print(f"Warning: Could not reconstruct JSON columns in row {line_num}")
                continue

        extracted = extract_response_from_tsv_row(query_json, result_json)

        if extracted:
            responses.append({
                'row_number': line_num,
                'query': extracted['query'],
                'response': extracted['response'],
                'filenames': extracted.get('filenames', [])
            })
        else:
            print(f"Warning: Could not extract query/response from row {line_num}")

    print(f"Successfully loaded {len(responses)} ChatGPT responses from TSV")
    return responses


def normalize_text(text: str) -> str:
    """
    Normalize text for better matching by handling encoding issues,
    removing extra whitespace, and standardizing characters.
    """
    if not text:
        return ""
    
    # Handle common encoding issues
    text = text.replace('�', "'")  # Replace unknown characters with apostrophe
    text = text.replace('"', '"').replace('"', '"')  # Normalize quotes
    text = text.replace(''', "'").replace(''', "'")  # Normalize apostrophes
    text = text.replace('–', '-').replace('—', '-')  # Normalize dashes
    text = text.replace('…', '...')  # Normalize ellipsis
    
    # Normalize unicode characters
    text = unicodedata.normalize('NFKD', text)
    
    # Remove extra whitespace and convert to lowercase
    text = re.sub(r'\s+', ' ', text.strip().lower())
    
    # Remove common punctuation that might cause issues
    text = re.sub(r'[^\w\s\-\.\,\?\!\:\;\(\)\[\]]', '', text)
    
    return text


def normalize_filepath(filepath) -> tuple:
    """
    Normalize a filepath value to a sorted tuple for consistent comparison.
    Handles both single string and list of strings (multi-file queries).
    Returns an empty tuple if filepath is None or empty.
    """
    if not filepath:
        return ()
    if isinstance(filepath, str):
        return (filepath,)
    if isinstance(filepath, (list, tuple)):
        return tuple(sorted(filepath))
    return (str(filepath),)


def filepaths_match(fp1, fp2) -> bool:
    """
    Check if two filepath values refer to the same set of documents.
    Both can be strings, lists, or tuples. Empty values never match.
    """
    norm1 = normalize_filepath(fp1)
    norm2 = normalize_filepath(fp2)
    if not norm1 or not norm2:
        return False
    return norm1 == norm2


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using multiple methods.
    Returns a score between 0 and 1.
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalize both texts
    norm_text1 = normalize_text(text1)
    norm_text2 = normalize_text(text2)
    
    if norm_text1 == norm_text2:
        return 1.0
    
    # Method 1: SequenceMatcher (overall similarity)
    seq_similarity = SequenceMatcher(None, norm_text1, norm_text2).ratio()
    
    # Method 2: Substring matching with length consideration
    if norm_text1 in norm_text2 or norm_text2 in norm_text1:
        length_ratio = min(len(norm_text1), len(norm_text2)) / max(len(norm_text1), len(norm_text2))
        substring_similarity = length_ratio
    else:
        substring_similarity = 0.0
    
    # Method 3: Word-level similarity (for partial matches)
    words1 = set(norm_text1.split())
    words2 = set(norm_text2.split())
    if words1 and words2:
        word_intersection = len(words1.intersection(words2))
        word_union = len(words1.union(words2))
        word_similarity = word_intersection / word_union if word_union > 0 else 0.0
    else:
        word_similarity = 0.0
    
    # Method 4: Longest common subsequence similarity
    def lcs_length(s1, s2):
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1] + 1
                else:
                    dp[i][j] = max(dp[i-1][j], dp[i][j-1])
        return dp[m][n]
    
    lcs_sim = 2 * lcs_length(norm_text1, norm_text2) / (len(norm_text1) + len(norm_text2)) if (len(norm_text1) + len(norm_text2)) > 0 else 0.0
    
    # Combine similarities with weights
    combined_similarity = (
        0.4 * seq_similarity +
        0.3 * substring_similarity +
        0.2 * word_similarity +
        0.1 * lcs_sim
    )
    
    return min(combined_similarity, 1.0)


def save_unmatched_analysis(unmatched_queries: List[QueryItem], unmatched_responses: List[Dict[str, Any]], output_prefix: str, responses: List[Dict[str, Any]]):
    """Save detailed analysis of unmatched queries and responses with similarity scores."""
    
    # Save unmatched queries with best matches found
    # NOTE: Uses fast word-overlap (Jaccard) instead of expensive LCS/SequenceMatcher.
    # LCS on 34 unmatched × 162 responses with ~1400-char queries takes ~47 minutes.
    # Jaccard gives equivalent best-match ranking in milliseconds.
    unmatched_queries_file = f"{output_prefix}_unmatched_queries.json"
    with open(unmatched_queries_file, 'w', encoding='utf-8') as f:
        unmatched_data = []
        for query in unmatched_queries:
            best_match = None
            best_similarity = 0
            
            query_words = set(normalize_text(query.query).split())
            for response in responses:
                resp_words = set(normalize_text(response['query']).split())
                if query_words and resp_words:
                    intersection = len(query_words & resp_words)
                    union = len(query_words | resp_words)
                    similarity = intersection / union if union > 0 else 0.0
                else:
                    similarity = 0.0
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = {
                        'row_number': response['row_number'],
                        'query': response['query'],
                        'similarity': round(similarity, 4)
                    }
            
            unmatched_data.append({
                'id': query.id,
                'filepath': query.filepath,
                'query': query.query,
                'gold': query.gold,
                'feature': query.feature,
                'number_of_pages': query.number_of_pages,
                'question_level': query.question_level,
                'best_match_found': best_match
            })
        json.dump(unmatched_data, f, indent=2, ensure_ascii=False)
    
    # Save unmatched responses
    unmatched_responses_file = f"{output_prefix}_unmatched_responses.json"
    with open(unmatched_responses_file, 'w', encoding='utf-8') as f:
        unmatched_data = []
        for response in unmatched_responses:
            entry = {
                'row_number': response['row_number'],
                'query': response['query'],
                'response_preview': response['response'][:500] + "..." if len(response['response']) > 500 else response['response']
            }
            if response.get('filenames'):
                entry['filenames'] = response['filenames']
            unmatched_data.append(entry)
        json.dump(unmatched_data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved unmatched analysis:")
    print(f"  - Unmatched queries: {unmatched_queries_file}")
    print(f"  - Unmatched responses: {unmatched_responses_file}")


def _make_processing_output(query: 'QueryItem', response_text: str, success: bool, error: str = None) -> 'ProcessingOutput':
    """Helper to create a ProcessingOutput from a QueryItem."""
    return ProcessingOutput(
        id=query.id,
        filepath=query.filepath,
        query=query.query,
        gold=query.gold,
        model="unknown",  # Overwritten by caller with actual model name
        answer=response_text,
        processing_time=0.0,
        success=success,
        error=error,
        feature=query.feature,
        number_of_pages=query.number_of_pages,
        question_level=query.question_level,
        question_level2=query.question_level2,
        size=query.size,
        sharepointurl=query.sharepointurl,
        downloadurl=query.downloadurl,
        domain1=query.domain1,
        domain2=query.domain2,
        filetype=query.filetype
    )


def match_queries_to_responses(queries: List[QueryItem], responses: List[Dict[str, Any]]) -> List[ProcessingOutput]:
    """Match original queries to ChatGPT responses based on question text and filepath.
    
    Matching strategy:
      Phase 1a: Exact match on (normalized query text + filepath) — highest confidence
      Phase 1b: Exact match on normalized query text only — fallback for queries
                where TSV has no filepath or filepath doesn't match
      Phase 2:  Fuzzy match with filepath preference — for remaining unmatched queries
    """
    matched_results = []
    unmatched_queries = []
    unmatched_responses = []
    
    # Create a set to track which responses have been matched
    matched_response_indices: Set[int] = set()
    
    # Check if any responses carry filepath information
    responses_have_filepaths = any(r.get('filenames') for r in responses)
    
    print(f"Matching {len(queries)} queries to {len(responses)} responses...")
    if responses_have_filepaths:
        print(f"  (filepath-aware matching enabled)")
    
    # Build lookup maps
    # Map 1: compound key (normalized_query, filepath_tuple) -> list of indices
    compound_response_map: Dict[tuple, List[int]] = {}
    # Map 2: query-only key normalized_query -> list of indices
    normalized_response_map: Dict[str, List[int]] = {}
    
    for i, response in enumerate(responses):
        norm_key = normalize_text(response['query'])
        # Query-only map (always populated)
        if norm_key not in normalized_response_map:
            normalized_response_map[norm_key] = []
        normalized_response_map[norm_key].append(i)
        # Compound map (only when TSV has filenames)
        resp_fp = normalize_filepath(response.get('filenames'))
        if resp_fp:
            compound_key = (norm_key, resp_fp)
            if compound_key not in compound_response_map:
                compound_response_map[compound_key] = []
            compound_response_map[compound_key].append(i)
    
    exact_match_count = 0
    filepath_match_count = 0
    fuzzy_queries = []  # Queries that need fuzzy matching
    
    for query in queries:
        norm_query = normalize_text(query.query)
        query_fp = normalize_filepath(query.filepath)
        
        found = False
        
        # Phase 1a: Try compound key (query + filepath) first
        if query_fp and responses_have_filepaths:
            compound_key = (norm_query, query_fp)
            if compound_key in compound_response_map:
                for idx in compound_response_map[compound_key]:
                    if idx not in matched_response_indices:
                        matched_response_indices.add(idx)
                        result = _make_processing_output(
                            query, responses[idx]['response'], True
                        )
                        matched_results.append(result)
                        exact_match_count += 1
                        filepath_match_count += 1
                        found = True
                        break
        
        # Phase 1b: Fall back to query-text-only match
        if not found and norm_query in normalized_response_map:
            for idx in normalized_response_map[norm_query]:
                if idx not in matched_response_indices:
                    matched_response_indices.add(idx)
                    result = _make_processing_output(
                        query, responses[idx]['response'], True
                    )
                    matched_results.append(result)
                    exact_match_count += 1
                    found = True
                    break
        
        if not found:
            fuzzy_queries.append(query)
    
    fp_info = f" ({filepath_match_count} by filepath)" if filepath_match_count else ""
    print(f"Phase 1 (exact match): {exact_match_count}/{len(queries)} matched{fp_info}")
    print(f"Phase 2 (fuzzy match): {len(fuzzy_queries)} remaining queries...")
    
    # Phase 2: Fuzzy matching for remaining unmatched queries
    # When filepaths are available, prefer responses with matching filepath
    for query in tqdm(fuzzy_queries, desc="Fuzzy matching"):
        query_fp = normalize_filepath(query.filepath)
        best_match_idx = None
        best_similarity = 0
        best_has_fp_match = False
        
        for i, response in enumerate(responses):
            if i in matched_response_indices:
                continue
            
            similarity = calculate_similarity(query.query, response['query'])
            
            if similarity <= 0.6:
                continue
            
            # Check filepath match
            resp_fp = normalize_filepath(response.get('filenames'))
            has_fp_match = bool(query_fp and resp_fp and query_fp == resp_fp)
            
            # Prefer filepath match over higher text similarity without filepath
            if has_fp_match and not best_has_fp_match:
                # Filepath match always wins over non-filepath match
                best_match_idx = i
                best_similarity = similarity
                best_has_fp_match = True
            elif has_fp_match == best_has_fp_match and similarity > best_similarity:
                # Same filepath status — pick higher text similarity
                best_match_idx = i
                best_similarity = similarity
                best_has_fp_match = has_fp_match
        
        if best_match_idx is not None:
            matched_response_indices.add(best_match_idx)
            result = _make_processing_output(
                query, responses[best_match_idx]['response'], True
            )
            matched_results.append(result)
        else:
            unmatched_queries.append(query)
            result = _make_processing_output(
                query, "", False, "No matching ChatGPT response found"
            )
            matched_results.append(result)
    
    # Track unmatched responses
    for i, response in enumerate(responses):
        if i not in matched_response_indices:
            unmatched_responses.append(response)
    
    print(f"Matching complete:")
    print(f"  - Successfully matched: {len(matched_results) - len(unmatched_queries)}")
    print(f"  - Unmatched queries: {len(unmatched_queries)}")
    print(f"  - Unmatched responses: {len(unmatched_responses)}")
    
    if unmatched_queries:
        print(f"\nFirst few unmatched queries:")
        for i, query in enumerate(unmatched_queries[:3]):
            fp_str = query.filepath if isinstance(query.filepath, str) else ', '.join(query.filepath) if query.filepath else 'N/A'
            print(f"  {i+1}. ID: {query.id}, File: {fp_str[:60]}, Query: {query.query[:80]}...")
    
    if unmatched_responses:
        print(f"\nFirst few unmatched responses:")
        for i, response in enumerate(unmatched_responses[:3]):
            fp_str = ', '.join(response.get('filenames', [])) or 'N/A'
            print(f"  {i+1}. Row: {response['row_number']}, File: {fp_str[:60]}, Query: {response['query'][:80]}...")
    
    return matched_results, unmatched_queries, unmatched_responses


def save_results_to_ndjson(results: List[ProcessingOutput], output_file: str):
    """Save results to NDJSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in results:
            json.dump(asdict(result), f, ensure_ascii=False)
            f.write('\n')
    print(f"Saved {len(results)} results to {output_file}")


def get_output_structure(input_file: str, output_base_dir: str = "Output", model_name: str = "unknown", output_dir_name: str = None) -> Dict[str, str]:
    """Create output directory structure based on input file name and model.
    
    Args:
        output_dir_name: Optional custom folder name under output_base_dir. If provided, uses this instead of auto-generated name.
    """
    # Get the base name without extension
    input_name = Path(input_file).stem
    
    # Create output folder name with input file and model
    output_folder_name = output_dir_name if output_dir_name else f"{input_name}_{model_name}"
    output_dir = Path(output_base_dir) / output_folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create plots subdirectory
    plots_dir = output_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    
    return {
        "output_dir": str(output_dir),
        "plots_dir": str(plots_dir),
        "results_file": str(output_dir / f"{input_name}_results.ndjson"),
        "evaluation_file": str(output_dir / f"{input_name}_evaluation.ndjson"),
        "metrics_file": str(output_dir / f"{input_name}_metrics.json")
    }


def find_input_file(input_filename: str) -> str:
    """Find input NDJSON, checking Input/Query/ then Input/."""
    if os.path.exists(input_filename):
        return input_filename
    # If it's a bare filename, try Input/Query/ first, then Input/ for back-compat.
    if os.path.basename(input_filename) == input_filename:
        for candidate in (os.path.join('Input', 'Query', input_filename),
                          os.path.join('Input', input_filename)):
            if os.path.exists(candidate):
                return candidate
    raise ValueError(f"Input file not found: {input_filename}")


def find_chatgpt_tsv_file(tsv_filename: str = None, chatgpt_directory: str = None) -> str:
    """Find scrape file (NDJSON preferred, then TSV) in `chatgpt_directory`.

    If `tsv_filename` is given and exists, it is used directly.
    Otherwise the directory is scanned: NDJSON/JSONL files are preferred over
    TSV; the largest matching file is returned.
    """
    if tsv_filename and os.path.exists(tsv_filename):
        return tsv_filename

    # Default to Input/Scrape/ if no directory was provided.
    if not chatgpt_directory:
        default_scrape = os.path.join('Input', 'Scrape')
        if os.path.isdir(default_scrape):
            chatgpt_directory = default_scrape

    if chatgpt_directory:
        chatgpt_dir = Path(chatgpt_directory)
        if not chatgpt_dir.exists() or not chatgpt_dir.is_dir():
            raise ValueError(f"Directory not found: {chatgpt_directory}")
        ndjson_files = list(chatgpt_dir.glob("*.ndjson")) + list(chatgpt_dir.glob("*.jsonl"))
        if ndjson_files:
            return str(max(ndjson_files, key=lambda f: f.stat().st_size))
        tsv_files = list(chatgpt_dir.glob("*.tsv"))
        if tsv_files:
            return str(max(tsv_files, key=lambda f: f.stat().st_size))
        raise ValueError(f"No .ndjson/.jsonl/.tsv files found in: {chatgpt_directory}")
    
    # Look for TSV files matching the pattern Word_*_chatgpt_*/*.tsv or PowerPoint_*_chatgpt_*/*.tsv
    current_dir = Path(".")
    chatgpt_dirs = list(current_dir.glob("*_chatgpt_*"))
    
    for chatgpt_dir in sorted(chatgpt_dirs, reverse=True):  # Most recent first
        tsv_files = [
            f for f in chatgpt_dir.glob("*.tsv")
            if f.name.endswith("_result.tsv")
            or f.name.endswith("_conversation.tsv")
        ]
        if tsv_files:
            return str(max(tsv_files, key=lambda f: f.stat().st_size))
    
    raise ValueError(
        "No ChatGPT TSV file found. Expected pattern: "
        "*_chatgpt_*/*_result.tsv or *_conversation.tsv"
    )


def find_all_tsv_files(chatgpt_directory: str) -> List[str]:
    """Find all scrape files (NDJSON/JSONL/TSV) in the specified directory."""
    chatgpt_dir = Path(chatgpt_directory)
    if not chatgpt_dir.exists() or not chatgpt_dir.is_dir():
        raise ValueError(f"Directory not found: {chatgpt_directory}")

    files = (
        list(chatgpt_dir.glob("*.ndjson"))
        + list(chatgpt_dir.glob("*.jsonl"))
        + list(chatgpt_dir.glob("*.tsv"))
    )
    if not files:
        raise ValueError(
            f"No .ndjson/.jsonl/.tsv scrape files found in directory: {chatgpt_directory}"
        )
    return [str(f) for f in sorted(files)]


def extract_model_name_from_tsv(tsv_path: str) -> str:
    """
    Extract model name from TSV filename.
    
    Expected patterns:
    - OfficeBench_PPTQnA_FileFidelity_0128_ChatGptPlus_16595_result.tsv -> ChatGptPlus
    - OfficeBench_PPTQnA_FileFidelity_0128_Gemini_16594_result.tsv -> Gemini
    - OfficeBench_PPTQnA_FileFidelity_0128_WorkCopilot_16643_result.tsv -> WorkCopilot
    - OfficeBench_PPTQnA_FileFidelity_0128_CwCCopilot_16644_result.tsv -> CwCCopilot
    """
    filename = Path(tsv_path).stem  # Remove .tsv extension
    
    # Common model name patterns to look for
    known_models = [
        "ChatGptPlus", "ChatGPT", "GPT",
        "Gemini", "GeminiPro", "Gemini2",
        "WorkCopilot", "CwCCopilot", "Copilot",
        "Claude", "ClaudeOpus", "ClaudeSonnet",
        "OpenAI", "GPT4", "GPT5"
    ]
    
    # Try to find a known model name in the filename
    for model in known_models:
        if model.lower() in filename.lower():
            # Extract the actual case-sensitive model name from filename
            pattern = re.compile(re.escape(model), re.IGNORECASE)
            match = pattern.search(filename)
            if match:
                # Get the surrounding context to capture full model name
                start = match.start()
                # Find the word boundary
                parts = filename.split('_')
                for part in parts:
                    if model.lower() in part.lower():
                        return part
    
    # Fallback: try to extract model name based on common patterns
    # Pattern: <prefix>_<ModelName>_<numbers>_result
    parts = filename.replace('_result', '').split('_')
    
    # Look for parts that look like model names (mixed case, no pure numbers)
    for part in reversed(parts):  # Check from end, model names often near the end
        if part and not part.isdigit() and not part.isupper():
            # Skip parts that look like dataset names (all uppercase or dates)
            if any(c.isupper() and any(c.islower() for c in part) for c in part):
                return part
    
    # Last resort: use a sanitized version of the filename
    return filename.replace('_result', '').split('_')[-2] if len(parts) > 1 else "unknown"


async def process_single_tsv(
    input_file: str,
    tsv_file: str,
    queries: List[QueryItem],
    evaluate: bool,
    eval_majority_vote: bool,
    eval_models: Optional[Dict[str, str]],
    model_name: str,
    max_concurrent: int = 3,
    prompt_template: str = "domain",
    output_dir_name: str = None
) -> Dict[str, Any]:
    """Process a single TSV file and return results summary."""
    print(f"\n{'='*60}")
    print(f"Processing TSV: {Path(tsv_file).name}")
    print(f"Model: {model_name}")
    print(f"{'='*60}")
    
    try:
        # Get output structure with model-specific directory
        output_structure = get_output_structure(input_file, model_name=model_name, output_dir_name=output_dir_name)
        print(f"Output directory: {output_structure['output_dir']}")
        
        # Load ChatGPT TSV responses
        print("Loading TSV responses...")
        responses = load_chatgpt_tsv_responses(tsv_file)
        
        # Match queries to responses
        print("Matching queries to responses...")
        results, unmatched_queries, unmatched_responses = match_queries_to_responses(queries, responses)
        
        # Update model name in results
        for result in results:
            result.model = model_name
        
        # Save unmatched analysis
        if unmatched_queries or unmatched_responses:
            output_prefix = Path(output_structure['results_file']).stem
            output_dir = Path(output_structure['output_dir'])
            save_unmatched_analysis(unmatched_queries, unmatched_responses, str(output_dir / output_prefix), responses)
        
        # Save processing results
        print("Saving processing results...")
        save_results_to_ndjson(results, output_structure['results_file'])
        
        evaluation_results = []
        
        # Run evaluation if requested
        if evaluate:
            print("Running evaluation...")
            
            # Show evaluation mode info
            if eval_majority_vote:
                models_str = ", ".join([f"{k}={v}" for k, v in (eval_models or {}).items()])
                print(f"  Mode: Multi-LLM majority voting")
                if models_str:
                    print(f"  Models: {models_str}")
            else:
                print(f"  Mode: Single-model evaluation")
            
            # Filter only successful results for evaluation
            successful_results = [r for r in results if r.success and r.answer.strip()]
            
            if successful_results:
                # Convert dataclass objects to dictionaries for evaluation
                successful_dicts = [asdict(result) for result in successful_results]
                
                # Evaluate using multi-LLM or single-model based on flag
                if eval_majority_vote:
                    evaluation_results = await evaluate_batch_results_with_multi_llm(
                        successful_dicts,
                        max_concurrent=max_concurrent,
                        use_majority_voting=True,
                        eval_models=eval_models
                    )
                else:
                    evaluation_results = await evaluate_batch_results_with_accuracy_prompt(successful_dicts, max_concurrent=max_concurrent)
                
                # Save evaluation results
                save_evaluation_results(evaluation_results, output_structure['evaluation_file'])
                print(f"Saved {len(evaluation_results)} evaluation results to {output_structure['evaluation_file']}")
                
                # Create categorized metrics
                print("Creating categorized metrics...")
                all_result_dicts = [asdict(r) for r in results]
                metrics = calculate_categorized_accuracy_metrics(evaluation_results, all_result_dicts)
                
                save_categorized_metrics(metrics, output_structure['metrics_file'])
                print(f"Saved categorized metrics to {output_structure['metrics_file']}")
                
                # Generate plots automatically
                print("Generating plots...")
                import subprocess
                import sys
                try:
                    subprocess.run([
                        sys.executable, 
                        "visualize_categorized_metrics.py", 
                        "--input", output_structure['metrics_file']
                    ], check=True, cwd=Path(__file__).parent)
                    print("Plots generated successfully")
                except subprocess.CalledProcessError as e:
                    print(f"Warning: Failed to generate plots: {e}")
            else:
                print("No successful results found for evaluation")
        
        successful_count = len([r for r in results if r.success])
        return {
            "tsv_file": tsv_file,
            "model": model_name,
            "total_queries": len(results),
            "successful": successful_count,
            "failed": len(results) - successful_count,
            "evaluated": len(evaluation_results),
            "output_dir": output_structure['output_dir'],
            "success": True,
            "error": None
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "tsv_file": tsv_file,
            "model": model_name,
            "total_queries": 0,
            "successful": 0,
            "failed": 0,
            "evaluated": 0,
            "output_dir": None,
            "success": False,
            "error": str(e)
        }


async def main():
    """Main function to process ChatGPT TSV responses."""
    parser = argparse.ArgumentParser(
        description="Process ChatGPT TSV responses and evaluate them",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Default Behavior:
- Input NDJSONs:    Input/Query/*.ndjson
- Input scrapes:    Input/Scrape/*.tsv (slim format: filepath\\tquery\\tresponse)
- Output:           Output/<run-name>/
- Evaluation:       runs eval + metrics + plots when --evaluate is set

Examples:
  # Run with the bundled sample
  python compete_tsv_response_processor.py \\
    --input OfficeBenchmark_DomainQnA_0505_NoWS_NoCl_NoFC.ndjson \\
    --scrape-directory Input/Scrape --evaluate

  # Point at a specific scrape file (NDJSON or TSV)
  python compete_tsv_response_processor.py \\
    --input OfficeBenchmark_DomainQnA_0505_NoWS_NoCl_NoFC.ndjson \\
    --tsv-file Input/Scrape/sample_conversations.ndjson --evaluate

  # Multi-LLM majority voting
  python compete_tsv_response_processor.py \\
    --input OfficeBenchmark_DomainQnA_0505_NoWS_NoCl_NoFC.ndjson \\
    --scrape-directory Input/Scrape --evaluate --eval-majority-vote
        """
    )

    parser.add_argument(
        "--input", "-i",
        default="OfficeBenchmark_DomainQnA_0505_NoWS_NoCl_NoFC.ndjson",
        help="Input NDJSON file (searches in Input/Query/ then Input/)"
    )
    
    parser.add_argument(
        "--tsv-file",
        help="Scrape file (.ndjson, .jsonl, or .tsv) with responses (auto-discovers if not specified)"
    )
    
    parser.add_argument(
        "--scrape-directory",
        help="Directory containing scrape files (.ndjson/.jsonl/.tsv); alternative to --tsv-file"
    )
    
    parser.add_argument(
        "--process-all",
        action="store_true",
        help="Process ALL TSV files in the --scrape-directory (creates separate output for each model)"
    )
    
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Process TSV files in parallel when using --process-all (default: sequential)"
    )
    
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Custom output folder name under Output/ (default: auto-generated from input filename and model)"
    )
    
    parser.add_argument(
        "--evaluate",
        action="store_true",
        default=True,
        help="Run evaluation on the responses (default: True)"
    )
    
    parser.add_argument(
        "--eval-majority-vote",
        action="store_true",
        help="Use multi-LLM majority voting for evaluation (GPT-5.4, Gemini 3.1 Pro Preview, Claude 4.6 Opus)"
    )
    
    parser.add_argument(
        "--eval-gpt-model",
        default="gpt-5.4",
        help="GPT model for evaluation (default: gpt-5.4)"
    )
    
    parser.add_argument(
        "--eval-gemini-model",
        default="gemini-3.1-pro-preview",
        help="Gemini model for evaluation (default: gemini-3.1-pro-preview)"
    )
    
    parser.add_argument(
        "--eval-claude-model",
        default="claude-opus-4-6",
        help="Claude model for evaluation (default: claude-opus-4-6)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of queries to process (default: all)"
    )
    
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=3,
        help="Maximum number of concurrent evaluations (default: 3)"
    )
    
    args = parser.parse_args()
    
    # Build evaluation models dict from arguments
    eval_models = None
    if args.eval_majority_vote:
        eval_models = {
            "gpt": args.eval_gpt_model,
            "gemini": args.eval_gemini_model,
            "claude": args.eval_claude_model
        }
    
    start_time = time.time()
    
    try:
        # Find input file
        print("Finding input file...")
        input_file = find_input_file(args.input)
        print(f"Using input file: {input_file}")
        
        # Load original queries once (shared across all TSV files)
        print("Loading original queries...")
        queries = load_queries_from_ndjson(input_file)
        print(f"Loaded {len(queries)} queries")
        
        # Apply limit if specified
        if args.limit and args.limit < len(queries):
            queries = queries[:args.limit]
            print(f"Limited to {len(queries)} queries (--limit {args.limit})")
        
        # Check if processing all TSV files in directory
        if args.process_all:
            if not args.scrape_directory:
                raise ValueError("--process-all requires --scrape-directory to be specified")
            
            print(f"\n{'#'*60}")
            print(f"BATCH PROCESSING MODE: Processing all TSV files")
            print(f"{'#'*60}")
            
            # Find all TSV files
            tsv_files = find_all_tsv_files(args.scrape_directory)
            print(f"Found {len(tsv_files)} TSV files to process:")
            for tsv_file in tsv_files:
                model_name = extract_model_name_from_tsv(tsv_file)
                print(f"  - {Path(tsv_file).name} -> Model: {model_name}")
            
            # Process each TSV file
            if args.parallel:
                print(f"\nRunning in PARALLEL mode ({len(tsv_files)} files concurrently)...")
                tasks = []
                for tsv_file in tsv_files:
                    model_name = extract_model_name_from_tsv(tsv_file)
                    tasks.append(process_single_tsv(
                        input_file=input_file,
                        tsv_file=tsv_file,
                        queries=queries,
                        evaluate=args.evaluate,
                        eval_majority_vote=args.eval_majority_vote,
                        eval_models=eval_models,
                        model_name=model_name,
                        max_concurrent=args.max_concurrent,
                        prompt_template="domain",
                        output_dir_name=args.output_dir
                    ))
                all_results = await asyncio.gather(*tasks)
                all_results = list(all_results)
            else:
                print(f"\nRunning in SEQUENTIAL mode...")
                all_results = []
                for tsv_file in tsv_files:
                    model_name = extract_model_name_from_tsv(tsv_file)
                    result = await process_single_tsv(
                        input_file=input_file,
                        tsv_file=tsv_file,
                        queries=queries,
                        evaluate=args.evaluate,
                        eval_majority_vote=args.eval_majority_vote,
                        eval_models=eval_models,
                        model_name=model_name,
                        max_concurrent=args.max_concurrent,
                        prompt_template="domain",
                        output_dir_name=args.output_dir
                    )
                    all_results.append(result)
            
            # Print summary
            print(f"\n{'#'*60}")
            print(f"BATCH PROCESSING COMPLETE")
            print(f"{'#'*60}")
            print(f"Total TSV files processed: {len(all_results)}")
            print(f"Total processing time: {time.time() - start_time:.2f} seconds")
            print()
            
            # Summary table
            print(f"{'Model':<20} {'Status':<10} {'Matched':<10} {'Evaluated':<10} {'Output Directory'}")
            print("-" * 80)
            for result in all_results:
                status = "SUCCESS" if result['success'] else "FAILED"
                matched = f"{result['successful']}/{result['total_queries']}"
                evaluated = str(result['evaluated'])
                output_dir = result['output_dir'] or "N/A"
                print(f"{result['model']:<20} {status:<10} {matched:<10} {evaluated:<10} {output_dir}")
            
            # Check for failures
            failures = [r for r in all_results if not r['success']]
            if failures:
                print(f"\nWarning: {len(failures)} TSV file(s) failed to process:")
                for f in failures:
                    print(f"  - {f['model']}: {f['error']}")
        
        else:
            # Original single-file processing logic
            # Find ChatGPT TSV file
            if args.tsv_file:
                tsv_file = args.tsv_file
            else:
                print("Auto-discovering ChatGPT TSV file...")
                tsv_file = find_chatgpt_tsv_file(chatgpt_directory=args.scrape_directory)
            print(f"Using ChatGPT TSV file: {tsv_file}")
            
            # Extract model name from TSV filename
            model_name = extract_model_name_from_tsv(tsv_file)
            print(f"Detected model: {model_name}")
            
            # Get output structure
            output_structure = get_output_structure(input_file, model_name=model_name, output_dir_name=args.output_dir)
            print(f"Output directory: {output_structure['output_dir']}")
            
            # Load ChatGPT TSV responses
            print("Loading ChatGPT TSV responses...")
            responses = load_chatgpt_tsv_responses(tsv_file)
            
            # Match queries to responses
            print("Matching queries to responses...")
            results, unmatched_queries, unmatched_responses = match_queries_to_responses(queries, responses)
            
            # Update model name in results
            for result in results:
                result.model = model_name
            
            # Save unmatched analysis
            if unmatched_queries or unmatched_responses:
                output_prefix = Path(output_structure['results_file']).stem
                output_dir = Path(output_structure['output_dir'])
                save_unmatched_analysis(unmatched_queries, unmatched_responses, str(output_dir / output_prefix), responses)
            
            # Save processing results
            print("Saving processing results...")
            save_results_to_ndjson(results, output_structure['results_file'])
            
            # Always run evaluation (default behavior)
            if args.evaluate:
                print("Running evaluation...")
                
                # Show evaluation mode info
                if args.eval_majority_vote:
                    models_str = ", ".join([f"{k}={v}" for k, v in (eval_models or {}).items()])
                    print(f"  Mode: Multi-LLM majority voting")
                    if models_str:
                        print(f"  Models: {models_str}")
                else:
                    print(f"  Mode: Single-model evaluation")
                
                # Filter only successful results for evaluation
                successful_results = [r for r in results if r.success and r.answer.strip()]
                
                if successful_results:
                    # Convert dataclass objects to dictionaries for evaluation
                    successful_dicts = []
                    for result in successful_results:
                        result_dict = asdict(result)
                        successful_dicts.append(result_dict)
                    
                    # Evaluate using multi-LLM or single-model based on flag
                    if args.eval_majority_vote:
                        evaluation_results = await evaluate_batch_results_with_multi_llm(
                            successful_dicts,
                            max_concurrent=args.max_concurrent,
                            use_majority_voting=True,
                            eval_models=eval_models
                        )
                    else:
                        evaluation_results = await evaluate_batch_results_with_accuracy_prompt(successful_dicts, max_concurrent=args.max_concurrent)
                    
                    # Save evaluation results
                    save_evaluation_results(evaluation_results, output_structure['evaluation_file'])
                    print(f"Saved {len(evaluation_results)} evaluation results to {output_structure['evaluation_file']}")
                    
                    # Create categorized metrics
                    print("Creating categorized metrics...")
                    # Convert all results to dicts for metrics calculation
                    all_result_dicts = [asdict(r) for r in results]
                    metrics = calculate_categorized_accuracy_metrics(evaluation_results, all_result_dicts)
                    
                    save_categorized_metrics(metrics, output_structure['metrics_file'])
                    print(f"Saved categorized metrics to {output_structure['metrics_file']}")
                    
                    # Generate plots automatically
                    print("Generating plots...")
                    # Use subprocess to call the visualization script
                    import subprocess
                    import sys
                    try:
                        subprocess.run([
                            sys.executable, 
                            "visualize_categorized_metrics.py", 
                            "--input", output_structure['metrics_file']
                        ], check=True, cwd=Path(__file__).parent)
                        print("Plots generated successfully")
                    except subprocess.CalledProcessError as e:
                        print(f"Warning: Failed to generate plots: {e}")
                else:
                    print("No successful results found for evaluation")
            
            print("Processing completed successfully!")
            print(f"Total processing time: {time.time() - start_time:.2f} seconds")
            print(f"Successfully processed: {len([r for r in results if r.success])}/{len(results)} queries")
            print(f"Results saved to: {output_structure['output_dir']}")
        
    except Exception as e:
        print(f"Error in processing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
