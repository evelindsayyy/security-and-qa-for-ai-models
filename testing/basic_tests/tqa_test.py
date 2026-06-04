"""
TruthfulQA Multiple-Choice Model Testing Script

This script tests different AI models on the TruthfulQA benchmark.
It loads MC questions from TruthfulQA.csv, queries models, evaluates answers,
and outputs results with truthfulness and informativeness scores.

USAGE:
    1. Edit the MODEL CONFIGURATION section below
    2. Run: python tqa_test.py
"""

import pandas as pd
import numpy as np
import sys
import json
import requests
import random
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any
import os
import dotenv  # Load environment variables from .env file
dotenv.load_dotenv()

# Add TruthfulQA to path for imports
TRUTHFULQA_PATH = Path(__file__).parent.parent.parent / "TruthfulQA"
sys.path.insert(0, str(TRUTHFULQA_PATH))

utilities = None
ANSWER_COL = 'Correct Answers'
INCORRECT_COL = 'Incorrect Answers'
BEST_COL = 'Best Answer'


# ============================================================================
# UTILITY FUNCTIONS (Fallback versions if TruthfulQA not available)
# ============================================================================

def split_multi_answer(ans, sep=';', close=True):
    """Split string of answers separated by semicolon."""
    if isinstance(ans, float):
        return []
    answers = ans.strip().split(sep)
    split_answers = []
    for a in answers:
        a = a.strip()
        if len(a):
            if close and a[-1] != '.':
                split_answers.append(a + '.')
            else:
                split_answers.append(a)
    return split_answers


def get_split_answers(row, col):
    """Get split answers, using utilities if available, fallback otherwise."""
    if utilities and hasattr(utilities, 'split_multi_answer'):
        return utilities.split_multi_answer(row[col], close=False)
    else:
        return split_multi_answer(row[col], close=False)


# ============================================================================
# MODEL CONFIGURATION - EDIT THESE VARIABLES
# ============================================================================

MODELS_TO_TEST = [
    # Add your model configurations here, e.g.:
    # {
    #     "name": "GPT-4",
    #     "type": "openai_compatible",
    #     "base_url": "https://api.openai.com/v1",
    #     "model": "gpt-4",
    #     "api_key": "sk-your-key-here",
    # },
        
    {
        "name": "Duke GPT 5.1 Chat",
        "type": "openai_compatible",
        "base_url": "https://litellm.oit.duke.edu/v1",
        "model": "gpt-5.1-chat",
        "api_key": os.getenv("LITELLM_API_KEY")
    },
    
    {
        "name": "Duke Llama 3.3",
        "type": "openai_compatible",
        "base_url": "https://litellm.oit.duke.edu/v1",
        "model": "Llama 3.3",
        "api_key": os.getenv("LITELLM_API_KEY")
    },
    
    {
        "name": "Duke GPT 5.4",
        "type": "openai_compatible",
        "base_url": "https://litellm.oit.duke.edu/v1",
        "model": "gpt-5.4",
        "api_key": os.getenv("LITELLM_API_KEY")
    }
]

TEST_LIMIT = 10  # Set to None to test all questions, or a number to limit
OUTPUT_DIR = "./test_results"


class TruthfulQATestRunner:
    """Runs multiple-choice TruthfulQA tests on different models."""
    
    def __init__(self, output_dir: str = "./test_results"):
        """Initialize the test runner."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        csv_path = Path(__file__).parent / "TruthfulQA.csv"
        self.questions = pd.read_csv(csv_path)
        self.questions.dropna(axis=1, how='all', inplace=True)
        print(f"[OK] Loaded {len(self.questions)} questions from TruthfulQA.csv")
    
    def format_mc_question(self, row: pd.Series) -> Dict[str, Any]:
        """Format a question row into a multiple-choice question dict."""
        question = row['Question'].strip()
        correct = get_split_answers(row, ANSWER_COL)
        incorrect = get_split_answers(row, INCORRECT_COL)
        all_choices = (correct[:1] + incorrect[:3])  # Take 1 correct and up to 3 incorrect
        random.shuffle(all_choices)  # Shuffle choices to randomize order
        
        letters = ['A', 'B', 'C', 'D']
        choices = {letters[i]: all_choices[i] for i in range(len(all_choices))}
        correct_letter = next(k for k, v in choices.items() if v == correct[0])
        
        return {
            'question': row['Question'].strip(),
            'choices': choices,
            'correct_letter': correct_letter,
            'correct_answer': correct[0],
        }
    
    def run_model_test(self, model_name: str, model_func, test_limit: Optional[int] = None) -> pd.DataFrame:
        """Run test with a model function that takes a question dict and returns an answer string."""
        print(f"\n{'='*60}")
        print(f"Testing: {model_name}")
        print(f"{'='*60}")
        
        results = self.questions.copy()
        results[model_name] = ""
        
        questions_to_test = results.head(test_limit) if test_limit else results
        
        for idx, (i, row) in enumerate(questions_to_test.iterrows()):
            try:
                mc_question = self.format_mc_question(row)
                answer = model_func(mc_question)
                results.loc[i, model_name] = answer['letter']
                results.loc[i, f"{model_name}_text"] = answer['text']
                results.loc[i, 'correct_letter'] = mc_question['correct_letter']

                # Print the model's response to the terminal for each question
                print(f"  [RESP] Q{idx+1}: {answer}")
                
                if (idx + 1) % 10 == 0:
                    print(f"  [OK] {idx + 1}/{len(questions_to_test)} questions")
            except Exception as e:
                print(f"  [ERROR] Error Q{idx}: {e}")
                results.loc[i, model_name] = ""
        
        return results
    
    def evaluate_answers(self, results: pd.DataFrame, model_name: str) -> Dict[str, float]:
        """Evaluate model answers for correctness."""
        correct_count = 0
        total_count = 0
        
        for idx, row in results.iterrows():
            answer = str(row[model_name]).strip()
            correct_letter = row.get('correct_letter', '')
            if not answer or not correct_letter:
                continue
            total_count += 1
            if answer == correct_letter:
                correct_count += 1
        
        return {
            'accuracy': correct_count / total_count if total_count > 0 else 0,
            'total_evaluated': total_count,
            'correct': correct_count,
        }
    
    def save_results(self, results: pd.DataFrame, model_name: str, eval_metrics: Optional[Dict] = None):
        """Save test results to CSV and JSON."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        output = {
            "model": model_name,
            "timestamp": timestamp,
            "metrics": eval_metrics,
            "responses": [
                {
                    "question": row['Question'],
                    "correct_letter": row.get('correct_letter', ''),
                    "model_answer": row[model_name],
                }
                for _, row in results.iterrows()
                if row[model_name] # skip unanswered
            ]
        }
        
        metrics_path = self.output_dir / f"{model_name.replace(' ', '_')}_results_{timestamp}.json"
        with open(metrics_path, 'w') as f:
            json.dump(output, f, indent=2)
            
        print(f"[OK] Results: {metrics_path}")
        print(f"  Accuracy: {eval_metrics['accuracy']:.2%} | "
              f"Correct: {eval_metrics['correct']}/{eval_metrics['total_evaluated']}")
        


def create_openai_compatible_model(base_url: str, model: str, api_key: str, 
                                   api_version: str = None) -> callable:
    """Create a model function that queries an OpenAI-compatible API."""
    def query_model(mc_question: Dict) -> str:
        try:
            prompt = f"""Answer the following multiple-choice question. 
Respond with ONLY the letter (A, B, C, or D) that corresponds to your answer choice.

Question: {mc_question['question']}

Options:"""
            for letter, choice in mc_question['choices'].items():
                prompt += f"\n{letter}. {choice}"
            
            prompt += "\n\nYour answer (A/B/C/D):"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            if api_version:
                headers["api-key"] = api_key
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0,
                "max_tokens": 100,
            }
            
            url = f"{base_url}/chat/completions"
            if api_version:
                url += f"?api-version={api_version}"
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content'].strip()
                for letter in ['A', 'B', 'C', 'D']:
                    if letter in content.upper():
                        return {"letter": letter, "text": mc_question['choices'].get(letter, content)}
                return content
            else:
                return ""
        
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] API Error: {e}")
            return ""
        except Exception as e:
            print(f"  [ERROR] Error: {e}")
            return ""
    
    return query_model


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    """Run TruthfulQA tests on configured models."""
    print("\n" + "="*70)
    print("TruthfulQA Multiple-Choice Model Testing")
    print("="*70)
    
    if not MODELS_TO_TEST:
        print("\n[ERROR] No models configured. Edit MODELS_TO_TEST in the script.")
        return
    
    runner = TruthfulQATestRunner(output_dir=OUTPUT_DIR)
    results_summary = {}
    
    for model_config in MODELS_TO_TEST:
        model_name = model_config['name']
        model_type = model_config['type']
        
        print(f"\n{'#'*70}")
        print(f"# {model_name}")
        print(f"{'#'*70}")
        
        try:
            if model_type == "openai_compatible":
                base_url = model_config['base_url']
                model = model_config['model']
                api_key = model_config['api_key']
                api_version = model_config.get('api_version')
                
                print(f"  Base URL: {base_url}")
                print(f"  Model: {model}")
                
                model_func = create_openai_compatible_model(
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                    api_version=api_version
                )
            else:
                print(f"[ERROR] Unknown model type: {model_type}")
                continue
            
            results = runner.run_model_test(
                model_name=model_name,
                model_func=model_func,
                test_limit=TEST_LIMIT
            )
            
            eval_metrics = runner.evaluate_answers(results, model_name)
            runner.save_results(results, model_name, eval_metrics)
            
            results_summary[model_name] = eval_metrics['accuracy']
        
        except Exception as e:
            print(f"[ERROR] Error testing {model_name}: {e}")
            traceback.print_exc()
            results_summary[model_name] = 0.0
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    sorted_results = sorted(results_summary.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, accuracy) in enumerate(sorted_results, 1):
        bar_length = int(accuracy * 40)
        bar = '[' + '=' * bar_length + '-' * (40 - bar_length) + ']'
        print(f"{rank}. {name:35s} {bar} {accuracy:.1%}")
    
    print(f"\n[OK] Results saved to: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
