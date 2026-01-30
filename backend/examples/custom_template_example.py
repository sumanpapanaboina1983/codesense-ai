#!/usr/bin/env python3
"""
Example: Using Custom Templates for BRD Generation

This example shows how users can customize BRD output format
to match their organizational standards while still using
skill-based MCP tool integration.
"""

import asyncio
from pathlib import Path

from brd_generator.core.generator import BRDGenerator
from brd_generator.core.synthesizer import TemplateConfig
from brd_generator.models.request import BRDRequest


# =============================================================================
# Example 1: Basic Template Configuration
# =============================================================================

async def example_basic_config():
    """Use basic template configuration."""

    # Create template config with organizational settings
    template_config = TemplateConfig(
        organization_name="Acme Corp",
        document_prefix="ACME-BRD",
        require_approvals=True,
        approval_roles=["Product Owner", "Engineering Manager", "Architect"],
        include_code_references=True,
        include_file_paths=True,
        include_risk_matrix=True,
        risk_levels=["Critical", "High", "Medium", "Low"],
    )

    # Create generator with template config
    generator = BRDGenerator(
        template_config=template_config,
    )

    # Generate BRD - uses skill for MCP tools, template for output format
    request = BRDRequest(
        feature_description="Add user authentication with OAuth2",
        affected_components=["auth-service", "api-gateway"],
    )

    output = await generator.generate(request, use_skill=True)
    print(output.brd.to_markdown())


# =============================================================================
# Example 2: Custom Template Content
# =============================================================================

async def example_custom_template():
    """Provide completely custom template content."""

    # Custom BRD template matching company's documentation standard
    custom_brd_template = '''
# {ORGANIZATION} Technical Specification

**Spec ID:** {DOCUMENT_PREFIX}-{DATE}
**Project:** {TITLE}
**Classification:** Internal

---

## 1. Problem Statement
{BUSINESS_CONTEXT}

## 2. Proposed Solution
{OBJECTIVES}

## 3. Technical Design

### 3.1 Component Changes
{AFFECTED_COMPONENTS}

### 3.2 Code Modifications
{SOURCE_FILES}

### 3.3 Interface Changes
{API_CHANGES}

## 4. Requirements Matrix

### Functional
{FUNCTIONAL_REQUIREMENTS}

### Non-Functional
{TECHNICAL_REQUIREMENTS}

## 5. Risk Register
{RISKS}

## 6. Verification Criteria
{ACCEPTANCE_CRITERIA}

---

**Sign-off Required:**
- [ ] Engineering Lead
- [ ] Product Manager
- [ ] Security Review
'''

    template_config = TemplateConfig(
        brd_template=custom_brd_template,
        organization_name="TechCorp Inc",
        document_prefix="TC-SPEC",
        custom_sections=["Security Review", "Performance Baseline"],
    )

    generator = BRDGenerator(template_config=template_config)

    request = BRDRequest(
        feature_description="Implement rate limiting for API endpoints",
    )

    output = await generator.generate(request, use_skill=True)
    print(output.brd.to_markdown())


# =============================================================================
# Example 3: Custom Templates Directory
# =============================================================================

async def example_templates_directory():
    """Use templates from a custom directory."""

    # Point to organization's templates directory
    templates_dir = Path("/path/to/company/templates")

    # Templates directory should contain:
    # - brd-template.md
    # - epic-template.md
    # - backlog-template.md

    generator = BRDGenerator(
        templates_dir=templates_dir,
        template_config=TemplateConfig(
            organization_name="Enterprise Co",
            require_approvals=True,
        ),
    )

    request = BRDRequest(
        feature_description="Add audit logging for compliance",
    )

    output = await generator.generate(request, use_skill=True)
    print(output.brd.to_markdown())


# =============================================================================
# Example 4: Minimal Output (Startup Style)
# =============================================================================

async def example_minimal_template():
    """Minimal BRD for fast-moving startups."""

    minimal_template = '''
# Feature: {TITLE}

## What
{BUSINESS_CONTEXT}

## Why
{OBJECTIVES}

## How
{TECHNICAL_REQUIREMENTS}

## Files to Change
{SOURCE_FILES}

## Done When
{ACCEPTANCE_CRITERIA}
'''

    template_config = TemplateConfig(
        brd_template=minimal_template,
        require_approvals=False,
        include_risk_matrix=False,
        max_requirements_per_section=5,
    )

    generator = BRDGenerator(template_config=template_config)

    request = BRDRequest(
        feature_description="Add dark mode toggle",
    )

    output = await generator.generate(request, use_skill=True)
    print(output.brd.to_markdown())


# =============================================================================
# Example 5: Enterprise Compliance Template
# =============================================================================

async def example_enterprise_compliance():
    """Enterprise template with compliance sections."""

    template_config = TemplateConfig(
        organization_name="BigBank Financial",
        document_prefix="BB-REQ",
        require_approvals=True,
        approval_roles=[
            "Product Owner",
            "Engineering Lead",
            "Security Officer",
            "Compliance Officer",
            "Data Protection Officer",
        ],
        custom_sections=[
            "Data Privacy Impact Assessment",
            "Security Classification",
            "Regulatory Compliance",
            "Audit Trail Requirements",
            "Data Retention Policy",
        ],
        include_risk_matrix=True,
        risk_levels=["Critical", "High", "Medium", "Low", "Informational"],
        include_code_references=True,
        include_file_paths=True,
    )

    generator = BRDGenerator(template_config=template_config)

    request = BRDRequest(
        feature_description="Add PII encryption for customer data at rest",
        affected_components=["data-service", "encryption-service", "database"],
    )

    output = await generator.generate(request, use_skill=True)
    print(output.brd.to_markdown())


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("BRD Generator - Custom Template Examples")
    print("=" * 60)

    # Run the basic example
    asyncio.run(example_basic_config())
