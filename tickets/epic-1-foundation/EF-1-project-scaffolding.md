# EF-1: Project Scaffolding

**Epic**: Epic 1 — Foundation & Data Models
**Priority**: Highest
**Depends On**: None

## Description

Create the `email_finder/` directory structure with all `__init__.py` files and placeholder modules.

## Directory Structure

```
email_finder/
    __init__.py
    models.py
    config.py
    finder.py              (placeholder)
    verification/
        __init__.py
        name_email_matcher.py   (placeholder)
        mailin_automator.py     (placeholder)
    discovery/
        __init__.py
        perplexity_search.py    (placeholder)
        website_scraper.py      (placeholder)
        pattern_generator.py    (placeholder)
        browser_discovery.py    (placeholder)
```

## Acceptance Criteria

- [ ] All directories and files exist
- [ ] Module is importable from a notebook with `from email_finder import ...`
- [ ] All placeholder files have a docstring describing their purpose
