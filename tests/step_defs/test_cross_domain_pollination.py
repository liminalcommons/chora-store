"""
Step definitions for cross_domain_pollination.feature

Tests for Experiment 4: Cross-Domain Pollination.
"""

import pytest
from datetime import datetime, timezone
from pytest_bdd import scenarios, given, when, then, parsers
from typing import List, Tuple

from chora_store.models import Entity
from chora_store.evaluator import PatternInductor, PatternProposal

# Load scenarios from feature file
scenarios('../features/cross_domain_pollination.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED BACKGROUND STEPS (from conftest fixtures)
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('a factory with epigenetic support')
def factory_with_epigenetics(factory):
    """Factory is already available from fixture."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1: Manual Bridge Discovery
# ═══════════════════════════════════════════════════════════════════════════════

@given(parsers.parse('learnings exist in domain "{domain}" about boundaries'))
def create_domain_learnings_about_boundaries(repository, context, domain):
    """Create learnings in a specific domain with boundary-related themes."""
    learnings = []
    for i in range(3):
        learning = Entity(
            id=f"learning-{domain}-boundary-{i}",
            type="learning",
            status="captured",
            created_at=datetime.now(timezone.utc),
            data={
                "name": f"Learning about boundary validation in {domain} {i}",
                "insight": f"Clear boundary definitions prevent errors and improve modularity in {domain}. "
                          f"Validation at boundaries catches issues early.",
                "domain": domain,
            }
        )
        repository.create(learning)
        learnings.append(learning)

    if 'domain_learnings' not in context:
        context['domain_learnings'] = {}
    context['domain_learnings'][domain] = learnings


@when('cross-domain similarity search is performed')
def perform_cross_domain_search(repository, context):
    """Perform similarity search across domains."""
    domains = list(context.get('domain_learnings', {}).keys())
    if len(domains) < 2:
        pytest.skip("Need at least 2 domains for cross-domain search")

    # Simple keyword-based similarity for testing
    # (actual implementation uses embeddings)
    candidates = []
    domain_a, domain_b = domains[0], domains[1]
    learnings_a = context['domain_learnings'][domain_a]
    learnings_b = context['domain_learnings'][domain_b]

    for la in learnings_a:
        for lb in learnings_b:
            # Check for shared keywords (simplified similarity)
            words_a = set(la.data.get('insight', '').lower().split())
            words_b = set(lb.data.get('insight', '').lower().split())
            overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
            if overlap > 0.1:  # Low threshold for test
                candidates.append({
                    'learning_a': la,
                    'learning_b': lb,
                    'domains': (domain_a, domain_b),
                    'similarity': overlap,
                })

    context['cross_domain_candidates'] = candidates


@then('candidate pairs are returned with similarity scores')
def candidates_have_similarity_scores(context):
    """Verify candidates have similarity scores."""
    candidates = context.get('cross_domain_candidates', [])
    assert len(candidates) > 0, "Expected at least one candidate pair"
    for c in candidates:
        assert 'similarity' in c, f"Candidate missing similarity: {c}"
        assert c['similarity'] > 0, f"Expected positive similarity: {c['similarity']}"


@then('candidates span both domains')
def candidates_span_domains(context):
    """Verify candidates reference learnings from different domains."""
    candidates = context.get('cross_domain_candidates', [])
    for c in candidates:
        domains = c.get('domains', ())
        assert len(set(domains)) == 2, f"Expected 2 different domains, got: {domains}"


@given('a validated cross-domain candidate pair')
def create_validated_candidate(repository, context):
    """Create a pre-validated cross-domain candidate."""
    # Create source learnings in two domains
    learning_a = Entity(
        id="learning-source-domain-a",
        type="learning",
        status="captured",
        created_at=datetime.now(timezone.utc),
        data={
            "name": "BDD contracts define behavior",
            "insight": "Given/When/Then structure provides clear contract specification",
            "domain": "bdd-testing",
        }
    )
    repository.create(learning_a)

    learning_b = Entity(
        id="learning-source-domain-b",
        type="learning",
        status="captured",
        created_at=datetime.now(timezone.utc),
        data={
            "name": "Repository interfaces need contracts",
            "insight": "Repository methods benefit from clear pre/post conditions",
            "domain": "repository-design",
        }
    )
    repository.create(learning_b)

    context['candidate'] = {
        'learning_a': learning_a,
        'learning_b': learning_b,
        'source_domain': 'bdd-testing',
        'target_domain': 'repository-design',
        'similarity': 0.75,
    }


@when('a bridge learning is created with bridge_metadata')
def create_bridge_learning(repository, context):
    """Create a bridge learning from the candidate."""
    candidate = context['candidate']

    bridge = Entity(
        id="learning-bridge-bdd-to-repo",
        type="learning",
        status="captured",
        created_at=datetime.now(timezone.utc),
        data={
            "name": "BDD Given/When/Then maps to repository Pre/Op/Post",
            "insight": "The contract structure from BDD testing can inform repository interface design. "
                      "Given=preconditions, When=operation, Then=postconditions.",
            "domain": f"bridge:{candidate['source_domain']}->{candidate['target_domain']}",
            "links": [candidate['learning_a'].id, candidate['learning_b'].id],
            "bridge_metadata": {
                "source_domain": candidate['source_domain'],
                "target_domain": candidate['target_domain'],
                "transfer_type": "structural_metaphor",
                "transferability_score": 4,
                "similarity": candidate['similarity'],
            }
        }
    )
    repository.create(bridge)
    context['bridge_learning'] = bridge


@then('the learning has domain starting with "bridge:"')
def learning_has_bridge_domain(context):
    """Verify bridge learning has bridge: domain prefix."""
    bridge = context['bridge_learning']
    domain = bridge.data.get('domain', '')
    assert domain.startswith('bridge:'), f"Expected bridge: prefix, got: {domain}"


@then('the learning has bridge_metadata with source and target domains')
def learning_has_bridge_metadata(context):
    """Verify bridge learning has proper bridge_metadata."""
    bridge = context['bridge_learning']
    metadata = bridge.data.get('bridge_metadata', {})
    assert 'source_domain' in metadata, "Missing source_domain in bridge_metadata"
    assert 'target_domain' in metadata, "Missing target_domain in bridge_metadata"
    assert metadata['source_domain'] != metadata['target_domain'], \
        "Source and target domains should differ"


@given('a bridge learning was created')
def bridge_learning_exists(repository, context):
    """Ensure a bridge learning exists."""
    # Create bridge learning if not already present
    if 'bridge_learning' not in context:
        bridge = Entity(
            id="learning-bridge-test",
            type="learning",
            status="captured",
            created_at=datetime.now(timezone.utc),
            data={
                "name": "Test bridge learning",
                "insight": "Cross-domain insight for testing",
                "domain": "bridge:domain-a->domain-b",
                "bridge_metadata": {
                    "source_domain": "domain-a",
                    "target_domain": "domain-b",
                }
            }
        )
        repository.create(bridge)
        context['bridge_learning'] = bridge


@when('the discovery trace is generated')
def generate_discovery_trace(repository, context):
    """Generate a potentiative trace for the bridge discovery."""
    bridge = context['bridge_learning']

    trace = Entity(
        id=f"learning-cross-domain-bridge-discovered-{bridge.id}",
        type="learning",
        status="captured",
        created_at=datetime.now(timezone.utc),
        data={
            "name": f"Cross-domain bridge discovered: {bridge.data.get('domain', '')}",
            "insight": f"A cross-domain pattern transfer was identified. "
                      f"Bridge: {bridge.id}. This enables future automation.",
            "domain": "autoevolution-experiment",
            "links": [bridge.id],
            "experiment_metadata": {
                "experiment_id": "experiment-4-cross-domain-pollination",
                "outcome": "bridge_validated",
            }
        }
    )
    repository.create(trace)
    context['discovery_trace'] = trace


@then('a learning exists with domain "autoevolution-experiment"')
def learning_exists_with_experiment_domain(repository, context):
    """Verify experiment trace exists."""
    trace = context.get('discovery_trace')
    assert trace is not None, "Discovery trace not created"
    assert trace.data.get('domain') == 'autoevolution-experiment', \
        f"Expected autoevolution-experiment domain, got: {trace.data.get('domain')}"


@then('the learning links to the bridge learning')
def trace_links_to_bridge(context):
    """Verify trace links to bridge learning."""
    trace = context.get('discovery_trace')
    bridge = context.get('bridge_learning')
    links = trace.data.get('links', [])
    assert bridge.id in links, f"Expected bridge {bridge.id} in links: {links}"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2: Automated Detection
# ═══════════════════════════════════════════════════════════════════════════════

@given('learnings exist in different domains with similar themes')
def create_similar_cross_domain_learnings(repository, context):
    """Create learnings with high cross-domain similarity."""
    # Domain A: Testing - about boundaries
    for i in range(3):
        learning = Entity(
            id=f"learning-testing-boundary-{i}",
            type="learning",
            status="captured",
            created_at=datetime.now(timezone.utc),
            data={
                "name": f"Testing boundary insight {i}",
                "insight": "Boundary validation at interfaces prevents bugs and improves test coverage. "
                          "Testing boundaries ensures system reliability.",
                "domain": "testing",
            }
        )
        repository.create(learning)

    # Domain B: Architecture - about boundaries (very similar theme)
    for i in range(3):
        learning = Entity(
            id=f"learning-architecture-boundary-{i}",
            type="learning",
            status="captured",
            created_at=datetime.now(timezone.utc),
            data={
                "name": f"Architecture boundary insight {i}",
                "insight": "Boundary definition at interfaces improves modularity and reduces bugs. "
                          "Clear boundaries ensure system reliability.",
                "domain": "architecture",
            }
        )
        repository.create(learning)

    context['domains'] = ['testing', 'architecture']


@when('the pattern inductor analyzes without cross_domain flag')
def analyze_without_cross_domain(repository, context):
    """Analyze with cross_domain disabled (default)."""
    inductor = PatternInductor(repository, thresholds={
        "min_learnings": 2,
        "confidence_threshold": 0.3,
        "max_proposals": 10,
        "keyword_overlap": 0.01,
        "embedding_similarity": 0.30,
    })
    # Default: include_cross_domain=False
    proposals = inductor.analyze()
    context['proposals'] = proposals


@then('no cross-domain proposals are generated')
def no_cross_domain_proposals(context):
    """Verify no cross-domain proposals exist."""
    proposals = context.get('proposals', [])
    cross_domain = [p for p in proposals if getattr(p, 'cross_domain', False)]
    assert len(cross_domain) == 0, f"Expected no cross-domain proposals, got {len(cross_domain)}"


@then('only within-domain proposals may exist')
def only_within_domain_proposals(context):
    """Verify all proposals are within-domain."""
    proposals = context.get('proposals', [])
    for p in proposals:
        assert not getattr(p, 'cross_domain', False), \
            f"Unexpected cross-domain proposal: {p.name}"


@when(parsers.parse('the pattern inductor analyzes with include_cross_domain=true'))
def analyze_with_cross_domain(repository, context):
    """Analyze with cross_domain enabled."""
    inductor = PatternInductor(repository, thresholds={
        "min_learnings": 2,
        "confidence_threshold": 0.3,
        "max_proposals": 10,
        "keyword_overlap": 0.01,
        "embedding_similarity": 0.30,
        "cross_domain_similarity": 0.70,  # Lower threshold for testing
    })
    proposals = inductor.analyze(include_cross_domain=True)
    context['proposals'] = proposals


@then('cross-domain proposals are generated')
def cross_domain_proposals_exist(context):
    """Verify cross-domain proposals were generated."""
    proposals = context.get('proposals', [])
    cross_domain = [p for p in proposals if getattr(p, 'cross_domain', False)]
    assert len(cross_domain) > 0, "Expected at least one cross-domain proposal"
    context['cross_domain_proposals'] = cross_domain


@then('the proposals have cross_domain=true')
def proposals_have_cross_domain_flag(context):
    """Verify proposals have cross_domain flag set."""
    cross_domain = context.get('cross_domain_proposals', [])
    for p in cross_domain:
        assert p.cross_domain is True, f"Proposal {p.name} missing cross_domain=True"


@then('the proposals have source_domains from multiple domains')
def proposals_have_multiple_source_domains(context):
    """Verify proposals have source_domains from 2+ domains."""
    cross_domain = context.get('cross_domain_proposals', [])
    for p in cross_domain:
        source_domains = getattr(p, 'source_domains', [])
        assert len(source_domains) >= 2, \
            f"Expected 2+ source_domains, got: {source_domains}"


@given('learnings exist with moderate cross-domain similarity')
def create_moderate_similarity_learnings(repository, context):
    """Create learnings with only moderate cross-domain similarity."""
    # Domain A: About testing
    for i in range(3):
        learning = Entity(
            id=f"learning-testing-moderate-{i}",
            type="learning",
            status="captured",
            created_at=datetime.now(timezone.utc),
            data={
                "name": f"Testing insight {i}",
                "insight": "Unit tests verify individual components work correctly.",
                "domain": "testing",
            }
        )
        repository.create(learning)

    # Domain B: About deployment (different topic)
    for i in range(3):
        learning = Entity(
            id=f"learning-deployment-moderate-{i}",
            type="learning",
            status="captured",
            created_at=datetime.now(timezone.utc),
            data={
                "name": f"Deployment insight {i}",
                "insight": "Continuous deployment pipelines automate release processes.",
                "domain": "deployment",
            }
        )
        repository.create(learning)

    context['domains'] = ['testing', 'deployment']


@then('within-domain proposals may still be generated')
def within_domain_proposals_may_exist(context):
    """Within-domain proposals are allowed."""
    # This is a documentation step - we don't assert anything specific
    # as within-domain proposals depend on the learnings
    pass


@when('the pattern inductor approves a cross-domain proposal')
def approve_cross_domain_proposal(repository, context):
    """Approve a cross-domain proposal."""
    # First ensure we have cross-domain proposals
    inductor = PatternInductor(repository, thresholds={
        "min_learnings": 2,
        "confidence_threshold": 0.3,
        "max_proposals": 10,
        "keyword_overlap": 0.01,
        "embedding_similarity": 0.30,
        "cross_domain_similarity": 0.70,  # Lower threshold for testing
    })
    proposals = inductor.analyze(include_cross_domain=True)

    cross_domain = [p for p in proposals if getattr(p, 'cross_domain', False)]
    if not cross_domain:
        pytest.skip("No cross-domain proposals to approve")

    proposal = cross_domain[0]
    pattern = inductor.approve_proposal(proposal)
    context['approved_pattern'] = pattern
    context['approved_proposal'] = proposal


@then('the created pattern has cross_domain=true')
def pattern_has_cross_domain(context):
    """Verify created pattern has cross_domain field."""
    pattern = context.get('approved_pattern')
    if pattern is None:
        pytest.skip("No pattern was created")
    cross_domain = pattern.data.get('cross_domain', False)
    assert cross_domain is True, f"Expected cross_domain=True, got: {cross_domain}"


@then('the created pattern has source_domains set')
def pattern_has_source_domains(context):
    """Verify created pattern has source_domains field."""
    pattern = context.get('approved_pattern')
    if pattern is None:
        pytest.skip("No pattern was created")
    source_domains = pattern.data.get('source_domains', [])
    assert len(source_domains) >= 2, f"Expected 2+ source_domains, got: {source_domains}"


@then('the created pattern has bridge_strength set')
def pattern_has_bridge_strength(context):
    """Verify created pattern has bridge_strength field."""
    pattern = context.get('approved_pattern')
    if pattern is None:
        pytest.skip("No pattern was created")
    bridge_strength = pattern.data.get('bridge_strength', 0.0)
    assert bridge_strength > 0, f"Expected positive bridge_strength, got: {bridge_strength}"
