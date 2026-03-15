# EF-10: Email Pattern Generator Node

**Epic**: Epic 5 — Email Pattern Generation
**Priority**: Medium
**Depends On**: EF-1, EF-2

## Description

Create `email_finder/discovery/pattern_generator.py` that generates common professional email patterns from a lead's name and domain. These candidates are later batch-verified via Mailin (Epic 7).

## Implementation

```python
def generate_email_patterns(full_name: str, domain: str) -> list[str]:
    """
    Generate common professional email patterns.
    Returns list of candidate emails in priority order (most common first).
    """
```

### Name Parsing

```python
def parse_name(full_name: str) -> dict:
    """
    Parse full name into components.
    Returns: {"first": "john", "last": "smith", "first_initial": "j", "last_initial": "s"}

    Handles:
    - "John Smith" → first=john, last=smith
    - "John Michael Smith" → first=john, last=smith (middle ignored)
    - "Mary-Jane Watson" → first=maryjane (also mary-jane, mary, jane), last=watson
    - "John Smith Jr." → first=john, last=smith (suffix stripped)
    - "Madonna" → first=madonna, last=None
    """
```

### Pattern Templates (in priority order)

```
1.  first.last@domain       # john.smith@acme.com     (most common)
2.  firstlast@domain        # johnsmith@acme.com
3.  flast@domain            # jsmith@acme.com
4.  first@domain            # john@acme.com
5.  last.first@domain       # smith.john@acme.com
6.  firstl@domain           # johns@acme.com
7.  f.last@domain           # j.smith@acme.com
8.  first_last@domain       # john_smith@acme.com
9.  first-last@domain       # john-smith@acme.com
10. last@domain             # smith@acme.com
```

### Node Function

```python
async def generate_patterns(lead: LeadInput, config: Config) -> NodeResult:
    """
    Generate email patterns for the lead.
    Requires company_domain (from lead or discovered by prior nodes).
    Returns NodeResult.found_emails with all candidates.
    """
```

- If no domain available → return NodeResult with error "no domain for pattern generation"
- Generate up to `config.max_patterns_per_lead` patterns
- Return all as candidates (verification happens in Mailin batch step)

## Acceptance Criteria

- [ ] `generate_email_patterns("John Smith", "acme.com")` returns ~10 patterns
- [ ] First pattern is `john.smith@acme.com` (most common format)
- [ ] Handles hyphenated names: "Mary-Jane Watson" generates "maryjane.watson@", "mary-jane.watson@", etc.
- [ ] Handles single names: "Madonna" generates "madonna@domain"
- [ ] Strips suffixes: "John Smith Jr." → treats as "John Smith"
- [ ] Returns empty list (not error) when domain is missing
