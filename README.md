# Patent RAG System for Prior Art Search
## Overview

This project aims to build a Retrieval-Augmented Generation (RAG) system that helps determine whether a new invention is already covered by existing patents.

## Objectives
Search patent databases using natural language invention descriptions.

Identify similar patents and prior art.

Compare invention features with patent claims.

Generate explainable novelty assessments.

## Architecture

## Data
https://data.uspto.gov/bulkdata/datasets/appxml?fileData=&fileDataFromDate=2025-06-20&fileDataToDate=2026-06-20

## Debugging invalid backend reports

Set `DEBUG_INVALID_REPORTS=true` before starting the API and worker. When report validation fails, the result page will provide a **Show raw backend response** section containing the response that failed validation.

Node server:

```sh
DEBUG_INVALID_REPORTS=true npm run start:node
```

Flask and Celery: add `DEBUG_INVALID_REPORTS=true` to `.env`, then restart both the Flask server and Celery worker.
