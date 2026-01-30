# BRD Generator Templates

This directory contains customizable templates for BRD generation output.

## How Templates Work

Templates define the **output format** for generated documents. Users can customize these templates to match their organizational standards.

## Template Files

| Template | Purpose | Placeholders |
|----------|---------|--------------|
| `brd-template.md` | Business Requirements Document format | `{TITLE}`, `{BUSINESS_CONTEXT}`, `{OBJECTIVES}`, etc. |
| `epic-template.md` | Epic format | `{EPIC_ID}`, `{TITLE}`, `{DESCRIPTION}`, etc. |
| `backlog-template.md` | User Story format | `{STORY_ID}`, `{AS_A}`, `{I_WANT}`, etc. |

## Customizing Templates

### Option 1: Modify Default Templates
Edit the template files in this directory.

### Option 2: Provide Custom Templates Directory
Set environment variable:
```bash
export BRD_TEMPLATES_DIR=/path/to/your/templates
```

### Option 3: Pass Template at Runtime
```python
generator = BRDGenerator(
    templates_dir=Path("/path/to/custom/templates")
)
```

## Template Placeholders

### BRD Template (`brd-template.md`)

| Placeholder | Description |
|-------------|-------------|
| `{TITLE}` | Feature/BRD title |
| `{VERSION}` | Document version |
| `{DATE}` | Generation date |
| `{BUSINESS_CONTEXT}` | Business problem and context |
| `{OBJECTIVES}` | Measurable goals |
| `{FUNCTIONAL_REQUIREMENTS}` | What the system should do |
| `{TECHNICAL_REQUIREMENTS}` | How it should be implemented |
| `{DEPENDENCIES}` | Internal/external dependencies |
| `{RISKS}` | Risks and mitigation strategies |
| `{ACCEPTANCE_CRITERIA}` | Success criteria |
| `{AFFECTED_COMPONENTS}` | Components from code graph |
| `{SOURCE_FILES}` | Key files to modify |

### Epic Template (`epic-template.md`)

| Placeholder | Description |
|-------------|-------------|
| `{EPIC_ID}` | Epic identifier (EPIC-001) |
| `{TITLE}` | Epic title |
| `{DESCRIPTION}` | Detailed description |
| `{COMPONENTS}` | Affected components |
| `{EFFORT}` | Estimated effort |
| `{STORIES}` | User stories in this epic |

### Backlog Template (`backlog-template.md`)

| Placeholder | Description |
|-------------|-------------|
| `{STORY_ID}` | Story identifier (STORY-001) |
| `{EPIC_ID}` | Parent epic |
| `{AS_A}` | User role |
| `{I_WANT}` | Desired capability |
| `{SO_THAT}` | Business benefit |
| `{ACCEPTANCE_CRITERIA}` | Testable criteria |
| `{POINTS}` | Story points |

## Example: Custom Organizational Template

```markdown
# [Company Name] Business Requirements Document

**Document ID:** BRD-{DATE}-{TITLE}
**Author:** {AUTHOR}
**Reviewers:** {REVIEWERS}
**Status:** Draft

---

## 1. Executive Summary
{BUSINESS_CONTEXT}

## 2. Business Objectives
{OBJECTIVES}

## 3. Scope
### 3.1 In Scope
{FUNCTIONAL_REQUIREMENTS}

### 3.2 Out of Scope
{OUT_OF_SCOPE}

## 4. Technical Approach
{TECHNICAL_REQUIREMENTS}

### 4.1 Affected Systems
{AFFECTED_COMPONENTS}

### 4.2 Files to Modify
{SOURCE_FILES}

## 5. Dependencies & Integrations
{DEPENDENCIES}

## 6. Risk Assessment
{RISKS}

## 7. Success Criteria
{ACCEPTANCE_CRITERIA}

## 8. Approval
| Role | Name | Signature | Date |
|------|------|-----------|------|
| Product Owner | | | |
| Tech Lead | | | |
| Architect | | | |
```
