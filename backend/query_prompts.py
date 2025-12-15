#!/usr/bin/env python3
"""Query prompts used in evaluations."""

import sqlite3

def get_prompts_for_evaluation(evaluation_id):
    """Get all prompts used for a specific evaluation."""
    conn = sqlite3.connect('grader.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            cs.id,
            cs.name as criterion_name,
            cs.score,
            cs.max_score,
            cs.prompt_used
        FROM criterion_scores cs
        WHERE cs.evaluation_id = ?
        ORDER BY cs.id
    """, (evaluation_id,))
    
    results = cursor.fetchall()
    conn.close()
    
    return results

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python query_prompts.py <evaluation_id>")
        sys.exit(1)
    
    eval_id = int(sys.argv[1])
    prompts = get_prompts_for_evaluation(eval_id)
    
    print(f"\nPrompts for Evaluation #{eval_id}")
    print("=" * 80)
    
    for row in prompts:
        print(f"\nCriterion: {row['criterion_name']}")
        print(f"Score: {row['score']}/{row['max_score']}")
        print(f"\nPrompt Used:")
        print("-" * 80)
        print(row['prompt_used'] or "No prompt stored (evaluation created before prompt storage was added)")
        print("=" * 80)
