# Validation Comparison Guide

## Overview

The Validation Comparison feature allows you to upload human-graded evaluations (as PDF documents) and compare them with AI-generated evaluations to validate the accuracy of the AI grading system.

## Features

- **Upload Human Grading PDFs**: Upload any PDF containing human grading scores
- **Automatic Extraction**: AI automatically extracts grader name, scores, and feedback from PDFs
- **View Comparisons**: See side-by-side comparisons of AI vs Human scores
- **Detailed Analysis**: View criterion-by-criterion differences
- **Statistics**: Get mean difference and mean absolute difference metrics
- **Color-Coded Differences**: Easily identify large discrepancies

## How to Use

### Step 1: Navigate to Validation Page

1. Start the application
2. Click on **Step 9: Validation** in the progress bar

### Step 2: Prepare Human Grading PDF

Create a PDF document with your human grading that includes:
- Grader name (optional - AI will extract it)
- Criterion names
- Scores for each criterion
- Maximum scores for each criterion
- Optional feedback comments

**Example PDF Content:**
```
Human Grading Evaluation
Grader: Dr. Smith

Criterion 1: Opening and Introduction
Score: 8.5/10
Feedback: Good greeting and rapport building

Criterion 2: Active Listening
Score: 9.0/10
Feedback: Excellent use of reflection

Total Score: 42.5/50
```

### Step 3: Upload Human Grading

1. Select an AI evaluation from the dropdown
2. Click "Choose PDF file" and select your human grading PDF
3. Optionally add notes about the grading session
4. Click "Upload & Parse Human Grading"
5. AI will automatically extract all scores and feedback

### Step 4: View Comparison

1. After uploading, the comparison will appear in the "Validation Comparisons" list
2. Click "View Details" to see:
   - Total score comparison (AI vs Human)
   - Overall difference
   - Mean absolute difference across all criteria
   - Detailed criterion-by-criterion breakdown with color-coded differences

## Understanding the Results

### Color Coding

- **Green**: Small difference (≤1 point) - Good agreement
- **Orange**: Moderate difference (1-2 points) - Acceptable variance
- **Red**: Large difference (>2 points) - Significant discrepancy
- **Gray**: N/A (criterion missing from one grading)

### Statistics Explained

- **Total Difference**: AI total score minus Human total score
  - Positive = AI graded higher
  - Negative = AI graded lower

- **Mean Difference**: Average difference across all criteria (signed)
  - Shows bias direction (AI over/under grading)

- **Mean Absolute Difference**: Average of absolute differences
  - Shows overall accuracy regardless of direction
  - Lower is better (indicates closer agreement)

## API Endpoints

### Upload Human Grading
```
POST /api/validations/{evaluation_id}/upload-human-grading
Content-Type: multipart/form-data

Fields:
- human_grading_file: PDF file
- llm_provider (optional): "openai" or "anthropic"
- notes (optional): string

Returns:
- message: Success message
- human_grading: Created grading record
- parsed_data: Extracted information (grader_name, total_score, criterion_count)
```

### Get Comparison
```
GET /api/validations/{evaluation_id}/comparison

Returns detailed comparison data including:
- Total scores (AI and Human)
- Differences and statistics
- Criterion-by-criterion breakdown
```

### List All Comparisons
```
GET /api/validations

Returns summary of all validation comparisons
```

### Delete Human Grading
```
DELETE /api/validations/{evaluation_id}/human-grading

Removes human grading data for an evaluation
```

## Example Workflow

1. **Create AI Evaluation**: Use the normal grading workflow (Steps 1-4)
2. **Human Grader Reviews**: A human grader evaluates the same transcript
3. **Create PDF**: Human grader creates a PDF with their scores and feedback
4. **Upload for Comparison**: Navigate to Step 9, select the AI evaluation, and upload the PDF
5. **AI Parses PDF**: System automatically extracts all scores and feedback
6. **Analyze Results**: Review the detailed comparison to validate AI accuracy
7. **Iterate**: Use insights to improve rubrics or prompts

## Tips for Best Results

1. **Clear PDF Format**: Use clear, structured format in human grading PDFs
2. **Match Criterion Names**: Try to use similar criterion names as the AI rubric
3. **Include All Details**: Make sure total scores and individual scores are visible
4. **Use Consistent Scoring**: Human graders should use the same max_score scale
5. **Multiple Comparisons**: Upload multiple human gradings to identify patterns
6. **Review Large Differences**: Investigate criteria with differences >2 points
7. **Document Findings**: Use the notes field to record insights about each comparison

## Troubleshooting

**Issue**: "No valid criterion scores found in PDF"
- **Solution**: Ensure PDF has clear score information. AI needs to see scores in format like "8/10" or "Score: 8, Max: 10"

**Issue**: Criterion appears as "N/A" in comparison
- **Solution**: Criterion names in human PDF don't exactly match AI evaluation. AI tries to match similar names but exact matches work best.

**Issue**: Upload fails or parsing error
- **Solution**: Ensure PDF is readable (not scanned image). Try re-saving as text-based PDF.

**Issue**: Wrong scores extracted
- **Solution**: Make PDF formatting clearer. Use consistent format like "Criterion: [name], Score: [x]/[y]"

## Database Schema

### human_gradings table
- id (Primary Key)
- evaluation_id (Foreign Key to evaluations)
- total_score
- max_total_score
- grader_name
- notes
- created_at

### human_criterion_scores table
- id (Primary Key)
- human_grading_id (Foreign Key to human_gradings)
- criterion_name
- score
- max_score
- feedback
