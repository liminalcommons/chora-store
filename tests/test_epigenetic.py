"""
Tests for the Epigenetic Bridge - Schema extension and hook execution.

The Epigenetic Bridge allows experimental patterns to:
1. Inject fields into entity schemas at runtime
2. Define hooks that modulate system behavior
3. All without modifying the kernel physics
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import tempfile
import os

from chora_store.factory import EntityFactory
from chora_store.observer import (
    EntityObserver,
    EpigeneticHook,
    HookResult,
    ChangeType,
)
from chora_store.repository import EntityRepository
from chora_store.models import Entity


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def repository(temp_db):
    """Create a repository with temp database."""
    return EntityRepository(db_path=temp_db)


@pytest.fixture
def observer():
    """Create a fresh observer."""
    return EntityObserver()


def make_pattern_entity(
    pattern_id: str = "pattern-feature-ttl",
    target: str = "feature",
    status: str = "experimental",
    inject_fields: dict = None,
    hooks: list = None,
) -> Entity:
    """Helper to create schema-extension pattern entities."""
    if inject_fields is None:
        inject_fields = {
            "ttl_days": {
                "type": "integer",
                "default": 30,
                "description": "Days before TTL expires",
            }
        }
    if hooks is None:
        hooks = [
            {
                "id": "check-ttl",
                "trigger": "cron:daily",
                "condition": "entity_type == 'feature' and entity_status == 'nascent' and days_since_created > entity_ttl_days",
                "action": "transition(status='drifting')",
            }
        ]

    return Entity(
        id=pattern_id,
        type="pattern",
        status=status,
        data={
            "name": "Feature TTL Pattern",
            "subtype": "schema-extension",
            "mechanics": {
                "target": target,
                "inject_fields": inject_fields,
                "hooks": hooks,
            },
        },
    )


def make_feature_entity(
    feature_id: str = "feature-test",
    status: str = "nascent",
    created_days_ago: int = 0,
    ttl_days: int = None,
    epigenetics: list = None,
) -> Entity:
    """Helper to create feature entities for testing."""
    created = datetime.utcnow() - timedelta(days=created_days_ago)
    data = {
        "name": "Test Feature",
        "created": created.isoformat(),
        "updated": datetime.utcnow().isoformat(),
    }
    if ttl_days is not None:
        data["ttl_days"] = ttl_days
    if epigenetics is not None:
        data["_epigenetics"] = epigenetics

    return Entity(
        id=feature_id,
        type="feature",
        status=status,
        data=data,
        created_at=created,
        updated_at=datetime.utcnow(),
    )


class TestEpigeneticHookLoading:
    """Test loading hooks from experimental patterns."""

    def test_load_hooks_from_experimental_pattern(self, repository, observer):
        """Test that hooks are loaded from experimental patterns."""
        # Create an experimental schema-extension pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Load hooks
        hooks = observer.load_epigenetic_hooks(repository, "cron:daily")

        assert len(hooks) == 1
        assert hooks[0].hook_id == "check-ttl"
        assert hooks[0].pattern_id == "pattern-feature-ttl"
        assert hooks[0].target_type == "feature"

    def test_ignore_non_experimental_patterns(self, repository, observer):
        """Test that non-experimental patterns are ignored."""
        pattern = make_pattern_entity(status="adopted")
        repository.create(pattern)

        hooks = observer.load_epigenetic_hooks(repository, "cron:daily")
        assert len(hooks) == 0

    def test_ignore_non_schema_extension_patterns(self, repository, observer):
        """Test that non-schema-extension patterns are ignored."""
        pattern = Entity(
            id="pattern-other",
            type="pattern",
            status="experimental",
            data={
                "name": "Other Pattern",
                "subtype": "process",  # Not schema-extension
            },
        )
        repository.create(pattern)

        hooks = observer.load_epigenetic_hooks(repository, "cron:daily")
        assert len(hooks) == 0

    def test_filter_hooks_by_trigger_type(self, repository, observer):
        """Test that hooks are filtered by trigger type."""
        pattern = make_pattern_entity(
            hooks=[
                {"id": "hook-daily", "trigger": "cron:daily", "condition": "true", "action": "noop"},
                {"id": "hook-hourly", "trigger": "cron:hourly", "condition": "true", "action": "noop"},
            ]
        )
        repository.create(pattern)

        daily_hooks = observer.load_epigenetic_hooks(repository, "cron:daily")
        assert len(daily_hooks) == 1
        assert daily_hooks[0].hook_id == "hook-daily"

        hourly_hooks = observer.load_epigenetic_hooks(repository, "cron:hourly")
        assert len(hourly_hooks) == 1
        assert hourly_hooks[0].hook_id == "hook-hourly"


class TestConditionEvaluation:
    """Test hook condition evaluation."""

    def test_simple_type_condition(self, observer):
        """Test evaluating simple entity type condition."""
        entity = make_feature_entity()
        result = observer._evaluate_condition("entity_type == 'feature'", entity)
        assert result is True

    def test_simple_status_condition(self, observer):
        """Test evaluating simple status condition."""
        entity = make_feature_entity(status="nascent")
        result = observer._evaluate_condition("entity_status == 'nascent'", entity)
        assert result is True

        entity = make_feature_entity(status="stable")
        result = observer._evaluate_condition("entity_status == 'nascent'", entity)
        assert result is False

    def test_entity_field_condition(self, observer):
        """Test evaluating condition with entity data fields."""
        entity = make_feature_entity(ttl_days=30)
        result = observer._evaluate_condition("entity_ttl_days == 30", entity)
        assert result is True

    def test_days_since_condition(self, observer):
        """Test evaluating days_since condition."""
        # Entity created 45 days ago
        entity = make_feature_entity(created_days_ago=45, ttl_days=30)
        result = observer._evaluate_condition(
            "days_since_created > entity_ttl_days",
            entity
        )
        assert result is True

        # Entity created 15 days ago
        entity = make_feature_entity(created_days_ago=15, ttl_days=30)
        result = observer._evaluate_condition(
            "days_since_created > entity_ttl_days",
            entity
        )
        assert result is False

    def test_compound_condition(self, observer):
        """Test evaluating compound AND condition."""
        entity = make_feature_entity(
            status="nascent",
            created_days_ago=45,
            ttl_days=30,
        )
        result = observer._evaluate_condition(
            "entity_type == 'feature' and entity_status == 'nascent' and days_since_created > entity_ttl_days",
            entity
        )
        assert result is True

    def test_invalid_condition_returns_false(self, observer):
        """Test that invalid conditions return False."""
        entity = make_feature_entity()
        result = observer._evaluate_condition("invalid syntax {{{{", entity)
        assert result is False


class TestActionExecution:
    """Test hook action execution."""

    def test_transition_action(self, repository, observer):
        """Test executing transition action."""
        # Create a feature
        feature = make_feature_entity(status="nascent")
        repository.create(feature)

        # Execute transition action
        result = observer._execute_action(
            "transition(status='drifting')",
            feature,
            repository,
        )

        assert "drifting" in result

        # Verify entity was updated
        updated = repository.read(feature.id)
        assert updated.status == "drifting"

    def test_unknown_action(self, repository, observer):
        """Test unknown action returns message."""
        feature = make_feature_entity()
        result = observer._execute_action("unknown_action()", feature, repository)
        assert "Unknown action" in result


class TestRunEpigeneticHooks:
    """Test end-to-end hook execution."""

    def test_run_hooks_transitions_expired_features(self, repository, observer):
        """Test that running hooks transitions features past TTL."""
        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Create a feature that should trigger (45 days old, 30 day TTL)
        feature = make_feature_entity(
            feature_id="feature-old",
            status="nascent",
            created_days_ago=45,
            ttl_days=30,
            epigenetics=["pattern-feature-ttl"],
        )
        repository.create(feature)

        # Run hooks
        results = observer.run_epigenetic_hooks(repository, "cron:daily")

        # Verify hook matched and acted
        assert len(results) == 1
        assert results[0].matched is True
        assert results[0].action_taken is not None
        assert "drifting" in results[0].action_taken

        # Verify entity was transitioned
        updated = repository.read("feature-old")
        assert updated.status == "drifting"

    def test_run_hooks_skips_fresh_features(self, repository, observer):
        """Test that hooks skip features within TTL."""
        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Create a fresh feature (5 days old, 30 day TTL)
        feature = make_feature_entity(
            feature_id="feature-fresh",
            status="nascent",
            created_days_ago=5,
            ttl_days=30,
            epigenetics=["pattern-feature-ttl"],
        )
        repository.create(feature)

        # Run hooks
        results = observer.run_epigenetic_hooks(repository, "cron:daily")

        # Verify hook did not match
        assert len(results) == 1
        assert results[0].matched is False
        assert results[0].action_taken is None

        # Verify entity was NOT transitioned
        unchanged = repository.read("feature-fresh")
        assert unchanged.status == "nascent"

    def test_run_hooks_skips_non_epigenetic_entities(self, repository, observer):
        """Test that hooks skip entities without epigenetic tagging."""
        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Create a feature WITHOUT epigenetic tagging
        feature = make_feature_entity(
            feature_id="feature-plain",
            status="nascent",
            created_days_ago=45,
            ttl_days=30,
            epigenetics=None,  # No epigenetic tagging
        )
        repository.create(feature)

        # Run hooks
        results = observer.run_epigenetic_hooks(repository, "cron:daily")

        # Should have no results (entity skipped)
        assert len(results) == 0

        # Verify entity was NOT transitioned
        unchanged = repository.read("feature-plain")
        assert unchanged.status == "nascent"


@pytest.fixture
def kernel_path():
    """Get the path to chora-kernel."""
    # When running tests from packages/chora-store, kernel is at ../../packages/chora-kernel
    # or from workspace root at packages/chora-kernel
    import os

    # Try various paths
    candidates = [
        "packages/chora-kernel",  # From workspace root
        "../chora-kernel",  # From packages/chora-store
        "../../packages/chora-kernel",  # From packages/chora-store/tests
    ]

    for path in candidates:
        schema_path = os.path.join(path, "standards", "entity.yaml")
        if os.path.exists(schema_path):
            return path

    # Fallback: construct absolute path
    test_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(test_dir, "..", "..", "chora-kernel")


class TestFactoryEpigeneticSchema:
    """Test factory's epigenetic schema extension."""

    def test_factory_loads_experimental_patterns(self, repository, kernel_path):
        """Test that factory loads experimental patterns."""
        factory = EntityFactory(
            kernel_path=kernel_path,
            repository=repository,
        )

        # Create experimental pattern in repository
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Load patterns
        patterns = factory._load_experimental_patterns("feature")
        assert len(patterns) == 1
        assert patterns[0].id == "pattern-feature-ttl"

    def test_get_effective_schema_merges_fields(self, repository, kernel_path):
        """Test that effective schema includes epigenetic fields."""
        factory = EntityFactory(
            kernel_path=kernel_path,
            repository=repository,
        )

        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Get effective schema
        type_schema, applied_patterns = factory._get_effective_schema("feature")

        # Verify pattern was applied
        assert "pattern-feature-ttl" in applied_patterns

        # Verify field was merged into additional_optional
        optional_fields = type_schema.get("additional_optional", [])
        assert "ttl_days" in optional_fields

        # Verify epigenetic field definition was stored
        epigenetic_fields = type_schema.get("_epigenetic_fields", {})
        assert "ttl_days" in epigenetic_fields

    def test_apply_epigenetic_defaults(self, repository, kernel_path):
        """Test that epigenetic defaults are applied."""
        factory = EntityFactory(
            kernel_path=kernel_path,
            repository=repository,
        )

        # Create experimental pattern
        pattern = make_pattern_entity()
        repository.create(pattern)

        # Get effective schema
        type_schema, _ = factory._get_effective_schema("feature")

        # Apply defaults to empty data
        data = {}
        data = factory._apply_epigenetic_defaults("feature", data, type_schema)

        # Verify default was applied
        assert data.get("ttl_days") == 30


# ═══════════════════════════════════════════════════════════════════════════
# PATTERN EVALUATOR TESTS - Fitness Engine (SELECT mechanism)
# ═══════════════════════════════════════════════════════════════════════════

from chora_store.evaluator import PatternEvaluator, MetricResult, FitnessReport


def make_pattern_with_fitness(
    pattern_id: str = "pattern-test-fitness",
    observation_period: str = "90 days",
    sample_size: int = 5,
    metrics: list = None,
    success_condition: str = "",
    failure_condition: str = "",
) -> Entity:
    """Helper to create pattern with fitness criteria."""
    if metrics is None:
        metrics = [
            {
                "name": "test_metric",
                "description": "Test metric",
                "baseline": 0.5,
                "target": 0.2,
                "direction": "lower_is_better",
                "query": "count(features WHERE status='stable') / count(features WHERE ttl_days IS NOT NULL)",
            }
        ]

    return Entity(
        id=pattern_id,
        type="pattern",
        status="experimental",
        data={
            "name": "Test Fitness Pattern",
            "subtype": "schema-extension",
            "experimental_since": (datetime.utcnow() - timedelta(days=30)).isoformat(),
            "mechanics": {
                "target": "feature",
                "inject_fields": {
                    "ttl_days": {"type": "integer", "default": 30},
                },
                "hooks": [],
                "fitness": {
                    "observation_period": observation_period,
                    "sample_size": sample_size,
                    "metrics": metrics,
                    "success_condition": success_condition,
                    "failure_condition": failure_condition,
                    "on_success": [
                        {"action": "transition(pattern.status='adopted')"},
                        {"action": "create(learning, title='Pattern succeeded')"},
                    ],
                    "on_failure": [
                        {"action": "transition(pattern.status='deprecated')"},
                        {"action": "finalize(pattern)"},
                    ],
                },
            },
        },
    )


class TestPatternEvaluatorLoading:
    """Test loading patterns for evaluation."""

    def test_loads_experimental_schema_extension_patterns(self, repository):
        """Test that evaluator loads only experimental schema-extension patterns."""
        evaluator = PatternEvaluator(repository)

        # Create experimental pattern
        pattern = make_pattern_with_fitness()
        repository.create(pattern)

        # Create adopted pattern (should be ignored)
        adopted = Entity(
            id="pattern-adopted",
            type="pattern",
            status="adopted",
            data={"subtype": "schema-extension"},
        )
        repository.create(adopted)

        patterns = evaluator._load_experimental_patterns()
        assert len(patterns) == 1
        assert patterns[0].id == "pattern-test-fitness"

    def test_parse_observation_period(self, repository):
        """Test parsing observation period strings."""
        evaluator = PatternEvaluator(repository)

        assert evaluator._parse_observation_period("90 days") == 90
        assert evaluator._parse_observation_period("60 day") == 60
        assert evaluator._parse_observation_period("30 Days") == 30
        assert evaluator._parse_observation_period("invalid") == 90  # Default


class TestMetricCalculation:
    """Test fitness metric calculations."""

    def test_count_entities_with_pattern(self, repository):
        """Test counting entities tagged with a pattern."""
        evaluator = PatternEvaluator(repository)

        # Create pattern
        pattern = make_pattern_with_fitness()
        repository.create(pattern)

        # Create features with epigenetic tagging
        for i in range(3):
            feature = make_feature_entity(
                feature_id=f"feature-tagged-{i}",
                status="nascent",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        # Create feature without tagging
        untagged = make_feature_entity(
            feature_id="feature-untagged",
            status="nascent",
        )
        repository.create(untagged)

        count = evaluator._count_entities_with_pattern(
            "pattern-test-fitness", "feature"
        )
        assert count == 3

    def test_count_with_status_filter(self, repository):
        """Test counting with status filter."""
        evaluator = PatternEvaluator(repository)

        # Create features with different statuses
        for status in ["nascent", "converging", "stable"]:
            feature = make_feature_entity(
                feature_id=f"feature-{status}",
                status=status,
                epigenetics=["pattern-test"],
            )
            repository.create(feature)

        stable_count = evaluator._count_entities_with_pattern(
            "pattern-test", "feature", status="stable"
        )
        assert stable_count == 1

    def test_calculate_ratio_metric(self, repository):
        """Test calculating a ratio metric."""
        evaluator = PatternEvaluator(repository)

        # Create pattern
        pattern = make_pattern_with_fitness(metrics=[
            {
                "name": "stability_rate",
                "description": "Ratio of stable features",
                "baseline": 0.3,
                "target": 0.5,
                "direction": "higher_is_better",
                "query": "count(features WHERE status='stable') / count(features WHERE status='nascent')",
            }
        ])
        repository.create(pattern)

        # Create features: 2 stable, 4 nascent (all with epigenetics)
        for i in range(2):
            feature = make_feature_entity(
                feature_id=f"feature-stable-{i}",
                status="stable",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        for i in range(4):
            feature = make_feature_entity(
                feature_id=f"feature-nascent-{i}",
                status="nascent",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        # Calculate metric
        metric_def = pattern.data["mechanics"]["fitness"]["metrics"][0]
        result = evaluator._calculate_metric(metric_def, pattern, "feature")

        # 2 stable / 4 nascent = 0.5
        assert result.current_value == 0.5
        assert result.achieved is True  # 0.5 >= 0.5 target


class TestSelectPhaseBehaviors:
    """
    BDD behaviors for the SELECT phase of the autoevolutionary loop.

    These tests verify that PatternEvaluator can correctly parse and execute
    fitness metric queries, enabling pattern promotion/deprecation.
    """

    def test_is_not_null_filters_entities(self, repository):
        """
        behavior-is-not-null-filters-entities:
          given: Entities where some have field X populated, others empty/null
          when: Evaluator executes count(type WHERE field IS NOT NULL)
          then: Only entities with non-empty, non-null field are counted
        """
        evaluator = PatternEvaluator(repository)

        # Create pattern
        pattern = make_pattern_with_fitness()
        repository.create(pattern)

        # Feature WITH test_evidence (non-empty)
        with_evidence = make_feature_entity(
            feature_id="feature-with-evidence",
            epigenetics=["pattern-test-fitness"],
        )
        with_evidence.data["test_evidence"] = "http://tests.example"
        repository.create(with_evidence)

        # Feature WITHOUT test_evidence (empty string)
        without_evidence = make_feature_entity(
            feature_id="feature-no-evidence",
            epigenetics=["pattern-test-fitness"],
        )
        without_evidence.data["test_evidence"] = ""
        repository.create(without_evidence)

        # Feature with None
        with_none = make_feature_entity(
            feature_id="feature-none-evidence",
            epigenetics=["pattern-test-fitness"],
        )
        with_none.data["test_evidence"] = None
        repository.create(with_none)

        # Execute IS NOT NULL query
        result = evaluator._execute_metric_query(
            "count(features WHERE test_evidence IS NOT NULL)",
            "pattern-test-fitness",
            "feature"
        )

        # Only the one with actual evidence should be counted
        assert result == 1.0

    def test_is_null_treats_empty_as_null(self, repository):
        """
        behavior-is-null-treats-empty-as-null:
          given: Feature has test_evidence = '' (empty string default)
          when: Evaluator executes count(features WHERE test_evidence IS NULL)
          then: Feature is included (empty string treated as NULL)
        """
        evaluator = PatternEvaluator(repository)

        # Create pattern
        pattern = make_pattern_with_fitness()
        repository.create(pattern)

        # Feature with empty string (should count as NULL)
        empty = make_feature_entity(
            feature_id="feature-empty",
            epigenetics=["pattern-test-fitness"],
        )
        empty.data["test_evidence"] = ""
        repository.create(empty)

        # Feature with None (should count as NULL)
        none_val = make_feature_entity(
            feature_id="feature-none",
            epigenetics=["pattern-test-fitness"],
        )
        none_val.data["test_evidence"] = None
        repository.create(none_val)

        # Feature with value (should NOT count as NULL)
        with_val = make_feature_entity(
            feature_id="feature-with-val",
            epigenetics=["pattern-test-fitness"],
        )
        with_val.data["test_evidence"] = "http://example.com"
        repository.create(with_val)

        # Execute IS NULL query
        result = evaluator._execute_metric_query(
            "count(features WHERE test_evidence IS NULL)",
            "pattern-test-fitness",
            "feature"
        )

        # Both empty and None should be counted as NULL
        assert result == 2.0

    def test_ratio_with_simple_denominator(self, repository):
        """
        behavior-ratio-with-simple-denominator:
          given: Query 'count(features WHERE status='stable') / count(features)'
          when: Evaluator executes the ratio query
          then: Returns correct ratio (numerator / all entities)
        """
        evaluator = PatternEvaluator(repository)

        # Create pattern
        pattern = make_pattern_with_fitness()
        repository.create(pattern)

        # Create 3 stable features
        for i in range(3):
            feature = make_feature_entity(
                feature_id=f"feature-stable-{i}",
                status="stable",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        # Create 7 nascent features (total 10)
        for i in range(7):
            feature = make_feature_entity(
                feature_id=f"feature-nascent-{i}",
                status="nascent",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        # Execute ratio query with simple denominator
        result = evaluator._execute_metric_query(
            "count(features WHERE status='stable') / count(features)",
            "pattern-test-fitness",
            "feature"
        )

        # 3 stable / 10 total = 0.3
        assert result == 0.3

    def test_pattern_evaluation_returns_metrics(self, repository):
        """
        behavior-pattern-evaluation-returns-metrics:
          given: Experimental pattern with fitness metrics defined
          when: PatternEvaluator.evaluate_pattern() is called
          then: All metrics have non-null current_value
        """
        evaluator = PatternEvaluator(repository)

        # Create pattern with metrics
        pattern = make_pattern_with_fitness(metrics=[
            {
                "name": "completion_rate",
                "description": "Ratio of stable features",
                "query": "count(features WHERE status='stable') / count(features)",
                "baseline": 0.3,
                "target": 0.5,
                "direction": "higher_is_better",
            },
            {
                "name": "drift_rate",
                "description": "Ratio of drifting features",
                "query": "count(features WHERE status='drifting') / count(features)",
                "baseline": 0.2,
                "target": 0.1,
                "direction": "lower_is_better",
            },
        ])
        repository.create(pattern)

        # Create some features
        for i in range(5):
            feature = make_feature_entity(
                feature_id=f"feature-{i}",
                status="stable" if i < 3 else "nascent",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        # Evaluate pattern
        report = evaluator.evaluate_pattern(pattern)

        # All metrics should have non-null values
        for metric in report.metrics:
            assert metric.current_value is not None, f"Metric {metric.name} has null value"


class TestConditionEvaluation:
    """Test success/failure condition evaluation."""

    def test_simple_metric_achieved_condition(self, repository):
        """Test evaluating metric.achieved condition."""
        evaluator = PatternEvaluator(repository)

        metric_results = {
            "test_metric": MetricResult(
                name="test_metric",
                description="",
                baseline=0.5,
                target=0.2,
                direction="lower_is_better",
                current_value=0.1,
                achieved=True,
            )
        }

        result = evaluator._evaluate_condition(
            "test_metric.achieved",
            metric_results,
            observation_period_elapsed=False,
        )
        assert result is True

    def test_observation_period_elapsed_condition(self, repository):
        """Test evaluating observation_period.elapsed condition."""
        evaluator = PatternEvaluator(repository)

        result = evaluator._evaluate_condition(
            "observation_period.elapsed",
            {},
            observation_period_elapsed=True,
        )
        assert result is True

        result = evaluator._evaluate_condition(
            "observation_period.elapsed",
            {},
            observation_period_elapsed=False,
        )
        assert result is False

    def test_compound_condition(self, repository):
        """Test evaluating compound AND condition."""
        evaluator = PatternEvaluator(repository)

        metric_results = {
            "metric_a": MetricResult(
                name="metric_a", description="", baseline=None, target=None,
                direction="lower_is_better", current_value=0.1, achieved=True,
            ),
            "metric_b": MetricResult(
                name="metric_b", description="", baseline=None, target=None,
                direction="lower_is_better", current_value=0.5, achieved=False,
            ),
        }

        # Both must be achieved
        result = evaluator._evaluate_condition(
            "metric_a.achieved and metric_b.achieved",
            metric_results,
            observation_period_elapsed=True,
        )
        assert result is False

        # Only one must be achieved
        result = evaluator._evaluate_condition(
            "metric_a.achieved or metric_b.achieved",
            metric_results,
            observation_period_elapsed=True,
        )
        assert result is True


class TestFitnessReportGeneration:
    """Test generating fitness reports."""

    def test_generate_continue_recommendation(self, repository):
        """Test report recommends continue when not enough data."""
        evaluator = PatternEvaluator(repository)

        # Create pattern requiring 10 samples
        pattern = make_pattern_with_fitness(sample_size=10)
        repository.create(pattern)

        # Create only 3 features
        for i in range(3):
            feature = make_feature_entity(
                feature_id=f"feature-{i}",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        report = evaluator.evaluate_pattern(pattern)

        assert report.sample_size_required == 10
        assert report.sample_size_actual == 3
        assert report.recommendation == "continue"

    def test_generate_promote_recommendation(self, repository):
        """Test report recommends promote when success condition met."""
        evaluator = PatternEvaluator(repository)

        # Create pattern with low sample size and achievable target
        pattern = make_pattern_with_fitness(
            sample_size=2,
            observation_period="30 days",
            metrics=[{
                "name": "test_rate",
                "description": "Test",
                "baseline": 1.0,
                "target": 0.5,
                "direction": "lower_is_better",
                "query": "count(features WHERE status='stable') / count(features WHERE status='nascent')",
            }],
            success_condition="test_rate.achieved",
        )
        # Set experimental_since to >30 days ago
        pattern.data["experimental_since"] = (datetime.utcnow() - timedelta(days=35)).isoformat()
        repository.create(pattern)

        # Create 2 stable, 4 nascent = 0.5 ratio (meets target)
        for i in range(2):
            feature = make_feature_entity(
                feature_id=f"feature-stable-{i}",
                status="stable",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        for i in range(4):
            feature = make_feature_entity(
                feature_id=f"feature-nascent-{i}",
                status="nascent",
                epigenetics=["pattern-test-fitness"],
            )
            repository.create(feature)

        report = evaluator.evaluate_pattern(pattern)

        assert report.success_condition_met is True
        assert report.recommendation == "promote"
        assert len(report.actions_to_take) > 0


class TestActionExecution:
    """Test executing fitness actions."""

    def test_execute_status_transition(self, repository):
        """Test executing pattern status transition."""
        evaluator = PatternEvaluator(repository)

        pattern = make_pattern_with_fitness()
        repository.create(pattern)

        result = evaluator._execute_action(
            "transition(pattern.status='adopted')",
            pattern,
        )

        assert "adopted" in result

        updated = repository.read(pattern.id)
        assert updated.status == "adopted"

    def test_execute_finalize(self, repository):
        """Test executing finalize action."""
        evaluator = PatternEvaluator(repository)

        pattern = make_pattern_with_fitness()
        repository.create(pattern)

        result = evaluator._execute_action("finalize(pattern)", pattern)

        assert "Finalized" in result

        updated = repository.read(pattern.id)
        assert updated.status == "deprecated"


class TestEvaluatorSummary:
    """Test evaluator summary generation."""

    def test_get_summary(self, repository):
        """Test getting summary of all patterns."""
        evaluator = PatternEvaluator(repository)

        # Create two patterns
        pattern1 = make_pattern_with_fitness(pattern_id="pattern-one")
        pattern2 = make_pattern_with_fitness(pattern_id="pattern-two")
        repository.create(pattern1)
        repository.create(pattern2)

        summary = evaluator.get_summary()

        assert summary["total_patterns"] == 2
        assert len(summary["patterns"]) == 2


# ═══════════════════════════════════════════════════════════════════════════
# CANARY MONITOR TESTS - Bricking Detection Safety System
# ═══════════════════════════════════════════════════════════════════════════

from chora_store.evaluator import CanaryMonitor, CanaryAlert, CANARY_THRESHOLDS


def make_pattern_for_canary(
    pattern_id: str = "pattern-canary-test",
    target: str = "feature",
    operation_stats: dict = None,
    metric_history: list = None,
) -> Entity:
    """Helper to create pattern for canary testing."""
    data = {
        "name": "Canary Test Pattern",
        "subtype": "schema-extension",
        "experimental_since": (datetime.utcnow() - timedelta(days=10)).isoformat(),
        "mechanics": {
            "target": target,
            "inject_fields": {},
            "hooks": [],
            "fitness": {
                "observation_period": "90 days",
                "sample_size": 5,
                "metrics": [],
            },
        },
    }

    if operation_stats:
        data["_operation_stats"] = operation_stats

    if metric_history:
        data["_metric_history"] = metric_history

    return Entity(
        id=pattern_id,
        type="pattern",
        status="experimental",
        data=data,
    )


class TestCanaryMonitorInit:
    """Test canary monitor initialization."""

    def test_init_with_defaults(self, repository):
        """Test canary monitor initializes with default thresholds."""
        monitor = CanaryMonitor(repository)

        assert monitor.thresholds == CANARY_THRESHOLDS
        assert monitor.repository == repository

    def test_init_with_custom_thresholds(self, repository):
        """Test canary monitor accepts custom thresholds."""
        custom = {"reversion_count": 10, "reversion_window_days": 14}
        monitor = CanaryMonitor(repository, thresholds=custom)

        assert monitor.thresholds["reversion_count"] == 10
        assert monitor.thresholds["reversion_window_days"] == 14


class TestReversionDetection:
    """Test detection of excessive reversions."""

    def test_no_alert_below_threshold(self, repository):
        """Test no alert when reversions below threshold."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        # Create features without reversions
        for i in range(3):
            feature = make_feature_entity(
                feature_id=f"feature-clean-{i}",
                epigenetics=["pattern-canary-test"],
            )
            repository.create(feature)

        alert = monitor._check_reversions(pattern)
        assert alert is None

    def test_alert_when_above_threshold(self, repository):
        """Test alert when reversions exceed threshold."""
        monitor = CanaryMonitor(repository, thresholds={
            **CANARY_THRESHOLDS,
            "reversion_count": 2,  # Low threshold for testing
        })

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        # Create features WITH reversions
        now = datetime.utcnow()
        for i in range(4):
            feature = Entity(
                id=f"feature-reverted-{i}",
                type="feature",
                status="converging",
                data={
                    "name": f"Reverted Feature {i}",
                    "_epigenetics": ["pattern-canary-test"],
                    "_last_reversion": now.isoformat(),
                    "quality_gate_reversion": True,
                },
                created_at=now,
                updated_at=now,
            )
            repository.create(feature)

        alert = monitor._check_reversions(pattern)

        assert alert is not None
        assert alert.signal == "excessive_reversions"
        assert alert.pattern_id == "pattern-canary-test"

    def test_critical_severity_for_double_threshold(self, repository):
        """Test critical severity when reversions > 2x threshold."""
        monitor = CanaryMonitor(repository, thresholds={
            **CANARY_THRESHOLDS,
            "reversion_count": 2,
        })

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        # Create many reverted features (> 2x threshold = 4)
        now = datetime.utcnow()
        for i in range(6):
            feature = Entity(
                id=f"feature-reverted-{i}",
                type="feature",
                status="converging",
                data={
                    "name": f"Reverted Feature {i}",
                    "_epigenetics": ["pattern-canary-test"],
                    "_last_reversion": now.isoformat(),
                },
                created_at=now,
                updated_at=now,
            )
            repository.create(feature)

        alert = monitor._check_reversions(pattern)

        assert alert is not None
        assert alert.severity == "critical"


class TestFitnessTrendDetection:
    """Test detection of negative fitness trends."""

    def test_no_alert_without_history(self, repository):
        """Test no alert when no metric history."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        alert = monitor._check_fitness_trend(pattern)
        assert alert is None

    def test_no_alert_with_improving_trend(self, repository):
        """Test no alert when metrics improving."""
        monitor = CanaryMonitor(repository)

        # Metric history with improving values (lower is better)
        history = [
            {"timestamp": datetime.utcnow().isoformat(), "metrics": {"rate": 0.2}},
            {"timestamp": (datetime.utcnow() - timedelta(days=1)).isoformat(), "metrics": {"rate": 0.3}},
            {"timestamp": (datetime.utcnow() - timedelta(days=2)).isoformat(), "metrics": {"rate": 0.4}},
            {"timestamp": (datetime.utcnow() - timedelta(days=3)).isoformat(), "metrics": {"rate": 0.5}},
        ]

        pattern = make_pattern_for_canary(metric_history=history)
        repository.create(pattern)

        alert = monitor._check_fitness_trend(pattern)
        assert alert is None

    def test_alert_with_declining_trend(self, repository):
        """Test alert when metrics declining."""
        monitor = CanaryMonitor(repository, thresholds={
            **CANARY_THRESHOLDS,
            "trend_decline_count": 3,
        })

        # Metric history with declining values (lower should be better, but getting worse)
        history = [
            {"timestamp": datetime.utcnow().isoformat(), "metrics": {"rate": 0.5}},
            {"timestamp": (datetime.utcnow() - timedelta(days=1)).isoformat(), "metrics": {"rate": 0.4}},
            {"timestamp": (datetime.utcnow() - timedelta(days=2)).isoformat(), "metrics": {"rate": 0.3}},
            {"timestamp": (datetime.utcnow() - timedelta(days=3)).isoformat(), "metrics": {"rate": 0.2}},
        ]

        pattern = make_pattern_for_canary(metric_history=history)
        repository.create(pattern)

        alert = monitor._check_fitness_trend(pattern)

        assert alert is not None
        assert alert.signal == "negative_trend"


class TestFailureRateDetection:
    """Test detection of high operation failure rates."""

    def test_no_alert_without_enough_data(self, repository):
        """Test no alert when not enough operations."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary(operation_stats={
            "total_operations": 5,  # Below min_operations threshold
            "failed_operations": 3,
        })
        repository.create(pattern)

        alert = monitor._check_failure_rate(pattern)
        assert alert is None

    def test_no_alert_below_threshold(self, repository):
        """Test no alert when failure rate below threshold."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary(operation_stats={
            "total_operations": 100,
            "failed_operations": 5,  # 5% failure rate
        })
        repository.create(pattern)

        alert = monitor._check_failure_rate(pattern)
        assert alert is None  # Default threshold is 10%

    def test_alert_above_threshold(self, repository):
        """Test alert when failure rate above threshold."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary(operation_stats={
            "total_operations": 100,
            "failed_operations": 15,  # 15% failure rate
        })
        repository.create(pattern)

        alert = monitor._check_failure_rate(pattern)

        assert alert is not None
        assert alert.signal == "failure_spike"
        assert "15.0%" in alert.details

    def test_critical_severity_for_high_failure_rate(self, repository):
        """Test critical severity when failure rate > 2x threshold."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary(operation_stats={
            "total_operations": 100,
            "failed_operations": 25,  # 25% > 20% (2x threshold)
        })
        repository.create(pattern)

        alert = monitor._check_failure_rate(pattern)

        assert alert is not None
        assert alert.severity == "critical"


class TestCanaryAutoDisable:
    """Test automatic pattern disabling."""

    def test_disable_pattern_transitions_status(self, repository):
        """Test that disable_pattern transitions pattern to deprecated."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        monitor.disable_pattern(pattern.id, reason="Test disable")

        updated = repository.read(pattern.id)
        assert updated.status == "deprecated"
        assert updated.data.get("disabled_by_canary") is True
        assert updated.data.get("disabled_reason") == "Test disable"

    def test_disable_pattern_creates_learning(self, repository):
        """Test that disable_pattern creates a learning."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        learning_id = monitor.disable_pattern(pattern.id, create_learning=True)

        assert learning_id is not None
        learning = repository.read(learning_id)
        assert learning is not None
        assert "disabled by canary" in learning.data.get("name", "").lower()

    def test_disable_without_learning(self, repository):
        """Test disable_pattern without creating learning."""
        monitor = CanaryMonitor(repository)

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        learning_id = monitor.disable_pattern(pattern.id, create_learning=False)

        assert learning_id is None


class TestCanaryCheckAll:
    """Test checking all patterns."""

    def test_check_all_returns_all_alerts(self, repository):
        """Test check_all aggregates alerts from all patterns."""
        monitor = CanaryMonitor(repository, thresholds={
            **CANARY_THRESHOLDS,
            "reversion_count": 1,  # Threshold is 1, so need >1 to trigger
        })

        # Create pattern with issues
        pattern = make_pattern_for_canary()
        repository.create(pattern)

        # Create multiple reverted features (need > threshold to trigger alert)
        now = datetime.utcnow()
        for i in range(3):  # Create 3 reverted features (> threshold of 1)
            feature = Entity(
                id=f"feature-reverted-{i}",
                type="feature",
                status="converging",
                data={
                    "name": f"Reverted Feature {i}",
                    "_epigenetics": ["pattern-canary-test"],
                    "_last_reversion": now.isoformat(),
                },
                created_at=now,
                updated_at=now,
            )
            repository.create(feature)

        alerts = monitor.check_all()

        # Should find at least the reversion alert
        assert len(alerts) >= 1


class TestCanarySummary:
    """Test canary summary generation."""

    def test_healthy_summary(self, repository):
        """Test summary shows healthy when no alerts."""
        monitor = CanaryMonitor(repository)

        # Create clean pattern
        pattern = make_pattern_for_canary()
        repository.create(pattern)

        summary = monitor.get_summary()

        assert summary["health"] == "healthy"
        assert summary["critical_alerts"] == 0
        assert summary["warning_alerts"] == 0

    def test_warning_summary(self, repository):
        """Test summary shows warning with warning alerts."""
        monitor = CanaryMonitor(repository, thresholds={
            **CANARY_THRESHOLDS,
            "reversion_count": 1,
        })

        pattern = make_pattern_for_canary()
        repository.create(pattern)

        # Create reverted features
        now = datetime.utcnow()
        for i in range(2):
            feature = Entity(
                id=f"feature-reverted-{i}",
                type="feature",
                status="converging",
                data={
                    "name": f"Reverted {i}",
                    "_epigenetics": ["pattern-canary-test"],
                    "_last_reversion": now.isoformat(),
                },
                created_at=now,
                updated_at=now,
            )
            repository.create(feature)

        summary = monitor.get_summary()

        assert summary["health"] in ["warning", "critical"]
        assert summary["warning_alerts"] + summary["critical_alerts"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# PATTERN INDUCTOR TESTS - Learning Analysis and Pattern Proposal System
# ═══════════════════════════════════════════════════════════════════════════

from chora_store.evaluator import PatternInductor, PatternProposal, INDUCTION_THRESHOLDS


def make_learning_entity(
    learning_id: str = "learning-test",
    domain: str = "general",
    insight: str = "Test insight",
    name: str = "Test Learning",
    status: str = "captured",
) -> Entity:
    """Helper to create learning for inductor testing."""
    now = datetime.utcnow()
    return Entity(
        id=learning_id,
        type="learning",
        status=status,
        data={
            "name": name,
            "domain": domain,
            "insight": insight,
        },
        created_at=now,
        updated_at=now,
    )


class TestPatternInductorInit:
    """Test pattern inductor initialization."""

    def test_init_with_defaults(self, repository):
        """Test inductor initializes with default thresholds."""
        inductor = PatternInductor(repository)

        assert inductor.thresholds == INDUCTION_THRESHOLDS
        assert inductor.repository == repository

    def test_init_with_custom_thresholds(self, repository):
        """Test inductor accepts custom thresholds."""
        custom = {"min_learnings": 5, "confidence_threshold": 0.8}
        inductor = PatternInductor(repository, thresholds=custom)

        assert inductor.thresholds["min_learnings"] == 5
        assert inductor.thresholds["confidence_threshold"] == 0.8


class TestKeywordExtraction:
    """Test keyword extraction for clustering."""

    def test_extract_keywords(self, repository):
        """Test basic keyword extraction."""
        inductor = PatternInductor(repository)

        keywords = inductor._extract_keywords("Pattern matching algorithm for features")

        assert "pattern" in keywords
        assert "matching" in keywords
        assert "algorithm" in keywords
        assert "features" in keywords
        # Stopwords should be removed
        assert "for" not in keywords
        assert "the" not in keywords

    def test_extract_keywords_empty(self, repository):
        """Test keyword extraction with empty string."""
        inductor = PatternInductor(repository)

        keywords = inductor._extract_keywords("")
        assert keywords == []

    def test_keyword_overlap(self, repository):
        """Test calculating keyword overlap."""
        inductor = PatternInductor(repository)

        keywords1 = ["pattern", "matching", "algorithm"]
        keywords2 = ["pattern", "matching", "feature"]

        overlap = inductor._calculate_keyword_overlap(keywords1, keywords2)

        # Jaccard: 2 common / 4 total = 0.5
        assert overlap == 0.5


class TestLearningClustering:
    """Test clustering learnings by domain and keywords."""

    def test_cluster_by_domain(self, repository):
        """Test learnings are clustered by domain."""
        inductor = PatternInductor(repository)

        # Create learnings in different domains
        for i in range(3):
            learning = make_learning_entity(
                learning_id=f"learning-domain-a-{i}",
                domain="domain-a",
                insight=f"Insight about domain A topic {i}",
            )
            repository.create(learning)

        for i in range(3):
            learning = make_learning_entity(
                learning_id=f"learning-domain-b-{i}",
                domain="domain-b",
                insight=f"Insight about domain B topic {i}",
            )
            repository.create(learning)

        clusters = inductor._cluster_learnings()

        # Should have clusters for both domains
        domain_keys = [k.split("_")[0] for k in clusters.keys()]
        assert "domain-a" in domain_keys
        assert "domain-b" in domain_keys


class TestProposalGeneration:
    """Test generating pattern proposals from clusters."""

    def test_no_proposal_below_threshold(self, repository):
        """Test no proposal when too few learnings."""
        inductor = PatternInductor(repository, thresholds={
            **INDUCTION_THRESHOLDS,
            "min_learnings": 5,
        })

        # Create only 2 learnings
        for i in range(2):
            learning = make_learning_entity(
                learning_id=f"learning-{i}",
                domain="test-domain",
            )
            repository.create(learning)

        proposals = inductor.analyze()
        assert len(proposals) == 0

    def test_generate_proposal_above_threshold(self, repository):
        """Test proposal generated when enough learnings."""
        inductor = PatternInductor(repository, thresholds={
            **INDUCTION_THRESHOLDS,
            "min_learnings": 3,
            "confidence_threshold": 0.3,  # Low threshold for testing
            "keyword_overlap": 0.1,
        })

        # Create 4 similar learnings
        for i in range(4):
            learning = make_learning_entity(
                learning_id=f"learning-similar-{i}",
                domain="testing",
                name=f"Testing pattern {i}",
                insight=f"Testing patterns are important for quality {i}",
            )
            repository.create(learning)

        proposals = inductor.analyze()

        assert len(proposals) >= 1
        assert proposals[0].domain == "testing"

    def test_proposal_includes_source_learnings(self, repository):
        """Test proposal tracks source learnings."""
        inductor = PatternInductor(repository, thresholds={
            **INDUCTION_THRESHOLDS,
            "min_learnings": 3,
            "confidence_threshold": 0.3,
            "keyword_overlap": 0.1,
        })

        # Create learnings
        learning_ids = []
        for i in range(3):
            learning = make_learning_entity(
                learning_id=f"learning-tracked-{i}",
                domain="tracked",
                insight=f"Common insight about tracking {i}",
            )
            repository.create(learning)
            learning_ids.append(learning.id)

        proposals = inductor.analyze()

        if proposals:
            # Source learnings should be tracked
            assert len(proposals[0].source_learnings) >= 3


class TestConfidenceCalculation:
    """Test confidence score calculation."""

    def test_confidence_increases_with_count(self, repository):
        """Test confidence increases with more learnings."""
        inductor = PatternInductor(repository)

        # Create learnings with same keywords
        learnings = []
        for i in range(6):
            learning = make_learning_entity(
                learning_id=f"learning-conf-{i}",
                domain="confidence-test",
                insight="Testing confidence calculation with patterns",
            )
            repository.create(learning)
            learnings.append(learning)

        # Confidence should be reasonable with 6 learnings
        confidence = inductor._calculate_confidence(learnings)

        assert confidence > 0.5


class TestProposalApproval:
    """Test approving proposals to create patterns."""

    def test_approve_creates_pattern(self, repository):
        """Test approving proposal creates pattern entity."""
        inductor = PatternInductor(repository)

        # Create a proposal manually
        proposal = PatternProposal(
            id="pattern-proposed-test",
            name="Test Proposed Pattern",
            description="A test pattern from induction",
            source_learnings=["learning-1", "learning-2", "learning-3"],
            domain="test",
            confidence=0.75,
            suggested_target="feature",
            suggested_fields={},
        )

        # Create source learnings
        for i in range(3):
            learning = make_learning_entity(
                learning_id=f"learning-{i+1}",
                domain="test",
            )
            repository.create(learning)

        pattern = inductor.approve_proposal(proposal)

        assert pattern is not None
        assert pattern.type == "pattern"
        assert pattern.status == "proposed"
        assert "induced_from" in pattern.data

    def test_approve_marks_learnings_applied(self, repository):
        """Test approving proposal marks source learnings as applied."""
        inductor = PatternInductor(repository)

        # Create source learnings
        for i in range(3):
            learning = make_learning_entity(
                learning_id=f"learning-apply-{i}",
                domain="apply-test",
                status="captured",
            )
            repository.create(learning)

        proposal = PatternProposal(
            id="pattern-proposed-apply",
            name="Apply Test Pattern",
            description="Testing learning application",
            source_learnings=["learning-apply-0", "learning-apply-1", "learning-apply-2"],
            domain="apply-test",
            confidence=0.8,
            suggested_target="feature",
            suggested_fields={},
        )

        inductor.approve_proposal(proposal)

        # Check learnings were marked as applied
        for i in range(3):
            learning = repository.read(f"learning-apply-{i}")
            assert learning.status == "applied"


class TestInductorSummary:
    """Test inductor summary generation."""

    def test_summary_includes_stats(self, repository):
        """Test summary includes learning stats."""
        inductor = PatternInductor(repository)

        # Create learnings with different statuses (unique IDs)
        import uuid
        for i, status in enumerate(["captured", "captured", "validated", "applied"]):
            learning = make_learning_entity(
                learning_id=f"learning-stats-{i}-{uuid.uuid4().hex[:8]}",
                status=status,
            )
            repository.create(learning)

        summary = inductor.get_summary()

        assert summary["total_learnings"] >= 4
        assert "captured" in summary
        assert "validated" in summary
        assert "applied" in summary

    def test_summary_includes_proposals(self, repository):
        """Test summary includes proposals when available."""
        inductor = PatternInductor(repository, thresholds={
            **INDUCTION_THRESHOLDS,
            "min_learnings": 3,
            "confidence_threshold": 0.3,
            "keyword_overlap": 0.1,
        })

        # Create enough learnings for a proposal
        for i in range(4):
            learning = make_learning_entity(
                learning_id=f"learning-summary-{i}",
                domain="summary-test",
                insight="Summary testing with similar keywords",
            )
            repository.create(learning)

        summary = inductor.get_summary()

        assert "proposals" in summary
        assert "proposals_count" in summary
