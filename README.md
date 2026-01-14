# About

## Overview

This repository reproduces and extends the **Sema-Join** approach from Microsoft Research, implementing bitmap-based algorithms for discovering join relationships between database tables. The system automatically identifies which columns from different tables should be joined together by analyzing co-occurrence patterns in large table corpora.

**Based on:** [Sema-Join: Joining Semantically-Related Tables Using Big Table Corpora](https://www.microsoft.com/en-us/research/publication/sema-join/) (Microsoft Research)

## What Problem Does This Solve?

When working with large collections of tables (e.g., Wikipedia tables, GitHub repositories, web data), manually identifying join relationships is time-consuming and error-prone. This system automates join discovery by:
- Analyzing statistical co-occurrence patterns between column values across millions of tables
- Using normalized pointwise mutual information (NPMI) to measure semantic relationships
- Leveraging bitmap operations for efficient computation at massive scale

## Datasets

This implementation has been tested and benchmarked on three major table corpora:

### 1. **WikiTables**
- Collection of tables extracted from Wikipedia articles
- Rich semantic relationships (cities↔states, countries↔capitals, etc.)
- Diverse domains and entity types

### 2. **GitTables**
- Tables extracted from CSV files in GitHub repositories
- Real-world data from open-source projects
- Technical and scientific data domains

### 3. **WDC (Web Data Commons)**
- Large-scale web table corpus
- Millions of tables from Common Crawl
- Broad coverage of web data patterns

## Implemented Algorithms

### 1. CS-JP-LP (Column Score Join Prediction with Linear Programming)
- Returns a single best join candidate per value
- Uses constraint-based optimization to ensure one-to-one mappings
- Employs linear programming (via PuLP/HiGHS) for globally optimal selection
- Maximizes aggregate pairwise column-level co-occurrence scores
- Based on the CS-JP formulation from the original Sema-Join paper

### 2. RS-JP (Row Score Join Prediction)
- Returns up to K candidate joins per value (default: K=1)
- Maximizes aggregate row-level co-occurrence scores
- Provides ranked alternatives based on NPMI scores
- Faster than CS-JP-LP, useful when multiple options are valuable
- Simpler variant from the original Sema-Join paper

### 3. AI-Enhanced Join Selection (Novel Extension)
- Evaluates RS-JP candidates using large language models (Ollama)
- Selects semantically appropriate matches using contextual understanding
- Examples:
  - "dover" → "delaware" (capital city relationship)
  - "phoenix" → "arizona" (city in state)
  - "moon" → "earth" (celestial body relationship)
- Provides natural language explanations for each selection

## Citation

If you use this work, please cite the original Sema-Join paper:

```bibtex
@inproceedings{he2015sema-join,
  author = {He, Yeye and Ganjam, Kris and Chu, Xu},
  title = {SEMA-JOIN: Joining Semantically-Related Tables Using Big Table Corpora},
  booktitle = {Proceedings of the VLDB Endowment},
  year = {2015},
  volume = {8},
  number = {12},
  pages = {1358--1369}
}
```

## References

- **Original Paper:** [Sema-Join: Joining Semantically-Related Tables Using Big Table Corpora](https://www.microsoft.com/en-us/research/publication/sema-join/)
- **WikiTables:** [1.6M Wikipedia Tables in JSON format (TabEL dataset)](http://websail-fe.cs.northwestern.edu/TabEL/)
- **GitTables:** [GitTables: A Large-Scale Corpus of Relational Tables](https://arxiv.org/abs/2106.07258)
- **WDC Web Tables:** [Web Data Commons - Web Tables Corpus](http://webdatacommons.org/webtables/)
