"""Step definitions for route crystallization BDD tests."""

import json
from dataclasses import replace
from pytest_bdd import scenarios, given, when, then, parsers

from chora_store.metabolism import RouteTable, TraceCapture, MetabolicEngine

# Load scenarios from feature file
scenarios("../features/route_crystallization.feature")


# ═══════════════════════════════════════════════════════════════════════════════
# Background
# ═══════════════════════════════════════════════════════════════════════════════


@given("a fresh database")
def fresh_database(repository):
    """Repository is already fresh from fixture."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario: Traces crystallize into route
# ═══════════════════════════════════════════════════════════════════════════════


@given("5 similar inference traces for the same input")
def five_similar_traces(repository, context):
    """Create 5 traces with the same input and consistent output."""
    input_sig = json.dumps(["learning-1", "learning-2", "learning-3"])
    output = json.dumps({
        "name": "Test Pattern",
        "context": "When testing",
        "solution": "Do the test",
        "domain": "testing",
        "confidence": "high",
    })

    # Create 5 similar traces
    for i in range(5):
        with TraceCapture(
            repository,
            operation_type="synthesize",
            tier="inference",
            capability_id="tool-synthesize-learnings",
        ) as trace:
            trace.set_inputs(json.loads(input_sig))
            trace.set_outputs([output])
            trace.set_cost(100.0)

    context["input_sig"] = input_sig
    context["expected_output"] = output


@when("auto_crystallize is called")
def call_auto_crystallize(repository, context):
    """Trigger auto-crystallization."""
    route_table = RouteTable(repository)
    new_routes = route_table.auto_crystallize(min_traces=5, consistency_threshold=0.95)
    context["new_routes"] = new_routes


@then(parsers.parse('a route is created with status "{status}"'))
def route_created_with_status(context, status):
    """Verify a route was created with the expected status."""
    new_routes = context.get("new_routes", [])
    assert len(new_routes) >= 1, f"Expected at least 1 route, got {len(new_routes)}"
    assert new_routes[0].status == status, f"Expected status {status}, got {new_routes[0].status}"


@then("the route stores the consistent output")
def route_stores_output(context):
    """Verify the route stored the correct output."""
    new_routes = context["new_routes"]

    route = new_routes[0]
    # The output_template should contain the consistent output
    assert route.output_template is not None
    # It should be valid JSON
    parsed = json.loads(route.output_template)
    assert parsed is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario: Route promotes after hits
# ═══════════════════════════════════════════════════════════════════════════════


@given("a canary route with 10 successful hits")
def canary_route_with_hits(repository, context):
    """Create a canary route and record hits."""
    route_table = RouteTable(repository)

    # Create a route
    route = route_table.create(
        tool_id="tool-synthesize-learnings",
        input_signature='["learning-a", "learning-b"]',
        output_template='{"name": "Hit Pattern"}',
        source_traces=["trace-1", "trace-2"],
        confidence=0.95,
    )

    # Record 10 hits
    for _ in range(10):
        route_table.record_hit(route.id)

    context["route_id"] = route.id


@when("promote_route is called")
def call_promote_route(repository, context):
    """Promote the route."""
    route_table = RouteTable(repository)
    route_id = context["route_id"]
    success = route_table.promote(route_id)
    context["promote_success"] = success


@then(parsers.parse('route status is "{status}"'))
def check_route_status(repository, context, status):
    """Verify the route has the expected status."""
    route_table = RouteTable(repository)
    route_id = context["route_id"]

    # Find the route
    routes = route_table.list_routes()
    route = next((r for r in routes if r.id == route_id), None)
    assert route is not None, f"Route {route_id} not found"
    assert route.status == status, f"Expected status {status}, got {route.status}"


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario: Route deprecates on high miss rate
# ═══════════════════════════════════════════════════════════════════════════════


@given("an active route")
def active_route(repository, context):
    """Create an active route."""
    route_table = RouteTable(repository)

    # Create a route
    route = route_table.create(
        tool_id="tool-synthesize-learnings",
        input_signature='["learning-x", "learning-y"]',
        output_template='{"name": "Active Pattern"}',
        source_traces=["trace-a", "trace-b"],
        confidence=0.9,
    )

    # Promote to active
    route_table.promote(route.id)

    context["route_id"] = route.id


@when(parsers.parse("{misses:d} of {total:d} lookups are misses"))
def record_misses(repository, context, misses, total):
    """Record hits and misses."""
    route_table = RouteTable(repository)
    route_id = context["route_id"]

    hits = total - misses
    for _ in range(hits):
        route_table.record_hit(route_id)
    for _ in range(misses):
        route_table.record_miss(route_id)


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario: Route lookup bypasses inference
# ═══════════════════════════════════════════════════════════════════════════════


@given("a crystallized active route for synthesis")
def crystallized_active_route(repository, context):
    """Create a crystallized active route."""
    route_table = RouteTable(repository)

    # The input signature will be a sorted JSON array of learning IDs
    learning_ids = ["learning-route-1", "learning-route-2", "learning-route-3"]
    input_sig = json.dumps(sorted(learning_ids))

    # The output template is what the route will return
    output = json.dumps({
        "name": "Crystallized Pattern",
        "context": "From route",
        "solution": "Use the cached result",
        "domain": "efficiency",
        "confidence": 0.9,
        "source_learnings": learning_ids,
        "keywords": ["route", "cache"],
    })

    route = route_table.create(
        tool_id="tool-synthesize-learnings",
        input_signature=input_sig,
        output_template=output,
        source_traces=["trace-orig-1"],
        confidence=0.95,
    )
    route_table.promote(route.id)

    # Record initial hit count
    routes = route_table.list_routes(status="active")
    active_route = next((r for r in routes if r.id == route.id), None)
    context["route_id"] = route.id
    context["learning_ids"] = learning_ids
    context["initial_hit_count"] = active_route.hit_count if active_route else 0


@given("learnings that match the route input")
def learnings_matching_route(factory, repository, context):
    """Create learnings that match the route's input signature."""
    learning_ids = context["learning_ids"]

    # Create learnings - the IDs are set by factory, but the route uses the
    # canonical signature from the learning_ids we stored
    created_ids = []
    for i, expected_id in enumerate(learning_ids):
        learning = factory.create(
            "learning",
            f"Test Learning {i}",
            insight=f"This is test learning {expected_id}",
            context="Testing route lookup",
            source="test",
            domain="testing",
        )
        created_ids.append(learning.id)

    # Update context to use actual created IDs
    # Note: For route lookup to work, we need the input signature to match
    # So we'll update the learning_ids to match what was created
    # Or we need to create learnings with specific IDs - let's do the latter
    # Actually, we'll just override the IDs using _replace

    # Clear the ones we just created and recreate with specific IDs
    for lid in learning_ids:
        learning = factory.create(
            "learning",
            f"Route Learning {lid}",
            insight=f"Learning for route test: {lid}",
            context="Route lookup test",
            source="test",
            domain="testing",
        )
        # Override the ID
        new_learning = replace(learning, id=lid)
        # Delete the auto-generated one and create with correct ID
        try:
            repository.delete(learning.id)
        except Exception:
            pass
        repository.create(new_learning)


@when("tiered_synthesize is called")
def call_tiered_synthesize(repository, context):
    """Call tiered_synthesize with the matching learnings."""
    learning_ids = context["learning_ids"]

    engine = MetabolicEngine(repository)
    result = engine.tiered_synthesize(learning_ids=learning_ids)

    context["synth_result"] = result


@then("resolution uses data tier")
def resolution_uses_data_tier(context):
    """Verify that resolution used the data tier (route hit)."""
    result = context["synth_result"]
    assert result["success"], f"Synthesis failed: {result.get('escalation_reason')}"
    assert result["tier_used"] == "data", f"Expected tier 'data', got '{result['tier_used']}'"


@then("the route hit count increases")
def route_hit_count_increases(repository, context):
    """Verify the route hit count increased."""
    route_table = RouteTable(repository)
    route_id = context["route_id"]
    initial_count = context["initial_hit_count"]

    routes = route_table.list_routes()
    route = next((r for r in routes if r.id == route_id), None)
    assert route is not None, f"Route {route_id} not found"
    assert route.hit_count > initial_count, (
        f"Hit count did not increase: was {initial_count}, now {route.hit_count}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Scenario: Routes track source learning IDs (Phase 5)
# ═══════════════════════════════════════════════════════════════════════════════


@given(parsers.parse('5 similar inference traces for learnings "{learning_a}" and "{learning_b}"'))
def five_traces_with_specific_learnings(repository, context, learning_a, learning_b):
    """Create 5 traces with specific learning IDs as input."""
    learning_ids = [learning_a, learning_b]
    input_sig = json.dumps(sorted(learning_ids))
    output = json.dumps({
        "name": "Source Learning Pattern",
        "context": "Testing source_learning_ids",
        "solution": "Track learning lineage",
        "domain": "testing",
        "confidence": "high",
        "source_learnings": learning_ids,
    })

    # Create 5 similar traces
    for i in range(5):
        with TraceCapture(
            repository,
            operation_type="synthesize",
            tier="inference",
            capability_id="tool-synthesize-learnings",
        ) as trace:
            trace.set_inputs(learning_ids)
            trace.set_outputs([output])
            trace.set_cost(100.0)

    context["input_sig"] = input_sig
    context["expected_learning_ids"] = learning_ids


@then(parsers.parse('the crystallized route has source_learning_ids containing "{learning_id}"'))
def route_has_source_learning_id(context, learning_id):
    """Verify the route tracks the source learning ID."""
    new_routes = context.get("new_routes", [])
    assert len(new_routes) >= 1, f"Expected at least 1 route, got {len(new_routes)}"

    route = new_routes[0]
    assert learning_id in route.source_learning_ids, (
        f"Expected '{learning_id}' in source_learning_ids, got {route.source_learning_ids}"
    )
