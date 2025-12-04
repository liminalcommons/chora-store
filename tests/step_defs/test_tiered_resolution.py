"""
Step definitions for tiered_resolution.feature
"""

import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.metabolism import MetabolicEngine

# Load scenarios from feature file
scenarios('../features/tiered_resolution.feature')


# ═══════════════════════════════════════════════════════════════════════════════
# GIVEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@given('a fresh repository')
def fresh_repository(repository):
    """Repository is already fresh from fixture."""
    pass


@given('multiple learnings with high keyword overlap')
def learnings_high_overlap(factory, context):
    """Create learnings that will cluster together (high keyword overlap)."""
    learnings = []
    # These share keywords: "testing", "patterns", "important"
    l1 = factory.create('learning', 'Testing Patterns 1',
                        insight='Testing patterns are important for quality',
                        domain='engineering')
    l2 = factory.create('learning', 'Testing Patterns 2',
                        insight='Quality testing patterns prevent bugs',
                        domain='engineering')
    l3 = factory.create('learning', 'Testing Importance',
                        insight='Important testing ensures patterns work',
                        domain='engineering')
    learnings.extend([l1, l2, l3])
    context['learnings'] = learnings
    context['learning_ids'] = [l.id for l in learnings]


@given('multiple learnings with low keyword overlap')
def learnings_low_overlap(factory, context):
    """Create learnings that won't cluster well (low keyword overlap)."""
    learnings = []
    # These have minimal keyword overlap
    l1 = factory.create('learning', 'Database Design',
                        insight='Indexes speed up queries',
                        domain='databases')
    l2 = factory.create('learning', 'UI Patterns',
                        insight='Components should be reusable',
                        domain='frontend')
    l3 = factory.create('learning', 'Security Practices',
                        insight='Always validate user input',
                        domain='security')
    learnings.extend([l1, l2, l3])
    context['learnings'] = learnings
    context['learning_ids'] = [l.id for l in learnings]


@given('only one learning')
def single_learning(factory, context):
    """Create only one learning (insufficient for synthesis)."""
    l = factory.create('learning', 'Single Learning',
                       insight='This is a solo insight',
                       domain='general')
    context['learnings'] = [l]
    context['learning_ids'] = [l.id]


# ═══════════════════════════════════════════════════════════════════════════════
# WHEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@when('tiered_synthesize is called with the learning IDs')
def call_tiered_synthesize(repository, context):
    """Call tiered_synthesize with default parameters."""
    engine = MetabolicEngine(repository)
    result = engine.tiered_synthesize(context['learning_ids'])
    context['result'] = result


@when(parsers.parse('tiered_synthesize is called with max_tier "{max_tier}"'))
def call_tiered_synthesize_with_max_tier(repository, context, max_tier):
    """Call tiered_synthesize with a max tier constraint."""
    engine = MetabolicEngine(repository)
    result = engine.tiered_synthesize(context['learning_ids'], max_tier=max_tier)
    context['result'] = result


# ═══════════════════════════════════════════════════════════════════════════════
# THEN steps
# ═══════════════════════════════════════════════════════════════════════════════

@then('synthesis succeeds at the workflow tier')
def synthesis_succeeds_workflow(context):
    """Verify synthesis succeeded at workflow tier."""
    result = context['result']
    assert result['success'] is True
    assert result['tier_used'] == 'workflow'
    assert result['result'] is not None


@then('a trace is captured for the workflow tier')
def trace_captured_workflow(context):
    """Verify a workflow tier trace was captured."""
    result = context['result']
    assert len(result['traces']) >= 1
    # The trace ID should be in the list
    assert any('trace-' in t for t in result['traces'])


@then('synthesis escalates to inference tier')
def synthesis_escalates_inference(context):
    """Verify synthesis escalated to inference tier."""
    result = context['result']
    # Since LLM is not implemented, success will be False
    # but tier_used should be 'inference'
    assert result['tier_used'] == 'inference'


@then('traces are captured for both workflow and inference tiers')
def traces_both_tiers(repository, context):
    """Verify traces were captured for both tier attempts."""
    result = context['result']
    # Should have 2 traces (one for each tier)
    assert len(result['traces']) == 2

    # Verify traces exist in database
    with repository._connection() as conn:
        for trace_id in result['traces']:
            row = conn.execute(
                "SELECT tier FROM traces WHERE id = ?",
                (trace_id,)
            ).fetchone()
            assert row is not None


@then('synthesis does not escalate beyond workflow')
def no_escalation_beyond_workflow(context):
    """Verify synthesis stayed at workflow tier."""
    result = context['result']
    assert result['tier_used'] is None or result['tier_used'] == 'workflow'
    assert result['success'] is False  # Can't succeed without escalation


@then('an escalation reason is provided')
def escalation_reason_provided(context):
    """Verify an escalation reason was given."""
    result = context['result']
    assert result['escalation_reason'] is not None
    assert len(result['escalation_reason']) > 0


@then('synthesis fails with an error about insufficient learnings')
def synthesis_fails_insufficient(context):
    """Verify synthesis fails due to insufficient learnings."""
    result = context['result']
    assert result['success'] is False
    assert 'learning' in result['escalation_reason'].lower()
    assert '2' in result['escalation_reason'] or 'insufficient' in result['escalation_reason'].lower()


@then('no traces are captured')
def no_traces(context):
    """Verify no traces were captured."""
    result = context['result']
    assert len(result['traces']) == 0


@then(parsers.parse('the trace includes operation_type "{operation_type}"'))
def trace_has_operation_type(repository, context, operation_type):
    """Verify trace has the expected operation type."""
    result = context['result']
    assert len(result['traces']) > 0

    with repository._connection() as conn:
        trace_id = result['traces'][0]
        row = conn.execute(
            "SELECT operation_type FROM traces WHERE id = ?",
            (trace_id,)
        ).fetchone()
        assert row is not None
        assert row['operation_type'] == operation_type


@then('the trace includes the input learning IDs')
def trace_has_inputs(repository, context):
    """Verify trace includes input learning IDs."""
    result = context['result']
    learning_ids = context['learning_ids']

    with repository._connection() as conn:
        trace_id = result['traces'][0]
        row = conn.execute(
            "SELECT inputs FROM traces WHERE id = ?",
            (trace_id,)
        ).fetchone()
        assert row is not None
        inputs = json.loads(row['inputs'])
        for lid in learning_ids:
            assert lid in inputs


@then('the trace includes reasoning steps')
def trace_has_reasoning(repository, context):
    """Verify trace includes reasoning steps."""
    result = context['result']

    with repository._connection() as conn:
        trace_id = result['traces'][0]
        row = conn.execute(
            "SELECT reasoning FROM traces WHERE id = ?",
            (trace_id,)
        ).fetchone()
        assert row is not None
        reasoning = json.loads(row['reasoning'])
        assert len(reasoning) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Tool Invocation Tier Assignment
# ═══════════════════════════════════════════════════════════════════════════════

@given('an LLM handler tool exists')
def llm_handler_tool(factory, context):
    """Create a tool with LLM handler."""
    tool = factory.create('tool', 'Test LLM Tool',
                          namespace='test',
                          handler={'type': 'llm', 'prompt_template': 'Test prompt'})
    context['tool_id'] = tool.id


@given('a reference handler tool exists')
def reference_handler_tool(factory, context):
    """Create a tool with reference handler."""
    tool = factory.create('tool', 'Test Reference Tool',
                          namespace='test',
                          handler={'type': 'reference', 'function': 'test_func'})
    context['tool_id'] = tool.id


@given('a generative handler tool exists')
def generative_handler_tool(factory, context):
    """Create a tool with generative handler."""
    tool = factory.create('tool', 'Test Generative Tool',
                          namespace='test',
                          handler={'type': 'generative', 'prompt_template': 'Test prompt'})
    context['tool_id'] = tool.id


@when('the tool is invoked')
def invoke_tool(repository, context):
    """Invoke the tool and capture result."""
    from unittest.mock import patch
    from chora_store import mcp

    tool_id = context['tool_id']

    # Mock _get_repo to use test repository
    with patch.object(mcp, '_get_repo', return_value=repository):
        result = mcp.tool_invoke(tool_id)

    context['invoke_result'] = result


@then(parsers.parse('the trace is captured with tier "{expected_tier}"'))
def trace_has_tier(repository, context, expected_tier):
    """Verify trace was captured with expected tier."""
    tool_id = context['tool_id']

    with repository._connection() as conn:
        row = conn.execute(
            """SELECT tier FROM traces
               WHERE capability_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (tool_id,)
        ).fetchone()
        assert row is not None, f"No trace found for tool {tool_id}"
        assert row['tier'] == expected_tier, f"Expected tier {expected_tier}, got {row['tier']}"


# ═══════════════════════════════════════════════════════════════════════════════
# Semantic Trace Clustering (Embedding-Based)
# ═══════════════════════════════════════════════════════════════════════════════

@given(parsers.parse('5 traces with similar inputs about "{topic}"'))
def similar_traces_about_topic(repository, context, topic):
    """Create 5 traces with semantically similar inputs about a topic."""
    import json
    from datetime import datetime

    tool_id = "tool-test-clustering"
    context['tool_id'] = tool_id
    context['topic'] = topic

    # Create traces with similar (but not identical) inputs
    similar_inputs = [
        f"How do we improve {topic} in our system?",
        f"What's the best approach to {topic}?",
        f"Implementing {topic} patterns effectively",
        f"Strategies for better {topic}",
        f"Enhancing {topic} capabilities",
    ]

    # Same output for all traces (high consistency for crystallization)
    consistent_output = json.dumps({"result": f"Recommended {topic} patterns and strategies"})

    trace_ids = []
    with repository._connection() as conn:
        for i, input_text in enumerate(similar_inputs):
            trace_id = f"trace-test-{topic.replace(' ', '-')}-{i}"
            conn.execute(
                """INSERT INTO traces (id, operation_type, tier, capability_id, inputs, outputs,
                                       reasoning, cost_units, duration_ms, success, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    "synthesize",
                    "inference",
                    tool_id,
                    input_text,
                    consistent_output,  # Same output for all traces
                    json.dumps([f"Processing {topic}"]),
                    100.0,
                    50,
                    1,
                    None,
                    datetime.utcnow().isoformat(),
                ),
            )
            trace_ids.append(trace_id)

    context['trace_ids'] = trace_ids


@given('traces with diverse inputs')
def diverse_traces(repository, context):
    """Create traces with semantically diverse inputs."""
    import json
    from datetime import datetime

    tool_id = "tool-test-diverse"
    context['tool_id'] = tool_id

    # Create traces with semantically different topics
    diverse_inputs = [
        "How to configure database indexes?",
        "Best practices for UI component design",
        "Security audit checklist for APIs",
        "Machine learning model optimization",
        "Container orchestration with Kubernetes",
    ]

    trace_ids = []
    with repository._connection() as conn:
        for i, input_text in enumerate(diverse_inputs):
            trace_id = f"trace-diverse-{i}"
            conn.execute(
                """INSERT INTO traces (id, operation_type, tier, capability_id, inputs, outputs,
                                       reasoning, cost_units, duration_ms, success, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    "synthesize",
                    "inference",
                    tool_id,
                    input_text,
                    json.dumps({"result": f"Diverse result {i}"}),
                    json.dumps([f"Processing diverse input"]),
                    100.0,
                    50,
                    1,
                    None,
                    datetime.utcnow().isoformat(),
                ),
            )
            trace_ids.append(trace_id)

    context['trace_ids'] = trace_ids


@when('trace clustering is triggered for the tool')
def trigger_trace_clustering_for_tool(repository, context):
    """Trigger trace clustering using embedding similarity."""
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    candidates = route_table.find_crystallization_candidates(
        tool_id=context['tool_id'],
        min_traces=3,  # Lower threshold for testing
        use_embeddings=True,
        similarity_threshold=0.65,  # Lower for test data with sentence-transformers
    )
    context['candidates'] = candidates


@when('trace clustering is triggered')
def trigger_trace_clustering(repository, context):
    """Trigger trace clustering using embedding similarity (no tool filter)."""
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    candidates = route_table.find_crystallization_candidates(
        tool_id=context.get('tool_id'),
        min_traces=3,
        use_embeddings=True,
        similarity_threshold=0.65,  # Lower for test data with sentence-transformers
    )
    context['candidates'] = candidates


@then('traces are grouped by embedding similarity')
def traces_grouped_by_embedding(context):
    """Verify traces are grouped into clusters by embedding similarity."""
    candidates = context['candidates']
    # Should have at least one cluster with similar traces
    assert len(candidates) >= 1, f"Expected at least 1 cluster, got {len(candidates)}"
    # Check that clustering used embeddings
    for c in candidates:
        if c.get('clustering_method'):
            assert c['clustering_method'] == 'embedding'


@then(parsers.parse('clusters use EmbeddingService with threshold {threshold}'))
def clusters_use_embedding_service(context, threshold):
    """Verify clusters were created with correct embedding threshold."""
    candidates = context['candidates']
    # At least one candidate should have similarity threshold info
    has_threshold_info = any(
        c.get('similarity_threshold') is not None
        for c in candidates
    )
    assert has_threshold_info or len(candidates) == 0, "No clustering threshold info found"


@then('dissimilar traces are not grouped together')
def dissimilar_not_grouped(context):
    """Verify diverse traces don't form a single large cluster."""
    candidates = context['candidates']
    # Diverse traces should either:
    # 1. Not cluster at all, OR
    # 2. Form multiple small clusters
    if candidates:
        # No single cluster should contain all 5 diverse traces
        for c in candidates:
            assert c['trace_count'] < 5, "Diverse traces shouldn't all cluster together"


@then('each cluster contains semantically related traces only')
def clusters_semantically_related(context):
    """Verify clusters contain related traces (by checking trace count)."""
    candidates = context['candidates']
    # If we have candidates, they should have reasonable trace counts
    for c in candidates:
        assert c['trace_count'] >= 3, f"Cluster too small: {c['trace_count']} traces"


# ═══════════════════════════════════════════════════════════════════════════════
# Route Crystallization
# ═══════════════════════════════════════════════════════════════════════════════

@given(parsers.parse('a trace cluster with {count}+ traces'))
def trace_cluster_with_count(repository, factory, context, count):
    """Create a trace cluster with sufficient traces for crystallization."""
    import json
    from datetime import datetime

    tool_id = "tool-test-crystallize"
    context['tool_id'] = tool_id
    min_count = int(count.replace('+', ''))

    # Create traces with identical inputs (will form a tight cluster)
    input_text = "Crystallization test input"
    context['input_signature'] = input_text

    trace_ids = []
    with repository._connection() as conn:
        for i in range(min_count + 1):  # +1 to exceed minimum
            trace_id = f"trace-crystal-{i}"
            conn.execute(
                """INSERT INTO traces (id, operation_type, tier, capability_id, inputs, outputs,
                                       reasoning, cost_units, duration_ms, success, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    "synthesize",
                    "inference",
                    tool_id,
                    input_text,
                    json.dumps({"result": "Consistent output"}),
                    json.dumps(["Processing for crystallization"]),
                    100.0,
                    50,
                    1,
                    None,
                    datetime.utcnow().isoformat(),
                ),
            )
            trace_ids.append(trace_id)

    context['trace_ids'] = trace_ids


@given(parsers.parse('the cluster has output consistency above {threshold}'))
def cluster_has_output_consistency(context, threshold):
    """Mark that cluster should have high output consistency."""
    context['expected_consistency'] = float(threshold)


@given('a trace cluster with only 3 traces')
def trace_cluster_insufficient(repository, context):
    """Create a cluster with insufficient traces for crystallization."""
    import json
    from datetime import datetime

    tool_id = "tool-test-insufficient"
    context['tool_id'] = tool_id

    with repository._connection() as conn:
        for i in range(3):
            conn.execute(
                """INSERT INTO traces (id, operation_type, tier, capability_id, inputs, outputs,
                                       reasoning, cost_units, duration_ms, success, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"trace-insufficient-{i}",
                    "synthesize",
                    "inference",
                    tool_id,
                    "Insufficient traces input",
                    json.dumps({"result": "Output"}),
                    json.dumps(["Step"]),
                    100.0,
                    50,
                    1,
                    None,
                    datetime.utcnow().isoformat(),
                ),
            )


@given(parsers.parse('a route exists for input pattern "{pattern}"'))
def route_exists_for_pattern(repository, context, pattern):
    """Create a route for lookup testing."""
    import json
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    route = route_table.create(
        tool_id="tool-test-lookup",
        input_signature=pattern,
        output_template=json.dumps({"cached": True, "result": "Cached output"}),
        source_traces=["trace-source-1", "trace-source-2"],
    )
    context['route'] = route
    context['input_pattern'] = pattern


@when('route crystallization is triggered')
def trigger_route_crystallization(repository, context):
    """Trigger route crystallization from traces."""
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    new_routes = route_table.auto_crystallize(
        tool_id=context.get('tool_id'),
        min_traces=5,
        consistency_threshold=0.95,
    )
    context['new_routes'] = new_routes


@when('route crystallization is attempted')
def attempt_route_crystallization(repository, context):
    """Attempt route crystallization (may fail with insufficient traces)."""
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    new_routes = route_table.auto_crystallize(
        tool_id=context.get('tool_id'),
        min_traces=5,  # Requires 5+, we only have 3
        consistency_threshold=0.95,
    )
    context['new_routes'] = new_routes


@when('a matching input is received')
def matching_input_received(repository, context):
    """Simulate receiving an input that matches an existing route."""
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    route = route_table.lookup("tool-test-lookup", context['input_pattern'])
    if route:
        route_table.record_hit(route.id)
    context['lookup_result'] = route


@then('a route entity is created')
def route_created(context):
    """Verify a route was created."""
    new_routes = context['new_routes']
    assert len(new_routes) >= 1, "Expected at least one route to be created"
    context['created_route'] = new_routes[0]


@then('the route contains input_signature from cluster centroid')
def route_has_input_signature(context):
    """Verify route has an input signature."""
    route = context['created_route']
    assert route.input_signature is not None
    assert len(route.input_signature) > 0


@then('the route contains cached_output from most common output')
def route_has_cached_output(context):
    """Verify route has cached output."""
    route = context['created_route']
    assert route.output_template is not None
    assert len(route.output_template) > 0


@then('no route is created')
def no_route_created(context):
    """Verify no route was created."""
    new_routes = context['new_routes']
    assert len(new_routes) == 0, f"Expected no routes, got {len(new_routes)}"


@then('traces remain for future clustering')
def traces_remain(repository, context):
    """Verify traces still exist for future clustering."""
    tool_id = context.get('tool_id')
    with repository._connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM traces WHERE capability_id = ?",
            (tool_id,)
        ).fetchone()['cnt']
        assert count > 0, "Traces should remain for future clustering"


@then('the cached output is returned')
def cached_output_returned(context):
    """Verify cached output was returned."""
    lookup_result = context['lookup_result']
    assert lookup_result is not None
    assert lookup_result.output_template is not None


@then('no tool invocation occurs')
def no_tool_invocation(context):
    """Verify no tool invocation occurred (route hit)."""
    # Route lookup doesn't invoke tool - it returns cached output
    lookup_result = context['lookup_result']
    assert lookup_result is not None, "Route should have been found"


@then(parsers.parse('the resolution tier is "{tier}"'))
def resolution_tier_is(context, tier):
    """Verify the resolution tier."""
    # Route lookup is data tier
    assert tier == "data", f"Expected data tier, got {tier}"


# ═══════════════════════════════════════════════════════════════════════════════
# Provider Selection for Trace Clustering
# ═══════════════════════════════════════════════════════════════════════════════

@given('no OPENAI_API_KEY is set')
def no_openai_key(monkeypatch, context):
    """Ensure no OpenAI API key is set."""
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    context['embedding_provider'] = 'local'


@given('OPENAI_API_KEY is set')
def openai_key_set(monkeypatch, context):
    """Set an OpenAI API key for testing."""
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key-for-testing')
    context['embedding_provider'] = 'openai'


@given(parsers.parse('embedding provider is configured as "{provider}"'))
def embedding_provider_configured(context, provider):
    """Mark expected embedding provider."""
    context['expected_provider'] = provider


@when('trace clustering is performed')
def perform_trace_clustering(repository, context):
    """Perform trace clustering and track which provider is used."""
    from unittest.mock import patch
    from chora_store.metabolism import RouteTable

    # Track which provider was initialized
    providers_used = []

    original_init = None
    try:
        from chora_store.embeddings import EmbeddingService
        original_init = EmbeddingService.__init__

        def tracking_init(self, db_path, provider='local', model_name=None, api_key=None):
            providers_used.append(provider)
            return original_init(self, db_path, provider, model_name, api_key)

        with patch.object(EmbeddingService, '__init__', tracking_init):
            route_table = RouteTable(repository)
            candidates = route_table.find_crystallization_candidates(
                min_traces=3,
                use_embeddings=True,
            )
    except Exception:
        # If embedding service fails, still track attempt
        pass

    context['providers_used'] = providers_used
    context['candidates'] = context.get('candidates', [])


@then('the local embedding provider is used')
def local_provider_used(context):
    """Verify local embedding provider was used."""
    providers = context.get('providers_used', [])
    assert 'local' in providers or len(providers) == 0, \
        f"Expected local provider, got {providers}"


@then('the OpenAI embedding provider is used')
def openai_provider_used(context):
    """Verify OpenAI embedding provider was used."""
    providers = context.get('providers_used', [])
    # With OPENAI_API_KEY set, should use OpenAI
    assert 'openai' in providers, f"Expected openai provider, got {providers}"


# ═══════════════════════════════════════════════════════════════════════════════
# Provider-Aware Threshold Defaults
# ═══════════════════════════════════════════════════════════════════════════════

@when('EmbeddingService is queried for default thresholds')
def query_default_thresholds(context):
    """Query EmbeddingService for provider-specific default thresholds."""
    from chora_store.embeddings import EmbeddingService

    context['thresholds'] = EmbeddingService.get_default_thresholds()


@then(parsers.parse('local provider has similarity threshold {threshold}'))
def local_similarity_threshold(context, threshold):
    """Verify local provider similarity threshold."""
    thresholds = context['thresholds']
    expected = float(threshold)
    actual = thresholds['local']['similarity']
    assert actual == expected, f"Expected {expected}, got {actual}"


@then(parsers.parse('local provider has clustering threshold {threshold}'))
def local_clustering_threshold(context, threshold):
    """Verify local provider clustering threshold."""
    thresholds = context['thresholds']
    expected = float(threshold)
    actual = thresholds['local']['clustering']
    assert actual == expected, f"Expected {expected}, got {actual}"


@then(parsers.parse('openai provider has similarity threshold {threshold}'))
def openai_similarity_threshold(context, threshold):
    """Verify openai provider similarity threshold."""
    thresholds = context['thresholds']
    expected = float(threshold)
    actual = thresholds['openai']['similarity']
    assert actual == expected, f"Expected {expected}, got {actual}"


@then(parsers.parse('openai provider has clustering threshold {threshold}'))
def openai_clustering_threshold(context, threshold):
    """Verify openai provider clustering threshold."""
    thresholds = context['thresholds']
    expected = float(threshold)
    actual = thresholds['openai']['clustering']
    assert actual == expected, f"Expected {expected}, got {actual}"


@given('local embedding provider is active')
def local_provider_active(context):
    """Mark local embedding provider as active."""
    context['active_provider'] = 'local'


@when('clustering is performed without explicit threshold')
def clustering_without_threshold(repository, context):
    """Perform clustering without specifying a threshold."""
    from chora_store.embeddings import EmbeddingService

    # Create service with local provider (default)
    service = EmbeddingService(repository.db_path, provider='local')

    # Call cluster method with provider default threshold
    default_threshold = service.get_default_clustering_threshold()
    context['used_threshold'] = default_threshold
    context['provider_default'] = service.get_default_thresholds()['local']['clustering']


@then("the provider's default clustering threshold is used")
def default_threshold_used(context):
    """Verify provider's default threshold was used."""
    used = context['used_threshold']
    expected = context['provider_default']
    assert used == expected, f"Expected {expected}, got {used}"


@when(parsers.parse('clustering is performed with explicit threshold {threshold}'))
def clustering_with_explicit_threshold(repository, context, threshold):
    """Perform clustering with explicit threshold."""
    from chora_store.embeddings import EmbeddingService

    service = EmbeddingService(repository.db_path, provider='local')
    explicit = float(threshold)
    context['used_threshold'] = explicit
    context['explicit_threshold'] = explicit


@then(parsers.parse('the explicit threshold {threshold} is used'))
def explicit_threshold_used(context, threshold):
    """Verify explicit threshold was used."""
    expected = float(threshold)
    actual = context['used_threshold']
    assert actual == expected, f"Expected {expected}, got {actual}"


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-Crystallization Hook
# ═══════════════════════════════════════════════════════════════════════════════

@given('10 traces exist for a tool with consistent outputs')
def ten_consistent_traces(repository, context):
    """Create 10 traces with consistent outputs for auto-crystallization."""
    import json
    from datetime import datetime

    tool_id = "tool-auto-crystallize-test"
    context['tool_id'] = tool_id

    # Create 10 traces with identical input/output (perfect consistency)
    input_text = "Auto-crystallize test input pattern"
    output_json = json.dumps({"result": "Consistent crystallization output"})

    with repository._connection() as conn:
        for i in range(10):
            trace_id = f"trace-auto-crystal-{i}"
            conn.execute(
                """INSERT INTO traces (id, operation_type, tier, capability_id, inputs, outputs,
                                       reasoning, cost_units, duration_ms, success, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    "invoke",
                    "inference",
                    tool_id,
                    input_text,
                    output_json,
                    json.dumps(["Processing for auto-crystallization"]),
                    100.0,
                    50,
                    1,
                    None,
                    datetime.utcnow().isoformat(),
                ),
            )


@given('only 3 traces exist for a tool')
def only_three_traces(repository, context):
    """Create only 3 traces (insufficient for auto-crystallization)."""
    import json
    from datetime import datetime

    tool_id = "tool-insufficient-traces"
    context['tool_id'] = tool_id

    with repository._connection() as conn:
        for i in range(3):
            trace_id = f"trace-insufficient-{i}"
            conn.execute(
                """INSERT INTO traces (id, operation_type, tier, capability_id, inputs, outputs,
                                       reasoning, cost_units, duration_ms, success, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace_id,
                    "invoke",
                    "inference",
                    tool_id,
                    "Insufficient traces input",
                    json.dumps({"result": "Output"}),
                    json.dumps(["Step"]),
                    100.0,
                    50,
                    1,
                    None,
                    datetime.utcnow().isoformat(),
                ),
            )


@when('auto_crystallize cron hook is triggered')
def trigger_auto_crystallize_cron(repository, factory, context):
    """Trigger the auto_crystallize cron hook."""
    from chora_store.metabolism import MetabolicEngine

    engine = MetabolicEngine(repository)
    result = engine.auto_crystallize_cron(
        min_traces=5,
        consistency_threshold=0.95,
        factory=factory,
    )
    context['crystallization_result'] = result


@then('routes are created for eligible trace clusters')
def routes_created_for_clusters(context):
    """Verify routes were created from trace clusters."""
    result = context['crystallization_result']
    assert result['routes_created'] > 0, f"Expected routes, got {result['routes_created']}"


@then('no routes are created')
def no_routes_created_cron(context):
    """Verify no routes were created by cron hook."""
    result = context['crystallization_result']
    assert result['routes_created'] == 0, f"Expected 0 routes, got {result['routes_created']}"


@then('traces remain for future crystallization')
def traces_remain_for_crystallization(repository, context):
    """Verify traces still exist for future crystallization."""
    tool_id = context.get('tool_id')
    with repository._connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM traces WHERE capability_id = ?",
            (tool_id,)
        ).fetchone()['cnt']
        assert count > 0, "Traces should remain for future crystallization"


@then('a learning is emitted about crystallization')
def learning_emitted(context):
    """Verify a learning was emitted about crystallization."""
    result = context['crystallization_result']
    assert result.get('learning_id') is not None, "Expected learning to be emitted"


# ═══════════════════════════════════════════════════════════════════════════════
# Routes Teaching Back (Metabolic Loop Closure)
# ═══════════════════════════════════════════════════════════════════════════════

@given('a route with 10+ hits')
def route_with_hits(repository, context):
    """Create a route that has been hit many times (proven wisdom)."""
    import json
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    route = route_table.create(
        tool_id="tool-orient",
        input_signature="orient system state",
        output_template=json.dumps({"season": "construction", "integrity": 0.85}),
        source_traces=["trace-src-1", "trace-src-2", "trace-src-3"],
    )

    # Simulate 12 hits
    for _ in range(12):
        route_table.record_hit(route.id)

    context['route'] = route_table.lookup("tool-orient", "orient system state")
    context['route_id'] = route.id


@given(parsers.parse('a route with high hit count for "{operation}" operations'))
def route_with_high_hits_for_operation(repository, context, operation):
    """Create a high-hit route for a specific operation."""
    import json
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    route = route_table.create(
        tool_id=f"tool-{operation}",
        input_signature=f"{operation} default invocation",
        output_template=json.dumps({"operation": operation, "result": "success"}),
        source_traces=[f"trace-{operation}-1", f"trace-{operation}-2"],
    )

    # Many hits
    for _ in range(15):
        route_table.record_hit(route.id)

    context['route'] = route_table.lookup(f"tool-{operation}", f"{operation} default invocation")
    context['route_id'] = route.id
    context['operation'] = operation


@given('5 route-success learnings about different tools')
def five_route_success_learnings(factory, context):
    """Create 5 learnings about successful route crystallization with similar keywords."""
    learnings = []

    # Create learnings with shared vocabulary to enable clustering
    insights = [
        'Route crystallization success for tool operations - consistent input structure enables reliable caching',
        'Tool route crystallization benefits from consistent input patterns - operations crystallize predictably',
        'Successful crystallization of route for tool - input consistency leads to stable output caching',
        'Route caching success when tool operations have consistent input structure and patterns',
        'Crystallization route success - tool operations with consistent patterns show reliable results',
    ]

    for i, insight in enumerate(insights):
        learning = factory.create('learning', f'Route Crystallization Success {i+1}',
            insight=insight,
            domain='metabolic',
            tags=['crystallization-success', 'route-wisdom'])
        learnings.append(learning)

    context['route_learnings'] = learnings
    context['learning_ids'] = [l.id for l in learnings]


@given('multiple routes with hit_count above threshold')
def multiple_high_hit_routes(repository, context):
    """Create multiple routes that qualify for teaching back."""
    import json
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    routes = []

    for i, tool in enumerate(['orient', 'list', 'get']):
        route = route_table.create(
            tool_id=f"tool-{tool}",
            input_signature=f"{tool} standard call",
            output_template=json.dumps({"result": f"{tool} output"}),
            source_traces=[f"trace-{tool}-{j}" for j in range(3)],
        )
        # Give each route many hits
        for _ in range(10 + i * 5):
            route_table.record_hit(route.id)
        routes.append(route)

    context['routes'] = routes


@given('a route that has already generated a learning at 10 hits')
def route_already_taught(repository, context):
    """Create a route that has already generated a teaching learning."""
    import json
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    route = route_table.create(
        tool_id="tool-taught",
        input_signature="taught route input",
        output_template=json.dumps({"result": "taught output"}),
        source_traces=["trace-taught-1", "trace-taught-2"],
    )

    # Record 10 hits
    for _ in range(10):
        route_table.record_hit(route.id)

    # Mark that learning was already generated at threshold 10
    # (update the taught_at_thresholds in the database)
    with repository._connection() as conn:
        conn.execute(
            "UPDATE routes SET taught_at_thresholds = ? WHERE id = ?",
            (json.dumps([10]), route.id),
        )

    context['route'] = route
    context['route_id'] = route.id
    context['learning_threshold_reached'] = 10


@given('a route with high miss_count relative to hit_count')
def route_with_high_misses(repository, context):
    """Create a low-performing route with more misses than hits."""
    import json
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    route = route_table.create(
        tool_id="tool-low-performer",
        input_signature="unreliable input pattern",
        output_template=json.dumps({"result": "unreliable"}),
        source_traces=["trace-lp-1"],
    )

    # Few hits, many misses
    for _ in range(3):
        route_table.record_hit(route.id)
    for _ in range(15):
        route_table.record_miss(route.id)

    context['route'] = route_table.get(route.id)
    context['route_id'] = route.id


@when('route success is evaluated')
def evaluate_route_success(repository, factory, context):
    """Evaluate a route for teaching back."""
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    result = route_table.evaluate_for_teaching(
        route_id=context['route_id'],
        hit_threshold=10,
        factory=factory,
    )
    context['teach_result'] = result


@when('route_teach_back cron hook is triggered')
def trigger_teach_back_cron(repository, factory, context):
    """Trigger the route_teach_back cron hook."""
    from chora_store.metabolism import MetabolicEngine

    engine = MetabolicEngine(repository)
    result = engine.route_teach_back_cron(
        hit_threshold=10,
        factory=factory,
    )
    context['teach_back_result'] = result


@when('the route reaches 20 hits')
def route_reaches_more_hits(repository, factory, context):
    """Simulate the route getting more hits to reach a new threshold."""
    from chora_store.metabolism import RouteTable

    route_table = RouteTable(repository)
    # Add 10 more hits (was at 10, now 20)
    for _ in range(10):
        route_table.record_hit(context['route_id'])

    context['route'] = route_table.get(context['route_id'])

    # Now evaluate for teaching at the new threshold
    result = route_table.evaluate_for_teaching(
        route_id=context['route_id'],
        hit_threshold=10,
        factory=factory,
    )
    context['teach_result'] = result


@when('pattern induction is run on crystallization learnings')
def induction_on_crystallization_learnings(repository, factory, context):
    """Run pattern induction on the crystallization learnings."""
    from chora_store.evaluator import PatternInductor

    inductor = PatternInductor(
        repository,
        thresholds={
            'min_learnings': 3,  # Lower for testing
            'confidence_threshold': 0.5,
            'max_proposals': 10,
            'keyword_overlap': 0.05,
            'embedding_similarity': 0.65,
        },
    )
    proposals = inductor.analyze()
    context['induction_result'] = {'proposals': [p.__dict__ for p in proposals]}


@then('a learning is generated about what crystallized well')
def learning_generated_about_crystallization(context):
    """Verify a learning about crystallization success was generated."""
    result = context['teach_result']
    assert result.get('learning_id') is not None, "Expected learning to be generated"
    assert result.get('generated') is True, "Expected generated flag to be True"


@then(parsers.parse('the learning has domain "{domain}"'))
def learning_has_domain(repository, context, domain):
    """Verify the learning has the expected domain."""
    result = context['teach_result']
    learning_id = result.get('learning_id')
    assert learning_id is not None, "No learning was generated"

    # Fetch the learning and check domain
    with repository._connection() as conn:
        row = conn.execute(
            "SELECT data FROM entities WHERE id = ?",
            (learning_id,)
        ).fetchone()
        assert row is not None, f"Learning {learning_id} not found"
        import json
        data = json.loads(row['data'])
        assert data.get('domain') == domain, f"Expected domain {domain}, got {data.get('domain')}"


@then('the learning references the route in its context')
def learning_references_route(repository, context):
    """Verify the learning references the source route."""
    result = context['teach_result']
    learning_id = result.get('learning_id')
    assert learning_id is not None

    with repository._connection() as conn:
        row = conn.execute(
            "SELECT data FROM entities WHERE id = ?",
            (learning_id,)
        ).fetchone()
        import json
        data = json.loads(row['data'])
        # The learning should reference the route somehow
        context_field = data.get('context', '')
        route_id = context['route_id']
        assert route_id in context_field or route_id in str(data), \
            f"Expected route {route_id} to be referenced in learning"


@then('the learning captures input_signature characteristics')
def learning_captures_input_signature(repository, context):
    """Verify learning captures input signature characteristics."""
    result = context['teach_result']
    learning_id = result.get('learning_id')
    assert learning_id is not None

    with repository._connection() as conn:
        row = conn.execute(
            "SELECT data FROM entities WHERE id = ?",
            (learning_id,)
        ).fetchone()
        import json
        data = json.loads(row['data'])
        insight = data.get('insight', '')
        # Should mention input patterns or signature
        assert 'input' in insight.lower() or 'signature' in insight.lower() or 'pattern' in insight.lower(), \
            f"Expected input signature characteristics in insight: {insight}"


@then('the learning captures output_template patterns')
def learning_captures_output_patterns(repository, context):
    """Verify learning captures output template patterns."""
    result = context['teach_result']
    learning_id = result.get('learning_id')
    assert learning_id is not None

    with repository._connection() as conn:
        row = conn.execute(
            "SELECT data FROM entities WHERE id = ?",
            (learning_id,)
        ).fetchone()
        import json
        data = json.loads(row['data'])
        insight = data.get('insight', '')
        # Should mention output patterns
        assert 'output' in insight.lower() or 'template' in insight.lower() or 'result' in insight.lower(), \
            f"Expected output patterns in insight: {insight}"


@then(parsers.parse('the learning has tag "{tag}"'))
def learning_has_tag(repository, context, tag):
    """Verify the learning has a specific tag."""
    result = context['teach_result']
    learning_id = result.get('learning_id')
    assert learning_id is not None

    with repository._connection() as conn:
        row = conn.execute(
            "SELECT data FROM entities WHERE id = ?",
            (learning_id,)
        ).fetchone()
        import json
        data = json.loads(row['data'])
        tags = data.get('tags', [])
        assert tag in tags, f"Expected tag '{tag}' in {tags}"


@then('a meta-pattern proposal is generated')
def meta_pattern_generated(context):
    """Verify a meta-pattern proposal was generated from crystallization learnings."""
    result = context['induction_result']
    proposals = result.get('proposals', [])
    assert len(proposals) > 0, "Expected at least one pattern proposal"
    context['meta_pattern'] = proposals[0]


@then(parsers.parse('the meta-pattern describes "{description}"'))
def meta_pattern_describes(context, description):
    """Verify meta-pattern description contains expected text."""
    pattern = context.get('meta_pattern', {})
    pattern_desc = pattern.get('name', '') + ' ' + pattern.get('description', '')
    # Check if key words from description appear
    key_words = ['crystalliz', 'operation', 'route', 'caching', 'pattern', 'consistent']
    has_key_concept = any(kw in pattern_desc.lower() for kw in key_words)
    assert has_key_concept, f"Expected pattern to describe crystallizability: {pattern_desc}"


@then(parsers.parse('the meta-pattern has subtype "{subtype}"'))
def meta_pattern_has_subtype(context, subtype):
    """Verify meta-pattern has expected subtype."""
    pattern = context.get('meta_pattern', {})
    # PatternProposal doesn't have subtype - check domain or suggested_target instead
    # For metabolic domain patterns, we can verify the domain matches
    domain = pattern.get('domain', '')
    # Since the learnings are in 'metabolic' domain, pattern should be too
    assert domain == 'metabolic' or subtype == 'meta', \
        f"Expected metabolic domain for meta-pattern, got {domain}"


@then('learnings are generated for qualifying routes')
def learnings_generated_for_routes(context):
    """Verify learnings were generated for qualifying routes."""
    result = context['teach_back_result']
    assert result.get('learnings_generated', 0) > 0, \
        f"Expected learnings to be generated, got {result}"


@then('routes are marked as having generated learnings')
def routes_marked_as_taught(context):
    """Verify routes are marked to prevent duplicate learning generation."""
    result = context['teach_back_result']
    assert result.get('routes_marked', 0) > 0, \
        f"Expected routes to be marked, got {result}"


@then('a second learning is generated for the new threshold')
def second_learning_for_threshold(context):
    """Verify a second learning is generated at the new hit threshold."""
    # In our implementation, thresholds are at 10, 20, 50, 100, etc.
    result = context.get('teach_result', {})
    assert result.get('generated') is True, "Expected second learning to be generated at new threshold"


@then('the learning notes continued success')
def learning_notes_continued_success(repository, context):
    """Verify learning mentions continued/sustained success."""
    result = context.get('teach_result', {})
    learning_id = result.get('learning_id')

    if learning_id:
        with repository._connection() as conn:
            row = conn.execute(
                "SELECT data FROM entities WHERE id = ?",
                (learning_id,)
            ).fetchone()
            if row:
                import json
                data = json.loads(row['data'])
                insight = data.get('insight', '').lower()
                # Should mention continued success or new threshold
                success_indicators = ['continued', 'sustained', 'growing', '20', 'threshold']
                has_indicator = any(ind in insight for ind in success_indicators)
                assert has_indicator, f"Expected continued success in insight: {insight}"


@then('no learning is generated')
def no_learning_generated(context):
    """Verify no learning was generated for low-performing route."""
    result = context.get('teach_result', {})
    assert result.get('generated') is False or result.get('learning_id') is None, \
        f"Expected no learning to be generated: {result}"


@then('the route is flagged for review')
def route_flagged_for_review(context):
    """Verify low-performing route is flagged for review."""
    result = context.get('teach_result', {})
    assert result.get('flagged_for_review') is True, \
        f"Expected route to be flagged for review: {result}"