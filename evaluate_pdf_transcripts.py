"""
Evaluate transcripts from PDF files using a structured 4-stage pipeline.

Pipeline Stages:
1. Rubric Extraction - Convert rubric PDF to structured JSON
2. Breakdown - Parse individual criteria from JSON
3. Scoring - Criterion-level scoring with temperature=0.2
4. Feedback Aggregation - Generate narrative feedback from scores
"""

import json
from datetime import datetime
from pathlib import Path
from src.services.rubric_extractor import RubricExtractor
from src.services.criterion_scorer import CriterionScorer
from src.services.feedback_aggregator import FeedbackAggregator
from src.utils.pdf_to_image import pdf_to_base64_images


def stage1_extract_rubric(rubric_path: str, force_reextract: bool = False) -> dict:
    """
    Stage 1: Extract rubric to JSON format.

    Args:
        rubric_path: Path to the rubric PDF
        force_reextract: If True, re-extract even if JSON exists

    Returns:
        Dictionary containing rubric JSON and metadata
    """
    print("\n" + "=" * 80)
    print("STAGE 1: RUBRIC EXTRACTION")
    print("=" * 80)

    # Check if JSON already exists
    rubric_name = Path(rubric_path).stem
    json_path = Path("rubrics_json") / f"{rubric_name}.json"

    if json_path.exists() and not force_reextract:
        print(f"\n✓ Loading existing rubric JSON from: {json_path}")
        with open(json_path, 'r', encoding='utf-8') as f:
            rubric_data = json.load(f)
        return {
            "rubric_json": rubric_data,
            "json_path": str(json_path),
            "extracted": False
        }

    print(f"\nExtracting rubric from: {rubric_path}")

    # Convert PDF to images for vision-based extraction
    print("Converting rubric PDF to images...")
    rubric_images = pdf_to_base64_images(rubric_path)
    print(f"✓ Rubric converted to {len(rubric_images)} page image(s)")

    # Extract rubric structure using Claude
    print("\nExtracting rubric structure using Claude (this may take 10-30 seconds)...")
    extractor = RubricExtractor()
    result = extractor.extract_rubric_from_images(
        rubric_images=rubric_images,
        temperature=0.2  # Low temperature for consistent extraction
    )

    rubric_json = result["rubric_json"]

    # Save to JSON file
    json_path.parent.mkdir(exist_ok=True)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(rubric_json, f, indent=2, ensure_ascii=False)

    print(f"✓ Rubric JSON saved to: {json_path}")
    print(f"  - Title: {rubric_json.get('rubric_title', 'N/A')}")
    print(f"  - Criteria: {len(rubric_json.get('criteria', []))}")
    print(f"  - Max Total Score: {rubric_json.get('max_total_score', 'N/A')}")
    print(f"  - Tokens used: {result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out")

    return {
        "rubric_json": rubric_json,
        "json_path": str(json_path),
        "usage": result["usage"],
        "extracted": True
    }


def stage2_3_score_criteria(transcript_images: list, rubric_json: dict) -> dict:
    """
    Stage 2 & 3: Parse criteria and perform criterion-level scoring.

    Args:
        transcript_images: List of transcript images
        rubric_json: Structured rubric JSON

    Returns:
        Dictionary containing criterion scores and metadata
    """
    print("\n" + "=" * 80)
    print("STAGE 2-3: CRITERION-LEVEL SCORING")
    print("=" * 80)

    criteria = rubric_json.get('criteria', [])
    print(f"\nScoring {len(criteria)} criteria individually (temperature=0.2 for consistency)...")

    scorer = CriterionScorer()
    result = scorer.score_all_criteria_from_images(
        transcript_images=transcript_images,
        criteria=criteria,
        temperature=0.2  # Low temperature for consistent scoring
    )

    # Display individual scores
    print("\n" + "-" * 80)
    print("CRITERION SCORES:")
    print("-" * 80)
    for score in result["criterion_scores"]:
        print(f"\n{score['criterion_name']}: {score['score']}/{score['max_score']}")
        print(f"  Evidence: {score['evidence'][:100]}...")
        print(f"  Justification: {score['justification'][:100]}...")

    print(f"\n✓ Scored {len(result['criterion_scores'])} criteria")
    print(f"  - Total tokens: {result['total_usage']['input_tokens']} in / {result['total_usage']['output_tokens']} out")

    return result


def stage4_aggregate_feedback(criterion_scores: list, rubric_json: dict) -> dict:
    """
    Stage 4: Aggregate scores and generate narrative feedback.

    Args:
        criterion_scores: List of criterion score dictionaries
        rubric_json: Structured rubric JSON

    Returns:
        Dictionary containing aggregated feedback and metadata
    """
    print("\n" + "=" * 80)
    print("STAGE 4: FEEDBACK AGGREGATION")
    print("=" * 80)

    print("\nGenerating narrative feedback from criterion scores...")

    aggregator = FeedbackAggregator()
    result = aggregator.aggregate_and_generate_feedback(
        criterion_scores=criterion_scores,
        rubric_json=rubric_json,
        temperature=0.7  # Higher temperature for creative narrative
    )

    # Display results
    print("\n" + "-" * 80)
    print("AGGREGATED FEEDBACK:")
    print("-" * 80)
    print(f"\nTotal Score: {result['total_score']}/{result['max_total_score']}")
    print(f"Performance Level: {result['performance_level']}")

    if result['key_strengths']:
        print("\nKey Strengths:")
        for strength in result['key_strengths']:
            print(f"  - {strength}")

    if result['areas_for_development']:
        print("\nPriority Areas for Development:")
        for area in result['areas_for_development']:
            print(f"  - {area}")

    if result['summary']:
        print("\nSummary:")
        print(result['summary'])

    print(f"\n✓ Narrative feedback generated")
    print(f"  - Tokens used: {result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out")

    return result


def evaluate_pdf_transcript(rubric_path: str, transcript_path: str, transcript_name: str, force_reextract_rubric: bool = False):
    """
    Evaluate a single PDF transcript using the 4-stage pipeline.

    Args:
        rubric_path: Path to the rubric PDF
        transcript_path: Path to the transcript PDF
        transcript_name: Display name for the transcript
        force_reextract_rubric: Force re-extraction of rubric even if JSON exists
    """
    print("\n" + "=" * 80)
    print(f"EVALUATING: {transcript_name}")
    print("=" * 80)
    print("\nPipeline: Extract Rubric → Score Criteria → Aggregate Feedback")

    # Convert transcript PDF to images
    print(f"\nPreparing transcript: {transcript_path}")
    transcript_images = pdf_to_base64_images(transcript_path)
    print(f"✓ Transcript converted to {len(transcript_images)} page image(s)")

    # Stage 1: Extract rubric to JSON
    rubric_result = stage1_extract_rubric(rubric_path, force_reextract=force_reextract_rubric)
    rubric_json = rubric_result["rubric_json"]

    # Stage 2-3: Score criteria individually
    scoring_result = stage2_3_score_criteria(transcript_images, rubric_json)

    # Stage 4: Aggregate and generate feedback
    feedback_result = stage4_aggregate_feedback(scoring_result["criterion_scores"], rubric_json)

    # Calculate total token usage
    total_input_tokens = scoring_result["total_usage"]["input_tokens"] + feedback_result["usage"]["input_tokens"]
    total_output_tokens = scoring_result["total_usage"]["output_tokens"] + feedback_result["usage"]["output_tokens"]

    if rubric_result.get("extracted"):
        total_input_tokens += rubric_result["usage"]["input_tokens"]
        total_output_tokens += rubric_result["usage"]["output_tokens"]

    print("\n" + "=" * 80)
    print("TOTAL API USAGE:")
    print(f"  Input tokens: {total_input_tokens}")
    print(f"  Output tokens: {total_output_tokens}")
    print("=" * 80)

    return {
        "rubric_json_path": rubric_result["json_path"],
        "total_score": feedback_result["total_score"],
        "max_total_score": feedback_result["max_total_score"],
        "performance_level": feedback_result["performance_level"],
        "key_strengths": feedback_result["key_strengths"],
        "areas_for_development": feedback_result["areas_for_development"],
        "summary": feedback_result["summary"],
        "criterion_scores": feedback_result["criterion_scores"],
        "narrative_feedback": feedback_result["narrative_feedback"],
        "total_usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens
        }
    }


def main():
    """Main function to evaluate PDF transcripts using the 4-stage pipeline."""

    print("=" * 80)
    print("PDF TRANSCRIPT EVALUATION SYSTEM (4-STAGE PIPELINE)")
    print("=" * 80)
    print("\nPipeline Stages:")
    print("  1. Rubric Extraction → JSON format (temperature=0.2)")
    print("  2. Breakdown → Parse individual criteria")
    print("  3. Scoring → Criterion-level scoring (temperature=0.2)")
    print("  4. Feedback → Aggregate and generate narrative (temperature=0.7)")

    # Define your PDF rubric
    rubric_pdf = "rubrics/ns4430.pdf"

    # Define PDF transcripts to evaluate
    transcripts = [
        # Add your PDF transcripts here:
        {
            "path": "transcripts/case1.pdf",
            "name": "Case 1"
        },
        # {
        #     "path": "transcripts/case1.pdf",
        #     "name": "Student Consultation 1"
        # },
    ]

    # Evaluate each transcript
    results = []
    for transcript_info in transcripts:
        try:
            eval_result = evaluate_pdf_transcript(
                rubric_path=rubric_pdf,
                transcript_path=transcript_info["path"],
                transcript_name=transcript_info["name"],
                force_reextract_rubric=False  # Set to True to re-extract rubric
            )

            # Prepare result data for JSON
            result_data = {
                "transcript_name": transcript_info["name"],
                "transcript_path": transcript_info["path"],
                "evaluation_timestamp": datetime.now().isoformat(),
                "rubric_json_path": eval_result["rubric_json_path"],
                "total_score": eval_result["total_score"],
                "max_total_score": eval_result["max_total_score"],
                "performance_level": eval_result["performance_level"],
                "key_strengths": eval_result["key_strengths"],
                "areas_for_development": eval_result["areas_for_development"],
                "summary": eval_result["summary"],
                "criterion_scores": eval_result["criterion_scores"],
                "narrative_feedback": eval_result["narrative_feedback"],
                "api_usage": eval_result["total_usage"]
            }
            results.append(result_data)

        except FileNotFoundError as e:
            print(f"\n✗ ERROR: File not found - {e}")
            print(f"  Skipping {transcript_info['name']}")
            continue
        except Exception as e:
            print(f"\n✗ ERROR: {str(e)}")
            print(f"  Skipping {transcript_info['name']}")
            continue

    # Summary comparison
    if results:
        print("\n\n" + "=" * 80)
        print("SUMMARY COMPARISON")
        print("=" * 80)

        for result in results:
            print(f"\n{result['transcript_name']}:")
            print(f"  Total Score: {result['total_score']}/{result['max_total_score']}")
            print(f"  Performance: {result['performance_level']}")
            if result['key_strengths']:
                print(f"  Top Strength: {result['key_strengths'][0]}")

        # Save results to JSON file
        output_dir = Path("evaluation_results")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"evaluation_results_{timestamp}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "evaluation_date": datetime.now().isoformat(),
                "pipeline_stages": [
                    "1. Rubric Extraction (temp=0.2)",
                    "2. Breakdown",
                    "3. Criterion Scoring (temp=0.2)",
                    "4. Feedback Aggregation (temp=0.7)"
                ],
                "rubric_path": rubric_pdf,
                "total_transcripts_evaluated": len(results),
                "results": results
            }, f, indent=2, ensure_ascii=False)

        print(f"\n✓ Results saved to: {output_file}")

    print("\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
